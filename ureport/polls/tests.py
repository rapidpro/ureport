import json
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.http import HttpRequest
from django.template import TemplateSyntaxError
from django.test import TestCase
from django.utils.text import slugify

import pycountry

from mock import patch, Mock
from dash.categories.models import Category, CategoryImage
from temba_client.client import Result, Flow, Group
from ureport.polls.models import Poll, PollQuestion, FeaturedResponse, PollImage, CACHE_POLL_RESULTS_KEY
from ureport.polls.models import UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME
from ureport.polls.tasks import refresh_main_poll, refresh_brick_polls, refresh_other_polls, refresh_org_flows
from ureport.polls.tasks import refresh_org_reporters, refresh_org_graphs_data, fetch_poll
from ureport.tests import DashTest, MockAPI, MockTembaClient


class PollTest(DashTest):
    def setUp(self):
        super(PollTest, self).setUp()
        self.uganda = self.create_org('uganda', self.admin)
        self.nigeria = self.create_org('nigeria', self.admin)

        self.health_uganda = Category.objects.create(org=self.uganda,
                                                     name="Health",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

    def test_poll_get_main_poll(self):
        self.assertIsNone(Poll.get_main_poll(self.uganda))
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertEquals(unicode(poll1), 'Poll 1')

        self.assertIsNone(Poll.get_main_poll(self.uganda))
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid='uuid-101',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.assertEquals(Poll.get_main_poll(self.uganda), poll1)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll2 = Poll.objects.create(flow_uuid="uuid-2",
                                    title="Poll 2",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2_question = PollQuestion.objects.create(poll=poll2,
                                                     title='question poll 2',
                                                     ruleset_uuid='uuid-202',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.assertEquals(Poll.get_main_poll(self.uganda), poll2)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))


        poll3 = Poll.objects.create(flow_uuid="uuid-3",
                                    title="Poll 3",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll3_question = PollQuestion.objects.create(poll=poll3,
                                                     title='question poll 3',
                                                     ruleset_uuid='uuid-303',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.assertEquals(Poll.get_main_poll(self.uganda), poll3)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll1.is_featured = True
        poll1.save()

        self.assertEquals(Poll.get_main_poll(self.uganda), poll1)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll1.is_active = False
        poll1.save()

        self.assertEquals(Poll.get_main_poll(self.uganda), poll3)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertIsNone(Poll.get_main_poll(self.uganda))
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

    def test_brick_polls(self):
        self.assertFalse(Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertFalse(Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid='uuid-101',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.assertFalse(Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll2 = Poll.objects.create(flow_uuid="uuid-2",
                                    title="Poll 2",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertFalse(Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))


        poll2_question = PollQuestion.objects.create(poll=poll2,
                                                     title='question poll 2',
                                                     ruleset_uuid='uuid-202',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.assertTrue(Poll.get_brick_polls(self.uganda))
        self.assertTrue(poll2 in Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll2.is_active = False
        poll2.save()

        self.assertFalse(Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll2.is_active = True
        poll2.save()
        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertFalse(Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        self.health_uganda.is_active = True
        self.health_uganda.save()

        poll3 = Poll.objects.create(flow_uuid="uuid-3",
                                    title="Poll 3",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertTrue(Poll.get_brick_polls(self.uganda))
        self.assertTrue(poll2 in Poll.get_brick_polls(self.uganda))
        self.assertTrue(poll3 not in Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll3_question = PollQuestion.objects.create(poll=poll3,
                                                     title='question poll 3',
                                                     ruleset_uuid='uuid-303',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.assertTrue(Poll.get_brick_polls(self.uganda))
        self.assertTrue(poll2 in Poll.get_brick_polls(self.uganda))
        self.assertTrue(poll3 in Poll.get_brick_polls(self.uganda))

        with patch('ureport.polls.models.Poll.get_first_question') as mock_first_question:
            mock_first_question.return_value = None

            self.assertFalse(Poll.get_brick_polls(self.uganda))

        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll3.is_featured = True
        poll3.save()

        self.assertTrue(Poll.get_brick_polls(self.uganda))
        self.assertTrue(poll2 in Poll.get_brick_polls(self.uganda))
        self.assertTrue(poll1 in Poll.get_brick_polls(self.uganda))
        self.assertEquals(Poll.get_brick_polls(self.uganda)[0], poll1)
        self.assertEquals(Poll.get_brick_polls(self.uganda)[1], poll2)
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll1.is_featured = False
        poll1.save()

        self.assertTrue(Poll.get_brick_polls(self.uganda))
        self.assertTrue(poll2 in Poll.get_brick_polls(self.uganda))
        self.assertTrue(poll1 in Poll.get_brick_polls(self.uganda))
        self.assertEquals(Poll.get_brick_polls(self.uganda)[0], poll2)
        self.assertEquals(Poll.get_brick_polls(self.uganda)[1], poll1)
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

    def test_get_flow(self):
        with patch('dash.orgs.models.Org.get_flows') as mock:
            mock.return_value = {'uuid-1': "Flow"}

            poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                        title="Poll 1",
                                        category=self.health_uganda,
                                        is_featured=True,
                                        org=self.uganda,
                                        created_by=self.admin,
                                        modified_by=self.admin)

            self.assertEquals(poll1.get_flow(), 'Flow')
            mock.assert_called_once_with()

    def test_best_and_worst(self):

        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        with patch('ureport.polls.models.PollQuestion.get_results') as mock:
            mock.return_value = [{u'open_ended': False, u'label': u'Abia', u'set': 338, u'unset': 36, u'boundary': u'R3713501', u'categories': [{u'count': 80, u'label': u'Yes'}, {u'count': 258, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Adamawa', u'set': 84, u'unset': 7, u'boundary': u'R3720358', u'categories': [{u'count': 41, u'label': u'Yes'}, {u'count': 43, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Akwa Ibom', u'set': 149, u'unset': 14, u'boundary': u'R3715359', u'categories': [{u'count': 41, u'label': u'Yes'}, {u'count': 108, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Anambra', u'set': 319, u'unset': 50, u'boundary': u'R3715505', u'categories': [{u'count': 81, u'label': u'Yes'}, {u'count': 238, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Bauchi', u'set': 59, u'unset': 5, u'boundary': u'R3722233', u'categories': [{u'count': 20, u'label': u'Yes'}, {u'count': 39, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Bayelsa', u'set': 102, u'unset': 11, u'boundary': u'R3715844', u'categories': [{u'count': 26, u'label': u'Yes'}, {u'count': 76, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Benue', u'set': 267, u'unset': 27, u'boundary': u'R3716076', u'categories': [{u'count': 115, u'label': u'Yes'}, {u'count': 152, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Borno', u'set': 76, u'unset': 5, u'boundary': u'R3721167', u'categories': [{u'count': 16, u'label': u'Yes'}, {u'count': 60, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Cross River', u'set': 120, u'unset': 17, u'boundary': u'R3716250', u'categories': [{u'count': 29, u'label': u'Yes'}, {u'count': 91, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Delta', u'set': 168, u'unset': 22, u'boundary': u'R3716950', u'categories': [{u'count': 39, u'label': u'Yes'}, {u'count': 129, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Ebonyi', u'set': 134, u'unset': 14, u'boundary': u'R3717071', u'categories': [{u'count': 24, u'label': u'Yes'}, {u'count': 110, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Edo', u'set': 193, u'unset': 17, u'boundary': u'R3717119', u'categories': [{u'count': 50, u'label': u'Yes'}, {u'count': 143, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Ekiti', u'set': 151, u'unset': 22, u'boundary': u'R3717154', u'categories': [{u'count': 27, u'label': u'Yes'}, {u'count': 124, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Enugu', u'set': 291, u'unset': 37, u'boundary': u'R3717212', u'categories': [{u'count': 109, u'label': u'Yes'}, {u'count': 182, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Federal Capital Territory', u'set': 940, u'unset': 87, u'boundary': u'R3717259', u'categories': [{u'count': 328, u'label': u'Yes'}, {u'count': 612, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Gombe', u'set': 73, u'unset': 7, u'boundary': u'R3720422', u'categories': [{u'count': 26, u'label': u'Yes'}, {u'count': 47, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Imo', u'set': 233, u'unset': 14, u'boundary': u'R3717825', u'categories': [{u'count': 50, u'label': u'Yes'}, {u'count': 183, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Jigawa', u'set': 69, u'unset': 5, u'boundary': u'R3703236', u'categories': [{u'count': 26, u'label': u'Yes'}, {u'count': 43, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Kaduna', u'set': 291, u'unset': 34, u'boundary': u'R3709353', u'categories': [{u'count': 121, u'label': u'Yes'}, {u'count': 170, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Kano', u'set': 222, u'unset': 23, u'boundary': u'R3710302', u'categories': [{u'count': 79, u'label': u'Yes'}, {u'count': 143, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Katsina', u'set': 293, u'unset': 23, u'boundary': u'R3711481', u'categories': [{u'count': 105, u'label': u'Yes'}, {u'count': 188, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Kebbi', u'set': 124, u'unset': 19, u'boundary': u'R3707933', u'categories': [{u'count': 34, u'label': u'Yes'}, {u'count': 90, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Kogi', u'set': 108, u'unset': 13, u'boundary': u'R3717971', u'categories': [{u'count': 41, u'label': u'Yes'}, {u'count': 67, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Kwara', u'set': 183, u'unset': 23, u'boundary': u'R3718090', u'categories': [{u'count': 68, u'label': u'Yes'}, {u'count': 115, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Lagos', u'set': 460, u'unset': 33, u'boundary': u'R3718182', u'categories': [{u'count': 172, u'label': u'Yes'}, {u'count': 288, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Nasarawa', u'set': 182, u'unset': 16, u'boundary': u'R3720495', u'categories': [{u'count': 52, u'label': u'Yes'}, {u'count': 130, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Niger', u'set': 224, u'unset': 21, u'boundary': u'R3718384', u'categories': [{u'count': 68, u'label': u'Yes'}, {u'count': 156, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Ogun', u'set': 274, u'unset': 16, u'boundary': u'R3718463', u'categories': [{u'count': 81, u'label': u'Yes'}, {u'count': 193, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Ondo', u'set': 271, u'unset': 19, u'boundary': u'R3718605', u'categories': [{u'count': 45, u'label': u'Yes'}, {u'count': 226, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Osun', u'set': 133, u'unset': 16, u'boundary': u'R3718720', u'categories': [{u'count': 51, u'label': u'Yes'}, {u'count': 82, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Oyo', u'set': 187, u'unset': 12, u'boundary': u'R3720554', u'categories': [{u'count': 65, u'label': u'Yes'}, {u'count': 122, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Plateau', u'set': 416, u'unset': 31, u'boundary': u'R3720611', u'categories': [{u'count': 151, u'label': u'Yes'}, {u'count': 265, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Rivers', u'set': 192, u'unset': 18, u'boundary': u'R3720743', u'categories': [{u'count': 49, u'label': u'Yes'}, {u'count': 143, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Sokoto', u'set': 143, u'unset': 15, u'boundary': u'R3707368', u'categories': [{u'count': 60, u'label': u'Yes'}, {u'count': 83, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Taraba', u'set': 142, u'unset': 8, u'boundary': u'R3720850', u'categories': [{u'count': 60, u'label': u'Yes'}, {u'count': 82, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Yobe', u'set': 50, u'unset': 7, u'boundary': u'R3698564', u'categories': [{u'count': 16, u'label': u'Yes'}, {u'count': 34, u'label': u'No'}]}, {u'open_ended': False, u'label': u'Zamfara', u'set': 85, u'unset': 9, u'boundary': u'R3706956', u'categories': [{u'count': 28, u'label': u'Yes'}, {u'count': 57, u'label': u'No'}]}]

            results = [{'percent': 91, 'boundary': u'Federal Capital Territory', 'total': 1027, 'type': 'best', 'responded': 940}, {'percent': 93, 'boundary': u'Lagos', 'total': 493, 'type': 'best', 'responded': 460}, {'percent': 93, 'boundary': u'Plateau', 'total': 447, 'type': 'best', 'responded': 416}, {'percent': 92, 'boundary': u'Bauchi', 'total': 64, 'type': 'worst', 'responded': 59}, {'percent': 87, 'boundary': u'Yobe', 'total': 57, 'type': 'worst', 'responded': 50}]

            self.assertEquals(poll1.best_and_worst(), results)
            mock.assert_called_once_with(segment=dict(location="State"))

        with patch('ureport.polls.models.PollQuestion.get_results') as mock:
            mock.return_value = None

            results = []

            self.assertEquals(poll1.best_and_worst(), results)
            mock.assert_called_once_with(segment=dict(location="State"))


    def test_get_featured_responses(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertFalse(poll1.get_featured_responses())

        featured_response1= FeaturedResponse.objects.create(poll=poll1,
                                                            location="Kampala",
                                                            reporter="James",
                                                            message="Awesome",
                                                            created_by=self.admin,
                                                            modified_by=self.admin)
        self.assertEquals(unicode(featured_response1), 'Poll 1 - Kampala - Awesome')

        featured_response1.is_active = False
        featured_response1.save()

        self.assertFalse(poll1.get_featured_responses())

        featured_response1.is_active = True
        featured_response1.save()

        self.assertEquals(len(poll1.get_featured_responses()), 1)
        self.assertTrue(featured_response1 in poll1.get_featured_responses())

        featured_response2 = FeaturedResponse.objects.create(poll=poll1,
                                                             location="Entebbe",
                                                             reporter="George",
                                                             message="Exactly",
                                                             created_by=self.admin,
                                                             modified_by=self.admin)

        self.assertEquals(len(poll1.get_featured_responses()), 2)
        self.assertEquals(poll1.get_featured_responses()[0], featured_response2)
        self.assertEquals(poll1.get_featured_responses()[1], featured_response1)

    def test_runs(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertEquals(poll1.runs(), "----")

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        fetched_results = [dict(open_ended=False, set=40, unset=60, categories=[dict(count=15, label='Yes'),
                                                                                dict(count=25, label='No')],
                                label='All')]

        with patch('ureport.polls.models.PollQuestion.get_results') as mock:
            mock.return_value = fetched_results

            self.assertEquals(poll1.runs(), 100)
            mock.assert_called_with()

    def test_responded_runs(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertEquals(poll1.responded_runs(), "---")

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        fetched_results = [dict(open_ended=False, set=40, unset=60, categories=[dict(count=15, label='Yes'),
                                                                                dict(count=25, label='No')],
                                label='All')]

        with patch('ureport.polls.models.PollQuestion.get_results') as mock:
            mock.return_value = fetched_results

            self.assertEquals(poll1.responded_runs(), 40)
            mock.assert_called_once_with()

    def test_response_percentage(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertEquals(poll1.response_percentage(), "---")

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        fetched_results = [dict(open_ended=False, set=40, unset=60, categories=[dict(count=15, label='Yes'),
                                                                                dict(count=25, label='No')],
                                label='All')]

        with patch('ureport.polls.models.PollQuestion.get_results') as mock:
            mock.return_value = fetched_results

            self.assertEquals(poll1.response_percentage(), "40%")
            mock.assert_called_with()

    def test_get_featured_images(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertFalse(poll1.get_featured_images())

        poll_image1 = PollImage.objects.create(name='image 1',
                                               poll=poll1,
                                               created_by=self.admin,
                                               modified_by=self.admin)

        self.assertEquals(unicode(poll_image1), 'Poll 1 - image 1')

        self.assertFalse(poll1.get_featured_images())

        poll_image1.image = 'polls/image.jpg'
        poll_image1.is_active = False
        poll_image1.save()

        self.assertFalse(poll1.get_featured_images())

        poll_image1.is_active = True
        poll_image1.save()

        self.assertTrue(poll1.get_featured_images())
        self.assertTrue(poll_image1 in poll1.get_featured_images())
        self.assertEquals(len(poll1.get_featured_images()), 1)


    def test_get_categoryimage(self):

        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        self.assertEquals(poll1.get_category_image(), self.health_uganda.get_first_image())

        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertIsNone(poll1.get_category_image())

        self.health_uganda.is_active = True
        self.health_uganda.save()

        self.assertEquals(poll1.get_category_image(), self.health_uganda.get_first_image())

        category_image1 = CategoryImage.objects.create(category=self.health_uganda,
                                                       name='image 1',
                                                       image='categories/some_image.jpg',
                                                       created_by=self.admin,
                                                       modified_by=self.admin)

        poll1.category_image = category_image1
        poll1.save()

        self.assertEquals(poll1.get_category_image(), poll1.category_image.image)

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
    def test_create_poll(self):
        create_url = reverse('polls.poll_create')

        response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        with patch('dash.orgs.models.Org.get_flows') as mock:
            flows_cached = dict()
            flows_cached['uuid-25'] = dict(runs=300, completed_runs=120, name='Flow 1', uuid='uuid-25', participants=300,
                                           labels="", archived=False, created_on="2015-04-08T12:48:44.320Z",
                                           rulesets=[dict(uuid='uuid-8435', id=8435, response_type="C",
                                                          label='Does your community have power')])

            mock.return_value = flows_cached

            self.login(self.admin)
            response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
            self.assertEquals(response.status_code, 200)
            self.assertTrue('form' in response.context)

            self.assertEquals(len(response.context['form'].fields), 6)
            self.assertTrue('is_featured' in response.context['form'].fields)
            self.assertTrue('flow_uuid' in response.context['form'].fields)
            self.assertTrue('title' in response.context['form'].fields)
            self.assertTrue('category' in response.context['form'].fields)
            self.assertTrue('category_image' in response.context['form'].fields)
            self.assertTrue('loc' in response.context['form'].fields)

            self.assertEquals(len(response.context['form'].fields['flow_uuid'].choices), 1)
            self.assertEquals(response.context['form'].fields['flow_uuid'].choices[0][0], 'uuid-25')
            self.assertEquals(response.context['form'].fields['flow_uuid'].choices[0][1], 'Flow 1')

            response = self.client.post(create_url, dict(), SERVER_NAME='uganda.ureport.io')
            self.assertTrue(response.context['form'].errors)

            self.assertEquals(len(response.context['form'].errors), 3)
            self.assertTrue('title' in response.context['form'].errors)
            self.assertTrue('category' in response.context['form'].errors)
            self.assertTrue('flow_uuid' in response.context['form'].errors)
            self.assertFalse(Poll.objects.all())

            post_data = dict(title='Poll 1', category=self.health_uganda.pk, flow_uuid="uuid-25")

            response = self.client.post(create_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
            self.assertTrue(Poll.objects.all())

            poll = Poll.objects.get()
            self.assertEquals(poll.title, 'Poll 1')
            self.assertEquals(poll.flow_uuid, "uuid-25")
            self.assertEquals(poll.org, self.uganda)

            self.assertEquals(response.request['PATH_INFO'], reverse('polls.poll_questions', args=[poll.pk]))

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
    def test_update_poll(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2 = Poll.objects.create(flow_uuid="uuid-2",
                                    title="Poll 2",
                                    category=self.education_nigeria,
                                    is_featured=True,
                                    org=self.nigeria,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        uganda_update_url = reverse('polls.poll_update', args=[poll1.pk])
        nigeria_update_url = reverse('polls.poll_update', args=[poll2.pk])

        response = self.client.get(uganda_update_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_update_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_update_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        with patch('dash.orgs.models.Org.get_flows') as mock:
            flows_cached = dict()
            flows_cached['uuid-25'] = dict(runs=300, completed_runs=120, name='Flow 1', uuid='uuid-25', participants=300,
                                           labels="", archived=False, created_on="2015-04-08T12:48:44.320Z",
                                           rulesets=[dict(uuid='uuid-8435', id=8435, response_type="C",
                                                          label='Does your community have power')])

            mock.return_value = flows_cached

            response = self.client.get(uganda_update_url, SERVER_NAME='uganda.ureport.io')
            self.assertEquals(response.status_code, 200)
            self.assertTrue('form' in response.context)

            self.assertEquals(len(response.context['form'].fields), 7)
            self.assertTrue('is_active' in response.context['form'].fields)
            self.assertTrue('is_featured' in response.context['form'].fields)
            self.assertTrue('flow_uuid' in response.context['form'].fields)
            self.assertTrue('title' in response.context['form'].fields)
            self.assertTrue('category' in response.context['form'].fields)
            self.assertTrue('category_image' in response.context['form'].fields)
            self.assertTrue('loc' in response.context['form'].fields)

            response = self.client.post(uganda_update_url, dict(), SERVER_NAME='uganda.ureport.io')
            self.assertTrue('form' in response.context)
            self.assertTrue(response.context['form'].errors)
            self.assertEquals(len(response.context['form'].errors), 3)
            self.assertTrue('title' in response.context['form'].errors)
            self.assertTrue('category' in response.context['form'].errors)
            self.assertTrue('flow_uuid' in response.context['form'].errors)

            post_data = dict(title='title updated', category=self.health_uganda.pk, flow_uuid="uuid-25", is_featured=False)
            response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
            self.assertFalse('form' in response.context)
            updated_poll = Poll.objects.get(pk=poll1.pk)
            self.assertEquals(updated_poll.title, 'title updated')
            self.assertFalse(updated_poll.is_featured)

            self.assertEquals(response.request['PATH_INFO'], reverse('polls.poll_list'))

    def test_list_poll(self):
        list_url = reverse('polls.poll_list')
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2 = Poll.objects.create(flow_uuid="uuid-2",
                                    title="Poll 2",
                                    category=self.education_nigeria,
                                    is_featured=True,
                                    org=self.nigeria,
                                    created_by=self.admin,
                                    modified_by=self.admin)
        response = self.client.get(list_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(list_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(response.context['object_list']), 1)
        self.assertFalse(poll2 in response.context['object_list'])
        self.assertTrue(poll1 in response.context['object_list'])

        self.assertTrue(reverse('polls.poll_questions',args=[poll1.pk]) in response.content)
        self.assertTrue(reverse('polls.poll_responses',args=[poll1.pk]) in response.content)
        self.assertTrue(reverse('polls.poll_images',args=[poll1.pk]) in response.content)

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
    def test_questions_poll(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2 = Poll.objects.create(flow_uuid="uuid-2",
                                    title="Poll 2",
                                    category=self.education_nigeria,
                                    is_featured=True,
                                    org=self.nigeria,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        uganda_questions_url = reverse('polls.poll_questions', args=[poll1.pk])
        nigeria_questions_url = reverse('polls.poll_questions', args=[poll2.pk])

        response = self.client.get(uganda_questions_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_questions_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_questions_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        with patch('ureport.polls.models.Poll.get_flow') as mock:
            mock.return_value = dict(runs=300, completed_runs=120, name='Flow 1', uuid='uuid-25', participants=300,
                                     labels="", archived=False, created_on="2015-04-08T12:48:44.320Z",
                                     rulesets=[dict(uuid='uuid-8435', id=8435, response_type="C",
                                                    label='Does your community have power')])

            response = self.client.get(uganda_questions_url, SERVER_NAME='uganda.ureport.io')
            self.assertEquals(response.status_code, 200)
            self.assertTrue('form' in response.context)
            self.assertEquals(len(response.context['form'].fields), 2)
            self.assertTrue('ruleset_uuid-8435_include' in response.context['form'].fields)
            self.assertTrue('ruleset_uuid-8435_title' in response.context['form'].fields)
            self.assertEquals(response.context['form'].fields['ruleset_uuid-8435_title'].initial, 'Does your community have power')

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        with patch('ureport.polls.models.Poll.get_flow') as mock:
            mock.return_value = dict(runs=300, completed_runs=120, name='Flow 1', uuid='uuid-25', participants=300,
                                     labels="", archived=False, created_on="2015-04-08T12:48:44.320Z",
                                     rulesets=[dict(uuid='uuid-8435', id=8435, response_type="C",
                                                    label='Does your community have power'),
                                               dict(uuid='some-uuid', id=101, response_type="C",
                                                    label='label on rapid pro')])

            with patch('ureport.polls.models.Poll.fetch_poll_results_task') as mock_fetch_poll_results_task:
                mock_fetch_poll_results_task.return_value = "Fetched"

                response = self.client.get(uganda_questions_url, SERVER_NAME='uganda.ureport.io')
                self.assertEquals(response.status_code, 200)
                self.assertTrue('form' in response.context)
                self.assertEquals(len(response.context['form'].fields), 4)
                self.assertTrue('ruleset_uuid-8435_include' in response.context['form'].fields)
                self.assertTrue('ruleset_uuid-8435_title' in response.context['form'].fields)
                self.assertEquals(response.context['form'].fields['ruleset_uuid-8435_title'].initial, 'Does your community have power')
                self.assertTrue('ruleset_some-uuid_include' in response.context['form'].fields)
                self.assertTrue('ruleset_some-uuid_title' in response.context['form'].fields)
                self.assertEquals(response.context['form'].fields['ruleset_some-uuid_title'].initial, 'label on rapid pro')

                post_data = dict()
                response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
                self.assertTrue(response.context['form'].errors)
                self.assertTrue(response.context['form'].errors['__all__'][0], 'You must include at least one poll question.')

                post_data = dict()
                post_data['ruleset_uuid-8435_include'] = True
                response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
                self.assertTrue(response.context['form'].errors)
                self.assertTrue(response.context['form'].errors['__all__'][0], "You must include a title for every included question.")

                post_data = dict()
                post_data['ruleset_uuid-8435_include'] = True
                post_data['ruleset_uuid-8435_title'] = "hello " * 50
                response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
                self.assertTrue(response.context['form'].errors)
                self.assertTrue(response.context['form'].errors['__all__'][0], "Title too long. The max limit is 255 characters for each title")

                post_data = dict()
                post_data['ruleset_uuid-8435_include'] = True
                post_data['ruleset_uuid-8435_title'] = "have electricity access"
                response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
                self.assertTrue(PollQuestion.objects.filter(poll=poll1))

                poll_question = PollQuestion.objects.filter(poll=poll1, ruleset_uuid="uuid-8435")[0]
                self.assertEquals(poll_question.title, 'have electricity access')

                self.assertEquals(response.request['PATH_INFO'], reverse('polls.poll_images', args=[poll1.pk]))

                mock_fetch_poll_results_task.assert_called_once_with(poll1)

                post_data = dict()
                post_data['ruleset_uuid-8435_include'] = True
                post_data['ruleset_uuid-8435_title'] = "electricity network coverage"
                response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')

                self.assertTrue(PollQuestion.objects.filter(poll=poll1))

                poll_question = PollQuestion.objects.filter(poll=poll1)[0]
                self.assertEquals(poll_question.title, 'electricity network coverage')
                self.assertFalse(PollQuestion.objects.filter(pk=poll1_question.pk))

                with patch('ureport.polls.models.Poll.clear_brick_polls_cache') as mock:
                    mock.return_value = 'Cache cleared'

                    post_data = dict()
                    post_data['ruleset_uuid-8435_include'] = True
                    post_data['ruleset_uuid-8435_title'] = "electricity network coverage"
                    response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')

                    mock.assert_called_once_with(poll1.org)

    def test_images_poll(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2 = Poll.objects.create(flow_uuid="uuid-2",
                                    title="Poll 2",
                                    category=self.education_nigeria,
                                    is_featured=True,
                                    org=self.nigeria,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        uganda_poll_images_url = reverse('polls.poll_images', args=[poll1.pk])
        nigeria_poll_images_url = reverse('polls.poll_images', args=[poll2.pk])

        response = self.client.get(uganda_poll_images_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_poll_images_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_poll_images_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_poll_images_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)
        self.assertEquals(len(response.context['form'].fields), 3)
        for field in response.context['form'].fields:
            self.assertFalse(response.context['form'].fields[field].initial)

        self.assertFalse(PollImage.objects.filter(poll=poll1))

        upload = open("test-data/image.jpg", "r")
        post_data = dict(image_1=upload)
        response = self.client.post(uganda_poll_images_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertTrue(PollImage.objects.filter(poll=poll1))
        self.assertEquals(PollImage.objects.filter(poll=poll1).count(), 1)

        response = self.client.get(uganda_poll_images_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(len(response.context['form'].fields), 3)
        self.assertTrue(response.context['form'].fields['image_1'].initial)

        upload = open("test-data/image.jpg", "r")
        post_data = dict(image_1=upload)
        response = self.client.post(uganda_poll_images_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertTrue(PollImage.objects.filter(poll=poll1))
        self.assertEquals(PollImage.objects.filter(poll=poll1).count(), 1)

        self.assertEquals(response.request['PATH_INFO'], reverse('polls.poll_responses', args=[poll1.pk]))

    def test_responses_poll(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2 = Poll.objects.create(flow_uuid="uuid-2",
                                    title="Poll 2",
                                    category=self.education_nigeria,
                                    is_featured=True,
                                    org=self.nigeria,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        uganda_poll_responses_url = reverse('polls.poll_responses', args=[poll1.pk])
        nigeria_poll_responses_url = reverse('polls.poll_responses', args=[poll2.pk])

        response = self.client.get(uganda_poll_responses_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_poll_responses_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_poll_responses_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_poll_responses_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)
        self.assertEquals(len(response.context['form'].fields), 9)
        for field in response.context['form'].fields.values():
            self.assertFalse(field.initial)

        response = self.client.post(uganda_poll_responses_url, dict(), follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertFalse('form' in response.context)
        self.assertFalse(FeaturedResponse.objects.filter(poll=poll1))

        post_data = dict(reporter_1='Pink Floyd', location_1="Youtube Stream", message_1="Just give me a reason")

        response = self.client.post(uganda_poll_responses_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertFalse('form' in response.context)
        self.assertTrue(FeaturedResponse.objects.filter(poll=poll1))
        featured_response = FeaturedResponse.objects.filter(poll=poll1)[0]
        self.assertEquals(featured_response.message, "Just give me a reason")
        self.assertEquals(featured_response.location, "Youtube Stream")
        self.assertEquals(featured_response.reporter, "Pink Floyd")

        response = self.client.get(uganda_poll_responses_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)
        self.assertEquals(len(response.context['form'].fields), 9)
        self.assertEquals(response.context['form'].fields['reporter_1'].initial, 'Pink Floyd')
        self.assertEquals(response.context['form'].fields['location_1'].initial, 'Youtube Stream')
        self.assertEquals(response.context['form'].fields['message_1'].initial, 'Just give me a reason')

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
    def test_templatetags(self):
        from ureport.polls.templatetags.ureport import reporter_count, config, org_color, transparency, show_org_flags
        from ureport.polls.templatetags.ureport import org_host_link

        self.assertIsNone(reporter_count(None))
        self.assertEquals(reporter_count(self.uganda), 0)
        self.uganda.set_config('reporter_group', 'group_name')
        with patch("dash.orgs.models.Org.get_reporter_group") as mock:
            mock.return_value = dict(uuid="uuid-group", name="group_name", size=120)
            self.assertEquals(reporter_count(self.uganda), 120)

        with patch('dash.orgs.models.Org.get_config') as mock:
            mock.return_value = 'Done'

            self.assertIsNone(config(None, 'field_name'))
            self.assertEquals(config(self.uganda, 'field_name'), 'Done')
            mock.assert_called_with('field_name')

        self.assertIsNone(org_color(None, 1))
        self.assertEquals(org_color(self.uganda, 0), '#FFFF00')
        self.assertEquals(org_color(self.uganda, 1), '#1F49BF')
        self.assertEquals(org_color(self.uganda, 2), '#FFFF00')
        self.assertEquals(org_color(self.uganda, 3), '#1F49BF')

        self.uganda.set_config('primary_color', '#aaaaaa')

        self.assertEquals(org_color(self.uganda, 0), '#FFFF00')
        self.assertEquals(org_color(self.uganda, 1), '#1F49BF')
        self.assertEquals(org_color(self.uganda, 2), '#FFFF00')
        self.assertEquals(org_color(self.uganda, 3), '#1F49BF')

        self.uganda.set_config('secondary_color', '#bbbbbb')

        self.assertEquals(org_color(self.uganda, 0), '#aaaaaa')
        self.assertEquals(org_color(self.uganda, 1), '#bbbbbb')
        self.assertEquals(org_color(self.uganda, 2), '#aaaaaa')
        self.assertEquals(org_color(self.uganda, 3), '#bbbbbb')

        self.uganda.set_config('colors', '#cccccc, #dddddd, #eeeeee, #111111, #222222, #333333, #444444')

        self.assertEquals(org_color(self.uganda, 0), '#cccccc')
        self.assertEquals(org_color(self.uganda, 1), '#dddddd')
        self.assertEquals(org_color(self.uganda, 2), '#eeeeee')
        self.assertEquals(org_color(self.uganda, 3), '#111111')
        self.assertEquals(org_color(self.uganda, 4), '#222222')
        self.assertEquals(org_color(self.uganda, 5), '#333333')
        self.assertEquals(org_color(self.uganda, 6), '#444444')
        self.assertEquals(org_color(self.uganda, 7), '#cccccc')
        self.assertEquals(org_color(self.uganda, 8), '#dddddd')
        self.assertEquals(org_color(self.uganda, 9), '#eeeeee')
        self.assertEquals(org_color(self.uganda, 10), '#111111')
        self.assertEquals(org_color(self.uganda, 11), '#222222')

        self.assertIsNone(transparency(None, 0.8))
        self.assertEquals(transparency('#808080', 0.7), "rgba(128, 128, 128, 0.7)")

        with self.assertRaises(TemplateSyntaxError):
            transparency('#abc', 0.5)

        with patch('ureport.polls.templatetags.ureport.get_linked_orgs') as mock_get_linked_orgs:
            mock_get_linked_orgs.return_value = ['linked_org']

            request = Mock(spec=HttpRequest)
            request.user = User.objects.get(pk=1)

            with patch('django.contrib.auth.models.User.is_authenticated') as mock_authenticated:
                mock_authenticated.return_value = True

                show_org_flags(dict(is_iorg=True, request=request))
                mock_get_linked_orgs.assert_called_with(True)

                mock_authenticated.return_value = False
                show_org_flags(dict(is_iorg=True, request=request))
                mock_get_linked_orgs.assert_called_with(False)

        request = Mock(spec=HttpRequest)
        request.user = User.objects.get(pk=1)

        with patch('django.contrib.auth.models.User.is_authenticated') as mock_authenticated:
            mock_authenticated.return_value = True

            self.assertEqual(org_host_link(dict(request=request)), 'https://ureport.io')

            request.org = self.nigeria
            self.assertEqual(org_host_link(dict(request=request)), 'http://nigeria.ureport.io')

            with self.settings(SESSION_COOKIE_SECURE=True):
                self.assertEqual(org_host_link(dict(request=request)), 'https://nigeria.ureport.io')

            self.nigeria.domain = "ureport.ng"
            self.nigeria.save()

            self.assertEqual(org_host_link(dict(request=request)), 'http://nigeria.ureport.io')

            with self.settings(SESSION_COOKIE_SECURE=True):
                self.assertEqual(org_host_link(dict(request=request)), 'https://nigeria.ureport.io')


class PollQuestionTest(DashTest):
    def setUp(self):
        super(PollQuestionTest, self).setUp()
        self.uganda = self.create_org('uganda', self.admin)
        self.nigeria = self.create_org('nigeria', self.admin)

        self.health_uganda = Category.objects.create(org=self.uganda,
                                                     name="Health",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

    def test_poll_question_model(self):
        poll1 = Poll.objects.create(flow_uuid="uuid-1",
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    is_featured=True,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll_question1 = PollQuestion.objects.create(poll=poll1,
                                                     title="question 1",
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.assertEquals(unicode(poll_question1), 'question 1')
        fetched_results = [dict(open_ended=False, set=3462, unset=3694, categories=[dict(count=2210, label='Yes'),
                                                                                    dict(count=1252, label='No')],
                                    label='All')]

        self.uganda.set_config("state_label", "LGA")
        self.uganda.set_config("district_label", "District")


        with patch('dash.orgs.models.TembaClient.get_results') as mock:
            mock.return_value = Result.deserialize_list(fetched_results)

            with patch('django.core.cache.cache.set') as cache_set_mock:
                cache_set_mock.return_value = "Set"

                with patch("ureport.polls.models.datetime_to_ms") as mock_datetime_ms:
                    mock_datetime_ms.return_value = 500

                    poll_question1.fetch_results()
                    key = CACHE_POLL_RESULTS_KEY % (poll_question1.poll.org.pk, poll_question1.poll.pk, poll_question1.pk)

                    cache_set_mock.assert_called_with(key,
                                                      {'time': 500, 'results':fetched_results},
                                                      UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME)
                    mock.assert_called_with(poll_question1.ruleset_uuid, segment=None)

                    poll_question1.fetch_results(segment=dict(location='State'))

                    segment = json.dumps(dict(location='LGA'))
                    key += ":" + slugify(unicode(segment))

                    cache_set_mock.assert_called_with(key,
                                                      {'time': 500, 'results':fetched_results},
                                                      UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME)

                    mock.assert_called_with(poll_question1.ruleset_uuid, segment=segment)

        with patch('ureport.polls.models.PollQuestion.fetch_results') as mock:
            mock.return_value = None

            poll_question1.get_results()
            self.assertFalse(mock.called)

            poll_question1.get_results(segment=dict(location='State'))
            self.assertFalse(mock.called)

            with patch('django.core.cache.cache.get') as cache_get_mock:
                cache_get_mock.return_value = dict(results="RESULTS", time=500)

                poll_question1.get_results(segment=dict(location='District'))
                self.assertFalse(mock.called)

            with patch('django.core.cache.cache.get') as cache_get_mock:
                cache_get_mock.return_value = None

                poll_question1.get_results(segment=dict(location='District'))
                mock.assert_called_with(segment=dict(location='District'))

        with patch('ureport.polls.models.PollQuestion.get_results') as mock:
            mock.return_value = fetched_results

            self.assertFalse(poll_question1.is_open_ended())
            mock.assert_called_with()

            self.assertEquals(poll_question1.get_responded(), 3462)
            mock.assert_called_with()

            self.assertEquals(poll_question1.get_polled(), 3462 + 3694)
            mock.assert_called_with()

            self.assertEquals(poll_question1.get_words(), [dict(count=2210, label='Yes'), dict(count=1252, label='No')])
            mock.assert_called_with()

            self.assertEquals(poll_question1.get_response_percentage(), "48%")

    def test_tasks(self):
        self.org = self.create_org("burundi", self.admin)

        self.education = Category.objects.create(org=self.org,
                                                 name="Education",
                                                 created_by=self.admin,
                                                 modified_by=self.admin)

        self.poll = Poll.objects.create(flow_uuid="uuid-1",
                                        title="Poll 1",
                                        category=self.education,
                                        org=self.org,
                                        created_by=self.admin,
                                        modified_by=self.admin)

        with self.settings(CACHES={'default': {'BACKEND': 'redis_cache.cache.RedisCache',
                                               'LOCATION': '127.0.0.1:6379:1',
                                               'OPTIONS': {'CLIENT_CLASS': 'redis_cache.client.DefaultClient'}
                                               }}):

            with patch('ureport.polls.models.Poll.fetch_poll_results') as mock_fetch_poll_results:
                mock_fetch_poll_results.return_value = 'FETCHED'

                fetch_poll(self.poll.id)
                mock_fetch_poll_results.assert_called_once_with()

            with patch('ureport.polls.tasks.fetch_main_poll_results') as mock_fetch_main_poll_results:
                mock_fetch_main_poll_results.return_value = 'FETCHED'

                refresh_main_poll(self.org.pk)
                mock_fetch_main_poll_results.assert_called_once_with(self.org)

            with patch('ureport.polls.tasks.fetch_brick_polls_results') as mock_fetch_brick_polls_results:
                mock_fetch_brick_polls_results.return_value = 'FETCHED'

                refresh_brick_polls(self.org.pk)
                mock_fetch_brick_polls_results.assert_called_once_with(self.org)

            with patch('ureport.polls.tasks.fetch_other_polls_results') as mock_fetch_other_polls_results:
                mock_fetch_other_polls_results.return_value = 'FETCHED'

                refresh_other_polls(self.org.pk)
                mock_fetch_other_polls_results.assert_called_once_with(self.org)

            with patch('ureport.polls.tasks.fetch_org_graph_data') as mock_fetch_org_graph_data:
                mock_fetch_org_graph_data.return_value = 'FETCHED'

                refresh_org_graphs_data(self.org.pk)
                mock_fetch_org_graph_data.assert_called_once_with(self.org)

            with patch('ureport.polls.tasks.fetch_flows') as mock_fetch_flows:
                mock_fetch_flows.return_value = 'FETCHED'

                refresh_org_flows(self.org.pk)
                mock_fetch_flows.assert_called_once_with(self.org)

            with patch('ureport.polls.tasks.fetch_reporter_group') as mock_fetch_reporter_group:
                mock_fetch_reporter_group.return_value = 'FETCHED'

                with patch('ureport.polls.tasks.fetch_old_sites_count') as mock_fetch_old_sites_count:
                    mock_fetch_old_sites_count.return_value = 'FETCHED'

                    refresh_org_reporters(self.org.pk)
                    mock_fetch_reporter_group.assert_called_once_with(self.org)
                    mock_fetch_old_sites_count.assert_called_once_with()
