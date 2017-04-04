import json

from datetime import timedelta, datetime

import pytz
import six
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.http import HttpRequest
from django.template import TemplateSyntaxError
from django.test import TestCase
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import ugettext_lazy as _

import pycountry

from mock import patch, Mock
from dash.categories.models import Category, CategoryImage
from dash.categories.fields import CategoryChoiceField
from smartmin.csv_imports.models import ImportTask
from temba_client.v1.types import Result, Flow, Group

from dash.orgs.models import TaskState
from ureport.polls.models import Poll, PollQuestion, FeaturedResponse, PollImage, CACHE_POLL_RESULTS_KEY
from ureport.polls.models import PollResultsCounter, PollResult, PollResponseCategory
from ureport.polls.models import UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME
from ureport.polls.tasks import refresh_org_flows, pull_results_brick_polls, pull_results_other_polls, rebuild_counts, \
    pull_results_recent_other_polls
from ureport.polls.tasks import recheck_poll_flow_data, pull_results_main_poll, backfill_poll_results, pull_refresh
from ureport.polls.tasks import fetch_old_sites_count, update_results_age_gender, update_or_create_questions
from ureport.polls.templatetags.ureport import question_segmented_results
from ureport.tests import UreportTest, MockTembaClient
from ureport.utils import json_date_to_datetime, datetime_to_json_date


class PollTest(UreportTest):
    def setUp(self):
        super(PollTest, self).setUp()
        self.health_uganda = Category.objects.create(org=self.uganda,
                                                     name="Health",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

    def test_prepare_fields(self):

        with self.assertRaises(Exception):
            Poll.prepare_fields(dict())

        with self.assertRaises(Exception):
            Poll.prepare_fields(dict(), dict())

        self.assertEqual(dict(org=self.uganda, created_by=self.superuser),
                         Poll.prepare_fields(dict(), dict(org_id=self.uganda.pk), user=self.superuser))

    def test_poll_create_instance(self):

        self.assertFalse(Poll.objects.filter(org=self.uganda))
        self.assertFalse(PollQuestion.objects.filter(poll__org=self.uganda))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict())

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda, created_by=self.superuser))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Sports'))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Sports',
                                      uuid='uuid-flow-1'))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Sports',
                                      uuid='uuid-flow-1', name='Flow 1'))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Sports',
                                      uuid='uuid-flow-1', name='Flow 1', created_on='2010-07-07T14:24:12.753000Z'))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Sports',
                                      uuid='uuid-flow-1', name='Sport Activities', created_on='2010-07-07T14:24:12.753000Z',
                                      ruleset_uuid='question-uuid-1'))

        poll = Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Sports',
                                         uuid='uuid-flow-1', name='Sport Activities',
                                         created_on='2010-07-07T14:24:12.753000Z', ruleset_uuid='question-uuid-1',
                                         question='Did you participate in #CarFreeDay?'))

        self.assertTrue(Poll.objects.filter(org=self.uganda, flow_uuid='uuid-flow-1'))
        self.assertTrue(poll in Poll.objects.filter(org=self.uganda, flow_uuid='uuid-flow-1'))
        self.assertTrue(PollQuestion.objects.filter(poll__org=self.uganda, ruleset_uuid='question-uuid-1',
                                                    title='Did you participate in #CarFreeDay?'))

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 1)

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 1)

        # same row does not add duplicates
        Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Sports',
                                  uuid='uuid-flow-1', name='Sport Activities Here', created_on='2010-07-07T14:24:12.753000Z',
                                  ruleset_uuid='question-uuid-1', question='Did you participate in #CarFreeDay?'))

        self.assertTrue(Poll.objects.filter(org=self.uganda, flow_uuid='uuid-flow-1'))
        self.assertTrue(PollQuestion.objects.filter(poll__org=self.uganda, ruleset_uuid='question-uuid-1',
                                                    title='Did you participate in #CarFreeDay?'))

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 1)
        poll = Poll.objects.filter(org=self.uganda).first()
        # however update the poll title
        self.assertEqual(poll.title, "Sport Activities Here")

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 1)

        # new row add new poll and its questions
        Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Music',
                                  uuid='uuid-flow-2', name='Showbiz', created_on='2010-07-07T14:24:12.753000Z',
                                  ruleset_uuid='question-uuid-2', question='Which concert?'))

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 2)

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 2)

        # no hidden question
        self.assertFalse(PollQuestion.objects.filter(poll__org=self.uganda, is_active=False))

        # same flow without the question should add a new flow
        Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Music',
                                  uuid='uuid-flow-2', name='Sounds', created_on='2010-07-07T14:24:12.753000Z',
                                  ruleset_uuid='question-uuid-3', question='Which album?'))

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 3)

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 3)
        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda, is_active=True).count(), 3)

        # no hidden question
        self.assertFalse(PollQuestion.objects.filter(poll__org=self.uganda, is_active=False))

        poll = Poll.objects.filter(org=self.uganda, flow_uuid='uuid-flow-2').first()
        question = PollQuestion.update_or_create(self.superuser, poll, '', 'question-uuid-4', 'wait_message')
        PollQuestion.objects.filter(pk=question.pk).update(is_active=True)

        # same flow with the ruleset question existing should hide old questions without new flow
        Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category='Music',
                                  uuid='uuid-flow-2', name='Sounds', created_on='2010-07-07T14:24:12.753000Z',
                                  ruleset_uuid='question-uuid-2', question='Which album?'))

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 3)

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 4)
        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda, is_active=True).count(), 3)

        # poll other questions are hidden
        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda, is_active=False).count(), 1)
        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda, is_active=False,
                                                     ruleset_uuid='question-uuid-4').count(), 1)

    @patch('ureport.polls.models.Poll.update_or_create_questions_task')
    def test_poll_import_csv(self, mock_poll_update_or_create_questions_task):
        poll1 = self.create_poll(self.uganda, "Poll 1", "flow-uuid-1", self.health_uganda, self.admin)
        PollQuestion.objects.create(poll=poll1,
                                    title='question poll 1',
                                    ruleset_uuid='ruleset-uuid-1',
                                    created_by=self.admin,
                                    modified_by=self.admin)
        poll2 = self.create_poll(self.uganda, "Poll 2", "flow-uuid-2", self.health_uganda, self.admin)

        PollQuestion.objects.create(poll=poll2,
                                    title='question poll 2',
                                    ruleset_uuid='ruleset-uuid-2',
                                    created_by=self.admin,
                                    modified_by=self.admin)

        mock_poll_update_or_create_questions_task.side_effect = None

        import_params = dict(org_id=self.uganda.id, timezone=six.text_type(self.uganda.timezone), original_filename="polls.csv")

        task = ImportTask.objects.create(created_by=self.superuser, modified_by=self.superuser,
                                         csv_file='test_imports/polls.csv',
                                         model_class="Poll", import_params=json.dumps(import_params),
                                         import_log="", task_id="A")

        Poll.import_csv(task, log=None)

        place_poll = Poll.objects.filter(id=poll1.pk).first()
        time_poll = Poll.objects.filter(id=poll2.pk).first()

        self.assertEqual(place_poll.title, "Place poll")
        self.assertEqual(time_poll.title, "Time poll")

        mock_poll_update_or_create_questions_task.assert_called_once_with([place_poll, time_poll])

    def test_poll_import(self):
        import_url = reverse("polls.poll_import")

        response = self.client.get(import_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(import_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.superuser)

        response = self.client.get(import_url, SERVER_NAME='uganda.ureport.io')
        self.assertEqual(response.status_code, 200)

        self.assertTrue('csv_file' in response.context['form'].fields)

    @patch('ureport.polls.tasks.update_or_create_questions.delay')
    def test_poll_update_or_create_questions_task(self, mock_task_delay):
        poll1 = self.create_poll(self.uganda, "Poll 1", "flow-uuid-1", self.health_uganda, self.admin)
        poll2 = self.create_poll(self.uganda, "Poll 2", "flow-uuid-2", self.health_uganda, self.admin)

        Poll.update_or_create_questions_task([poll1, poll2])

        mock_task_delay.assert_called_once_with([poll1.pk, poll2.pk])

    def test_poll_pull_refresh(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

        pull_refresh_url = reverse('polls.poll_pull_refresh', args=[poll1.pk])

        post_data = dict(poll=poll1.pk)

        with patch('ureport.polls.models.Poll.pull_refresh_task') as mock_pull_refresh:
            mock_pull_refresh.return_value = 'Done'

            response = self.client.get(pull_refresh_url, SERVER_NAME='uganda.ureport.io')
            self.assertLoginRedirect(response)

            response = self.client.post(pull_refresh_url, post_data, SERVER_NAME='uganda.ureport.io')
            self.assertLoginRedirect(response)

            self.login(self.admin)

            response = self.client.get(pull_refresh_url, SERVER_NAME='uganda.ureport.io')
            self.assertLoginRedirect(response)

            response = self.client.post(pull_refresh_url, post_data, SERVER_NAME='uganda.ureport.io')
            self.assertLoginRedirect(response)

            self.login(self.superuser)

            with self.assertRaises(TemplateSyntaxError):
                self.client.get(pull_refresh_url, SERVER_NAME='uganda.ureport.io')

            with self.assertRaises(KeyError):
                self.client.post(pull_refresh_url, dict(), SERVER_NAME='uganda.ureport.io')

            response = self.client.post(pull_refresh_url, post_data, SERVER_NAME='uganda.ureport.io')
            self.assertEqual(response.status_code, 302)
            mock_pull_refresh.assert_called_once_with()
            mock_pull_refresh.reset_mock()

            response = self.client.post(pull_refresh_url, post_data, SERVER_NAME='uganda.ureport.io', follow=True)

            self.assertEqual(response.context['org'], self.uganda)
            self.assertEqual(response.request['PATH_INFO'], reverse('polls.poll_list'))
            self.assertTrue("Scheduled a pull refresh for poll #%d on org #%d" % (poll1.pk, poll1.org_id) in response.content)

            mock_pull_refresh.assert_called_once_with()

    @patch('ureport.polls.tasks.pull_refresh.apply_async')
    @patch('django.core.cache.cache.set')
    def test_pull_refresh_task(self, mock_cache_set, mock_pull_refresh):
        tz = pytz.timezone('Africa/Kigali')
        with patch.object(timezone, 'now', return_value=tz.localize(datetime(2015, 9, 4, 3, 4, 5, 0))):

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

            poll1.pull_refresh_task()

            now = timezone.now()
            mock_cache_set.assert_called_once_with(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (poll1.org_id,
                                                                                                   poll1.pk),
                                                   datetime_to_json_date(now.replace(tzinfo=pytz.utc)), None)

            mock_pull_refresh.assert_called_once_with((poll1.pk,), queue='sync')

    def test_get_public_polls(self):

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)
        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", self.health_uganda, self.admin, has_synced=True)

        poll3 = self.create_poll(self.nigeria, "Poll 3", "uuid-3", self.education_nigeria, self.admin, has_synced=True)

        self.assertTrue(Poll.get_public_polls(self.uganda))
        self.assertEqual(Poll.get_public_polls(self.uganda).count(), 1)
        self.assertTrue(poll2 in Poll.get_public_polls(self.uganda))

        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertFalse(Poll.get_public_polls(self.uganda))

        self.health_uganda.is_active = True
        self.health_uganda.save()

        poll2.is_active = False
        poll2.save()

        self.assertFalse(Poll.get_public_polls(self.uganda))

    def test_poll_get_main_poll(self):
        self.assertIsNone(Poll.get_main_poll(self.uganda))
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, has_synced=True)

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

        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", self.health_uganda, self.admin, has_synced=True)

        poll2_question = PollQuestion.objects.create(poll=poll2,
                                                     title='question poll 2',
                                                     ruleset_uuid='uuid-202',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.assertEquals(Poll.get_main_poll(self.uganda), poll2)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin, has_synced=True)

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

    @patch('django.core.cache.cache.get')
    def test_brick_polls(self, mock_cache_get):
        mock_cache_get.return_value = None
        self.assertFalse(Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True, has_synced=True)

        self.assertFalse(Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid='uuid-101',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.assertFalse(Poll.get_brick_polls(self.uganda))
        self.assertFalse(Poll.get_brick_polls(self.nigeria))

        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", self.health_uganda, self.admin, has_synced=True)

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

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin, has_synced=True)

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

    @patch('django.core.cache.cache.get')
    def test_get_other_polls(self, mock_cache_get):
        mock_cache_get.return_value = None

        polls = []
        for i in range(10):
            poll = self.create_poll(self.uganda, "Poll %s" % i, "uuid-%s" % i, self.health_uganda,
                                    self.admin, featured=True, has_synced=True)
            PollQuestion.objects.create(poll=poll, title='question poll %s' % i, ruleset_uuid='uuid-10-%s' % i,
                                        created_by=self.admin, modified_by=self.admin)

            polls.append(poll)

        self.assertTrue(Poll.get_other_polls(self.uganda))
        self.assertEqual(list(Poll.get_other_polls(self.uganda)), [polls[3], polls[2], polls[1], polls[0]])

    @patch('django.core.cache.cache.get')
    def test_get_recent_other_polls(self, mock_cache_get):
        mock_cache_get.return_value = None

        polls = []
        for i in range(10):
            poll = self.create_poll(self.uganda, "Poll %s" % i, "uuid-%s" % i, self.health_uganda,
                                    self.admin, featured=True, has_synced=True)
            PollQuestion.objects.create(poll=poll, title='question poll %s' % i, ruleset_uuid='uuid-10-%s' % i,
                                        created_by=self.admin, modified_by=self.admin)

            polls.append(poll)

        self.assertTrue(Poll.get_recent_other_polls(self.uganda))
        self.assertEqual(list(Poll.get_recent_other_polls(self.uganda)), [polls[3], polls[2], polls[1], polls[0]])

        now = timezone.now()
        a_month_ago = now - timedelta(days=30)

        Poll.objects.filter(pk__in=[polls[0].pk, polls[1].pk]).update(created_on=a_month_ago)

        self.assertTrue(Poll.get_recent_other_polls(self.uganda))
        self.assertEqual(list(Poll.get_recent_other_polls(self.uganda)), [polls[3], polls[2]])

    def test_get_flow(self):
        with patch('dash.orgs.models.Org.get_flows') as mock:
            mock.return_value = {'uuid-1': "Flow"}

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

            self.assertEquals(poll1.get_flow(), 'Flow')
            mock.assert_called_once_with()

    @patch('django.core.cache.cache.get')
    def test_most_responded_regions(self, mock_cache_get):
        mock_cache_get.return_value = None

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        with patch('ureport.polls.models.PollQuestion.get_results') as mock:
            mock.return_value = [{u'open_ended': False, u'label': u'Abia', u'set': 338, u'unset': 36, u'boundary': u'R3713501', u'categories': [{u'count': 80, u'label': u'Yes'}, {u'count': 258, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Adamawa', u'set': 84, u'unset': 7, u'boundary': u'R3720358', u'categories': [{u'count': 41, u'label': u'Yes'}, {u'count': 43, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Akwa Ibom', u'set': 149, u'unset': 14, u'boundary': u'R3715359', u'categories': [{u'count': 41, u'label': u'Yes'}, {u'count': 108, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Anambra', u'set': 319, u'unset': 50, u'boundary': u'R3715505', u'categories': [{u'count': 81, u'label': u'Yes'}, {u'count': 238, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Bauchi', u'set': 59, u'unset': 5, u'boundary': u'R3722233', u'categories': [{u'count': 20, u'label': u'Yes'}, {u'count': 39, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Bayelsa', u'set': 102, u'unset': 11, u'boundary': u'R3715844', u'categories': [{u'count': 26, u'label': u'Yes'}, {u'count': 76, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Benue', u'set': 267, u'unset': 27, u'boundary': u'R3716076', u'categories': [{u'count': 115, u'label': u'Yes'}, {u'count': 152, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Borno', u'set': 76, u'unset': 5, u'boundary': u'R3721167', u'categories': [{u'count': 16, u'label': u'Yes'}, {u'count': 60, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Cross River', u'set': 120, u'unset': 17, u'boundary': u'R3716250', u'categories': [{u'count': 29, u'label': u'Yes'}, {u'count': 91, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Delta', u'set': 168, u'unset': 22, u'boundary': u'R3716950', u'categories': [{u'count': 39, u'label': u'Yes'}, {u'count': 129, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Ebonyi', u'set': 134, u'unset': 14, u'boundary': u'R3717071', u'categories': [{u'count': 24, u'label': u'Yes'}, {u'count': 110, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Edo', u'set': 193, u'unset': 17, u'boundary': u'R3717119', u'categories': [{u'count': 50, u'label': u'Yes'}, {u'count': 143, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Ekiti', u'set': 151, u'unset': 22, u'boundary': u'R3717154', u'categories': [{u'count': 27, u'label': u'Yes'}, {u'count': 124, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Enugu', u'set': 291, u'unset': 37, u'boundary': u'R3717212', u'categories': [{u'count': 109, u'label': u'Yes'}, {u'count': 182, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Federal Capital Territory', u'set': 940, u'unset': 87, u'boundary': u'R3717259', u'categories': [{u'count': 328, u'label': u'Yes'}, {u'count': 612, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Gombe', u'set': 73, u'unset': 7, u'boundary': u'R3720422', u'categories': [{u'count': 26, u'label': u'Yes'}, {u'count': 47, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Imo', u'set': 233, u'unset': 14, u'boundary': u'R3717825', u'categories': [{u'count': 50, u'label': u'Yes'}, {u'count': 183, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Jigawa', u'set': 69, u'unset': 5, u'boundary': u'R3703236', u'categories': [{u'count': 26, u'label': u'Yes'}, {u'count': 43, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Kaduna', u'set': 291, u'unset': 34, u'boundary': u'R3709353', u'categories': [{u'count': 121, u'label': u'Yes'}, {u'count': 170, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Kano', u'set': 222, u'unset': 23, u'boundary': u'R3710302', u'categories': [{u'count': 79, u'label': u'Yes'}, {u'count': 143, u'label': u'No'}]},
                                 {u'open_ended': False, u'label': u'Katsina', u'set': 293, u'unset': 23, u'boundary': u'R3711481', u'categories': [{u'count': 105, u'label': u'Yes'}, {u'count': 188, u'label': u'No'}]}]

            results = [{'percent': 91, 'boundary': u'Federal Capital Territory', 'total': 1027, 'type': u'best', 'responded': 940},
                       {'percent': 90, 'boundary': u'Abia', 'total': 374, 'type': u'best', 'responded': 338},
                       {'percent': 86, 'boundary': u'Anambra', 'total': 369, 'type': u'best', 'responded': 319},
                       {'percent': 92, 'boundary': u'Katsina', 'total': 316, 'type': u'best', 'responded': 293},
                       {'percent': 89, 'boundary': u'Kaduna', 'total': 325, 'type': u'best', 'responded': 291}]

            self.assertEquals(poll1.most_responded_regions(), results)
            mock.assert_called_once_with(segment=dict(location="State"))
            mock.reset_mock()

            with patch('ureport.polls.models.PollQuestion.is_open_ended') as mock_open_ended:
                mock_open_ended.return_value = True

                self.assertEquals(poll1.most_responded_regions(), results)
                mock.assert_called_once_with(segment=dict(location="State"))

        with patch('ureport.polls.models.PollQuestion.get_results') as mock:
            mock.return_value = None

            results = []

            self.assertEquals(poll1.most_responded_regions(), results)
            mock.assert_called_once_with(segment=dict(location="State"))

    def test_get_featured_responses(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertFalse(poll1.get_featured_responses())

        featured_response1 = FeaturedResponse.objects.create(poll=poll1,
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
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEquals(poll1.runs(), "----")

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        with patch('ureport.polls.models.PollQuestion.get_polled') as mock:
            mock.return_value = 100

            self.assertEquals(poll1.runs(), 100)
            mock.assert_called_with()

    def test_responded_runs(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEquals(poll1.responded_runs(), "---")

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        with patch('ureport.polls.models.PollQuestion.get_responded') as mock:
            mock.return_value = 40

            self.assertEquals(poll1.responded_runs(), 40)
            mock.assert_called_once_with()

    def test_response_percentage(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEquals(poll1.response_percentage(), "---")

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        with patch('ureport.polls.models.PollQuestion.get_response_percentage') as mock_response_percentage:
            mock_response_percentage.return_value = "40%"

            self.assertEquals(poll1.response_percentage(), "40%")
            mock_response_percentage.assert_called_with()

    def test_get_featured_images(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

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

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

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

    @patch('dash.orgs.models.TembaClient2', MockTembaClient)
    def test_create_poll(self):
        create_url = reverse('polls.poll_create')

        response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        with patch('dash.orgs.models.Org.get_flows') as mock_get_flows:
            flows_cached = dict()
            flows_cached['uuid-25'] = dict(runs=300, completed_runs=120, name='Flow 1', uuid='uuid-25',
                                           participants=None, labels="", archived=False,
                                           created_on="2015-04-08T08:30:40.000Z", date_hint="2015-04-08",
                                           rulesets=[dict(uuid='uuid-8435', id=8435, response_type="C",
                                                          label='Does your community have power')])

            mock_get_flows.return_value = flows_cached

            self.login(self.admin)
            response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
            self.assertEquals(response.status_code, 200)
            self.assertTrue('form' in response.context)

            self.assertEquals(len(response.context['form'].fields), 6)
            self.assertTrue('is_featured' in response.context['form'].fields)
            self.assertTrue('flow_uuid' in response.context['form'].fields)
            self.assertTrue('title' in response.context['form'].fields)
            self.assertTrue('category' in response.context['form'].fields)
            self.assertIsInstance(response.context['form'].fields['category'].choices.field, CategoryChoiceField)
            self.assertEquals(list(response.context['form'].fields['category'].choices),
                              [('', '---------'),
                              (self.health_uganda.pk, 'uganda - Health')])
            self.assertTrue('category_image' in response.context['form'].fields)
            self.assertTrue('loc' in response.context['form'].fields)

            self.assertEquals(len(response.context['form'].fields['flow_uuid'].choices), 1)
            self.assertEquals(response.context['form'].fields['flow_uuid'].choices[0][0], 'uuid-25')
            self.assertEquals(response.context['form'].fields['flow_uuid'].choices[0][1], 'Flow 1 (2015-04-08)')

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
            self.assertEqual(poll.poll_date, json_date_to_datetime("2015-04-08T08:30:40.000Z"))

            self.assertEquals(response.request['PATH_INFO'], reverse('polls.poll_poll_date', args=[poll.pk]))

            tz = pytz.timezone('Africa/Kigali')
            with patch.object(timezone, 'now', return_value=tz.localize(datetime(2015, 9, 4, 3, 4, 5, 0))):
                flows_cached['uuid-30'] = dict(runs=300, completed_runs=120, name='Flow 2', uuid='uuid-30',
                                               labels="", archived=False, date_hint="2015-04-08", participants=None,
                                               rulesets=[dict(uuid='uuid-8435', id=8436, response_type="C",
                                                              label='Does your community have power')])

                mock_get_flows.return_value = flows_cached

                post_data = dict(title='Poll 2', category=self.health_uganda.pk, flow_uuid="uuid-30")
                response = self.client.post(create_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
                self.assertEqual(Poll.objects.all().count(), 2)

                poll = Poll.objects.get(flow_uuid='uuid-30')
                self.assertEquals(poll.title, 'Poll 2')
                self.assertEquals(poll.org, self.uganda)
                self.assertEqual(poll.poll_date, json_date_to_datetime("2015-09-04T01:04:05.000Z"))

    def test_poll_poll_date_view(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin,
                                     featured=True)

        uganda_poll_date_url = reverse('polls.poll_poll_date', args=[poll1.pk])
        nigeria_poll_date_url = reverse('polls.poll_poll_date', args=[poll2.pk])

        response = self.client.get(uganda_poll_date_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_poll_date_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_poll_date_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        with patch('dash.orgs.models.Org.get_flows') as mock_get_flows:
            flows_cached = dict()
            flows_cached['uuid-1'] = dict(runs=300, completed_runs=120, name='Flow 1', uuid='uuid-1',
                                          labels="", archived=False, created_on="2015-04-08T12:48:44.320Z",
                                          date_hint="2015-04-08", participants=None,
                                          rulesets=[dict(uuid='uuid-8435', id=8435, response_type="C",
                                                         label='Does your community have power')])

            mock_get_flows.return_value = flows_cached

            now = timezone.now()
            yesterday = now - timedelta(days=1)

            response = self.client.get(uganda_poll_date_url, SERVER_NAME='uganda.ureport.io')
            self.assertEquals(response.status_code, 200)
            self.assertTrue('form' in response.context)

            self.assertEquals(len(response.context['form'].fields), 2)

            self.assertTrue('poll_date' in response.context['form'].fields)
            self.assertTrue('loc' in response.context['form'].fields)

            post_data = dict(poll_date=yesterday.strftime('%Y-%m-%d %H:%M:%S'))
            response = self.client.post(uganda_poll_date_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')

            poll = Poll.objects.get(flow_uuid='uuid-1')
            self.assertEquals(poll.org, self.uganda)
            self.assertEquals(poll.title, 'Poll 1')
            self.assertEqual(poll.poll_date.astimezone(self.uganda.timezone).replace(tzinfo=pytz.UTC),
                             yesterday.replace(microsecond=0))

            self.assertEquals(response.request['PATH_INFO'], reverse('polls.poll_questions', args=[poll.pk]))

            tz = pytz.timezone('Africa/Kigali')
            with patch.object(timezone, 'now', return_value=tz.localize(datetime(2015, 9, 4, 3, 4, 5, 0))):
                response = self.client.post(uganda_poll_date_url, dict(), follow=True, SERVER_NAME='uganda.ureport.io')

                poll = Poll.objects.get(flow_uuid='uuid-1')
                self.assertEquals(poll.org, self.uganda)
                self.assertEquals(poll.title, 'Poll 1')
                self.assertEqual(poll.poll_date, json_date_to_datetime("2015-09-04T01:04:05.000Z"))

                self.assertEquals(response.request['PATH_INFO'], reverse('polls.poll_questions', args=[poll.pk]))

    @patch('dash.orgs.models.TembaClient2', MockTembaClient)
    def test_update_poll(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

        uganda_update_url = reverse('polls.poll_update', args=[poll1.pk])
        nigeria_update_url = reverse('polls.poll_update', args=[poll2.pk])

        response = self.client.get(uganda_update_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_update_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_update_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        with patch('dash.orgs.models.Org.get_flows') as mock_get_flows:
            flows_cached = dict()
            flows_cached['uuid-1'] = dict(runs=300, completed_runs=120, name='Flow 1', uuid='uuid-1',
                                          labels="", archived=False, created_on="2015-04-08T12:48:44.320Z",
                                          date_hint="2015-04-08", participants=None,
                                          rulesets=[dict(uuid='uuid-8435', id=8435, response_type="C",
                                                         label='Does your community have power')])

            mock_get_flows.return_value = flows_cached

            now = timezone.now()
            yesterday = now - timedelta(days=1)

            response = self.client.get(uganda_update_url, SERVER_NAME='uganda.ureport.io')
            self.assertEquals(response.status_code, 200)
            self.assertTrue('form' in response.context)

            self.assertEquals(len(response.context['form'].fields), 7)
            self.assertTrue('is_active' in response.context['form'].fields)
            self.assertTrue('is_featured' in response.context['form'].fields)
            self.assertTrue('title' in response.context['form'].fields)
            self.assertTrue('poll_date' in response.context['form'].fields)
            self.assertTrue('category' in response.context['form'].fields)
            self.assertIsInstance(response.context['form'].fields['category'].choices.field, CategoryChoiceField)
            self.assertEquals(list(response.context['form'].fields['category'].choices),
                              [('', '---------'),
                              (self.health_uganda.pk, 'uganda - Health')])
            self.assertTrue('category_image' in response.context['form'].fields)
            self.assertTrue('loc' in response.context['form'].fields)

            response = self.client.post(uganda_update_url, dict(), SERVER_NAME='uganda.ureport.io')
            self.assertTrue('form' in response.context)
            self.assertTrue(response.context['form'].errors)
            self.assertEquals(len(response.context['form'].errors), 2)
            self.assertTrue('title' in response.context['form'].errors)
            self.assertTrue('category' in response.context['form'].errors)

            post_data = dict(title='title updated', category=self.health_uganda.pk,
                             is_featured=False, poll_date=yesterday.strftime('%Y-%m-%d %H:%M:%S'))
            response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
            self.assertFalse('form' in response.context)
            updated_poll = Poll.objects.get(pk=poll1.pk)
            self.assertEquals(updated_poll.title, 'title updated')
            self.assertFalse(updated_poll.is_featured)

            self.assertEquals(response.request['PATH_INFO'], reverse('polls.poll_list'))

            tz = pytz.timezone('Africa/Kigali')
            with patch.object(timezone, 'now', return_value=tz.localize(datetime(2015, 9, 4, 3, 4, 5, 0))):
                response = self.client.get(uganda_update_url, SERVER_NAME='uganda.ureport.io')
                self.assertContains(response, "Edit Poll for flow [Flow 1 (2015-04-08)]")

                post_data = dict(title='Poll 2', category=self.health_uganda.pk,
                                 is_featured=False, poll_date="")
                response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
                self.assertEqual(Poll.objects.all().count(), 2)

                poll = Poll.objects.get(flow_uuid='uuid-1')
                self.assertEquals(poll.title, 'Poll 2')
                self.assertEquals(poll.org, self.uganda)
                self.assertEqual(poll.poll_date, json_date_to_datetime("2015-09-04T01:04:05.000Z"))

    def test_list_poll(self):
        list_url = reverse('polls.poll_list')
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

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

    @patch('dash.orgs.models.TembaClient2', MockTembaClient)
    def test_questions_poll(self):

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

        uganda_questions_url = reverse('polls.poll_questions', args=[poll1.pk])
        nigeria_questions_url = reverse('polls.poll_questions', args=[poll2.pk])

        response = self.client.get(uganda_questions_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_questions_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_questions_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_questions_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)
        self.assertEquals(len(response.context['form'].fields), 0)

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_label='question poll 1',
                                                     ruleset_uuid="uuid-101",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        response = self.client.get(uganda_questions_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)
        self.assertEquals(len(response.context['form'].fields), 4)
        self.assertTrue('ruleset_uuid-101_include' in response.context['form'].fields)
        self.assertTrue('ruleset_uuid-101_priority' in response.context['form'].fields)
        self.assertTrue('ruleset_uuid-101_label' in response.context['form'].fields)
        self.assertTrue('ruleset_uuid-101_title' in response.context['form'].fields)
        self.assertEquals(response.context['form'].fields['ruleset_uuid-101_priority'].initial, 0)
        self.assertEquals(response.context['form'].fields['ruleset_uuid-101_label'].initial, 'question poll 1')
        self.assertEquals(response.context['form'].fields['ruleset_uuid-101_title'].initial, 'question poll 1')
        self.assertContains(response, "The label of the ruleset from RapidPro")

        post_data = dict()
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertTrue(response.context['form'].errors)
        self.assertTrue(response.context['form'].errors['__all__'][0], 'You must include at least one poll question.')

        post_data = dict()
        post_data['ruleset_uuid-101_include'] = True
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertTrue(response.context['form'].errors)
        self.assertTrue(response.context['form'].errors['__all__'][0], "You must include a title for every included question.")

        post_data = dict()
        post_data['ruleset_uuid-101_include'] = True
        post_data['ruleset_uuid-101_title'] = "hello " * 50
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertTrue(response.context['form'].errors)
        self.assertTrue(response.context['form'].errors['__all__'][0], "Title too long. The max limit is 255 characters for each title")

        post_data = dict()
        post_data['ruleset_uuid-101_include'] = True
        post_data['ruleset_uuid-101_title'] = "have electricity access"
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertTrue(PollQuestion.objects.filter(poll=poll1))

        poll_question = PollQuestion.objects.filter(poll=poll1, ruleset_uuid="uuid-101")[0]
        self.assertEquals(poll_question.title, 'have electricity access')
        self.assertEquals(poll_question.ruleset_label, 'question poll 1')
        self.assertEquals(poll_question.priority, 0)

        self.assertEquals(response.request['PATH_INFO'], reverse('polls.poll_images', args=[poll1.pk]))

        post_data = dict()
        post_data['ruleset_uuid-101_include'] = True
        post_data['ruleset_uuid-101_title'] = "electricity network coverage"
        post_data['ruleset_uuid-101_priority'] = 5
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')

        self.assertTrue(PollQuestion.objects.filter(poll=poll1))

        poll_question = PollQuestion.objects.filter(poll=poll1)[0]
        self.assertEquals(poll_question.title, 'electricity network coverage')
        self.assertEquals(poll_question.ruleset_label, 'question poll 1')
        self.assertEquals(poll_question.priority, 5)

        with patch('ureport.polls.models.Poll.clear_brick_polls_cache') as mock:
            mock.return_value = 'Cache cleared'

            post_data = dict()
            post_data['ruleset_uuid-101_include'] = True
            post_data['ruleset_uuid-101_title'] = "electricity network coverage"
            response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')

            mock.assert_called_once_with(poll1.org)

    def test_images_poll(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

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
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

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

    @patch('dash.orgs.models.TembaClient2', MockTembaClient)
    def test_templatetags(self):
        from ureport.polls.templatetags.ureport import config, org_color, transparency, show_org_flags
        from ureport.polls.templatetags.ureport import org_host_link, org_arrow_link, question_results

        with patch('dash.orgs.models.Org.get_config') as mock:
            mock.return_value = 'Done'

            self.assertIsNone(config(None, 'field_name'))
            self.assertEquals(config(self.uganda, 'field_name'), 'Done')
            mock.assert_called_with('field_name')

        self.assertIsNone(org_color(None, 1))
        self.assertEquals(org_color(self.uganda, 0), '#FFD100')
        self.assertEquals(org_color(self.uganda, 1), '#1F49BF')
        self.assertEquals(org_color(self.uganda, 2), '#FFD100')
        self.assertEquals(org_color(self.uganda, 3), '#1F49BF')

        self.uganda.set_config('primary_color', '#aaaaaa')

        self.assertEquals(org_color(self.uganda, 0), '#FFD100')
        self.assertEquals(org_color(self.uganda, 1), '#1F49BF')
        self.assertEquals(org_color(self.uganda, 2), '#FFD100')
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

        self.assertIsNone(org_arrow_link(org=None))
        self.assertEqual(org_arrow_link(self.uganda), "&#8594;")

        self.uganda.language = 'ar'
        self.uganda.save()

        self.assertEqual(org_arrow_link(self.uganda), "&#8592;")

        self.assertFalse(question_results(None))

        with patch('ureport.polls.models.PollQuestion.get_results') as mock_results:
            mock_results.return_value = ["Results"]

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

            poll1_question = PollQuestion.objects.create(poll=poll1,
                                                         title='question poll 1',
                                                         ruleset_uuid="uuid-101",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

            self.assertEqual(question_results(poll1_question), "Results")

            mock_results.side_effect = KeyError

            self.assertFalse(question_results(poll1_question))

        with patch('ureport.polls.models.PollQuestion.get_results') as mock_results:
            mock_results.return_value = ["Results"]

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

            poll1_question = PollQuestion.objects.create(poll=poll1,
                                                         title='question poll 1',
                                                         ruleset_uuid="uuid-101",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

            self.assertEqual(question_segmented_results(poll1_question, 'gender'), ["Results"])

            mock_results.side_effect = KeyError

            self.assertFalse(question_segmented_results(poll1_question, 'gender'))

    def test_delete_poll_results_counter(self):
        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        poll_question = PollQuestion.objects.create(poll=poll, title='question 1', ruleset_uuid='step-uuid',
                                                    created_by=self.admin, modified_by=self.admin)

        self.assertFalse(PollResultsCounter.objects.all())

        PollResult.objects.create(org=self.nigeria, flow=poll.flow_uuid,
                                  ruleset=poll_question.ruleset_uuid, date=timezone.now(),
                                  contact='contact-uuid', completed=False)

        with self.settings(CACHES={'default': {'BACKEND': 'django_redis.cache.RedisCache',
                                               'LOCATION': '127.0.0.1:6379:1',
                                               'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'}
                                               }}):
            poll.rebuild_poll_results_counts()

            self.assertTrue(PollResultsCounter.objects.all())

            poll.delete_poll_results_counter()

            self.assertFalse(PollResultsCounter.objects.all())

    def test_delete_poll_results(self):
        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        poll_question = PollQuestion.objects.create(poll=poll, title='question 1', ruleset_uuid='step-uuid',
                                                    created_by=self.admin, modified_by=self.admin)
        PollResult.objects.create(org=self.nigeria, flow=poll.flow_uuid,
                                  ruleset=poll_question.ruleset_uuid, date=timezone.now(),
                                  contact='contact-uuid', completed=False)

        poll.delete_poll_results()

        self.assertFalse(PollResult.objects.filter(org=self.nigeria, flow=poll.flow_uuid))

    @patch('ureport.tests.TestBackend.pull_results')
    def test_poll_pull_results(self, mock_pull_results):
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        self.assertFalse(poll.has_synced)
        Poll.pull_results(poll.pk)

        poll = Poll.objects.get(pk=poll.pk)
        self.assertTrue(poll.has_synced)

        mock_pull_results.assert_called_once()


class PollQuestionTest(UreportTest):
    def setUp(self):
        super(PollQuestionTest, self).setUp()
        self.health_uganda = Category.objects.create(org=self.uganda,
                                                     name="Health",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

    def assertResult(self, result, index, category, count):
        self.assertEquals(count, result['categories'][index]['count'])
        self.assertEquals(category, result['categories'][index]['label'])

    def test_poll_question_model(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

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
        self.uganda.set_config("ward_label", "Ward")

        # no response category are ignored
        PollResponseCategory.update_or_create(poll_question1, 'rule-uuid-4', 'No Response')

        self.assertFalse(poll_question1.is_open_ended())

        PollResponseCategory.update_or_create(poll_question1, 'rule-uuid-1', 'Yes')

        self.assertTrue(poll_question1.is_open_ended())

        PollResponseCategory.update_or_create(poll_question1, 'rule-uuid-2', 'No')
        PollResponseCategory.objects.filter(category='No').update(is_active=False)

        self.assertTrue(poll_question1.is_open_ended())

        PollResponseCategory.objects.filter(category='No').update(is_active=True)

        self.assertFalse(poll_question1.is_open_ended())

        # should be ignored in calculated results
        PollResponseCategory.update_or_create(poll_question1, 'rule-uuid-3', 'Other')

        now = timezone.now()

        PollResult.objects.create(org=self.uganda, flow=poll1.flow_uuid, ruleset=poll_question1.ruleset_uuid,
                                  contact='contact-1', date=now, category='All responses', state='', district='',
                                  text='1 better place', completed=False)

        PollResult.objects.create(org=self.uganda, flow=poll1.flow_uuid, ruleset=poll_question1.ruleset_uuid,
                                  contact='contact-2', date=now, category='All responses', state='', district='',
                                  text='the great coffee', completed=False)

        PollResult.objects.create(org=self.uganda, flow=poll1.flow_uuid, ruleset=poll_question1.ruleset_uuid,
                                  contact='contact-3', date=now, category='All responses', state='', district='',
                                  text='1 cup of black tea', completed=False)

        PollResult.objects.create(org=self.uganda, flow=poll1.flow_uuid, ruleset=poll_question1.ruleset_uuid,
                                  contact='contact-3', date=now, category='All responses', state='', district='',
                                  text='1 cup of green tea', completed=False)

        PollResult.objects.create(org=self.uganda, flow=poll1.flow_uuid, ruleset=poll_question1.ruleset_uuid,
                                  contact='contact-4', date=now, category='All responses', state='', district='',
                                  text='awesome than this encore', completed=False)

        PollResult.objects.create(org=self.uganda, flow=poll1.flow_uuid, ruleset=poll_question1.ruleset_uuid,
                                  contact='contact-5', date=now, category='All responses', state='', district='',
                                  text='from an awesome place in kigali', completed=False)

        PollResult.objects.create(org=self.uganda, flow=poll1.flow_uuid, ruleset=poll_question1.ruleset_uuid,
                                  contact='contact-5', date=now, category='All responses', state='', district='',
                                  text='HtTp://kigali.coffee.fbcdn.com/like_image.png', completed=False)

        with patch('ureport.polls.models.PollQuestion.is_open_ended') as mock_open:
            mock_open.return_value = True

            results = poll_question1.calculate_results()
            result = results[0]
            self.assertEquals(11, len(result['categories']))
            self.assertTrue(result['open_ended'])
            self.assertResult(result, 0, "awesome", 2)
            self.assertResult(result, 1, "cup", 2)
            self.assertResult(result, 2, "place", 2)
            self.assertResult(result, 3, "tea", 2)
            self.assertResult(result, 4, "better", 1)
            self.assertResult(result, 5, "black", 1)
            self.assertResult(result, 6, "coffee", 1)
            self.assertResult(result, 7, "encore", 1)
            self.assertResult(result, 8, "great", 1)
            self.assertResult(result, 9, "green", 1)
            self.assertResult(result, 10, "kigali", 1)

            self.uganda.language = 'fr'
            self.uganda.save()

            results = poll_question1.calculate_results()
            result = results[0]
            self.assertEquals(10, len(result['categories']))
            self.assertTrue(result['open_ended'])
            self.assertResult(result, 0, "awesome", 2)
            self.assertResult(result, 1, "cup", 2)
            self.assertResult(result, 2, "place", 2)
            self.assertResult(result, 3, "tea", 2)
            self.assertResult(result, 4, "better", 1)
            self.assertResult(result, 5, "black", 1)
            self.assertResult(result, 6, "coffee", 1)
            self.assertResult(result, 7, "great", 1)
            self.assertResult(result, 8, "green", 1)
            self.assertResult(result, 9, "kigali", 1)

            self.uganda.language = 'en'
            self.uganda.save()

            with patch('ureport.utils.get_dict_from_cursor') as mock_get_dict_from_cursor:
                # no error for segmenting
                results = poll_question1.calculate_results(dict(location='State'))
                # should not have used the path with custom sql
                self.assertFalse(mock_get_dict_from_cursor.called)

        question_results = dict()
        question_results['ruleset:%s:total-ruleset-responded' % poll_question1.ruleset_uuid] = 3462
        question_results['ruleset:%s:total-ruleset-polled' % poll_question1.ruleset_uuid] = 7156
        question_results['ruleset:%s:category:yes' % poll_question1.ruleset_uuid] = 2210
        question_results['ruleset:%s:category:no' % poll_question1.ruleset_uuid] = 1252

        with patch('ureport.polls.models.PollQuestion.get_question_results') as mock:
            mock.return_value = dict()

            calculated_results = [dict(open_ended=False, set=0, unset=0, categories=[dict(count=0, label='Yes'),
                                                                                     dict(count=0, label='No')])]

            self.assertEqual(poll_question1.calculate_results(), calculated_results)
            mock.assert_called_with()

            self.assertEquals(poll_question1.get_responded(), 0)
            mock.assert_called_with()

            self.assertEquals(poll_question1.get_polled(), 0)
            mock.assert_called_with()

            with patch('ureport.polls.models.PollQuestion.get_results') as mock_get_results:
                mock_get_results.return_value = calculated_results
                self.assertEquals(poll_question1.get_words(), [dict(count=0, label='Yes'), dict(count=0, label='No')])
                mock_get_results.assert_called_with()

            mock.return_value = question_results
            poll1.runs_count = 7156
            poll1.save()

            calculated_results = [dict(open_ended=False, set=3462, unset=3694,
                                       categories=[dict(count=2210, label='Yes'),
                                                   dict(count=1252, label='No')])]

            self.assertEqual(poll_question1.calculate_results(), calculated_results)

            self.assertEquals(poll_question1.get_responded(), 3462)
            mock.assert_called_with()

            self.assertEquals(poll_question1.get_polled(), 7156)
            mock.assert_called_with()

            with patch('ureport.polls.models.PollQuestion.get_results') as mock_get_results:
                mock_get_results.return_value = calculated_results
                self.assertEquals(poll_question1.get_words(), [dict(count=2210, label='Yes'), dict(count=1252, label='No')])
                mock.assert_called_with()

            self.assertEquals(poll_question1.get_response_percentage(), "48%")

            question_results['ruleset:%s:category:yes:state:R-KGL' % poll_question1.ruleset_uuid] = 10
            question_results['ruleset:%s:category:yes:state:R-LAGOS' % poll_question1.ruleset_uuid] = 20
            question_results['ruleset:%s:category:no:state:R-LAGOS' % poll_question1.ruleset_uuid] = 30
            question_results['ruleset:%s:nocategory:state:R-LAGOS' % poll_question1.ruleset_uuid] = 33

            mock.return_value = question_results

            with patch('dash.orgs.models.Org.get_segment_org_boundaries') as mock_segment_boundaries:
                mock_segment_boundaries.return_value = [dict(osm_id='R-KGL', name='Kigali'),
                                                        dict(osm_id='R-LAGOS', name='Lagos')]

                self.assertEqual(poll_question1.calculate_results(segment=dict(location='State')),
                                 [dict(open_ended=False, set=10, unset=0, boundary='R-KGL', label='Kigali',
                                       categories=[dict(count=10, label='Yes'), dict(count=0, label='No')]),
                                  dict(open_ended=False, set=50, unset=33, boundary='R-LAGOS', label='Lagos',
                                       categories=[dict(count=20, label='Yes'), dict(count=30, label='No')])])

            question_results['ruleset:%s:category:yes:gender:m' % poll_question1.ruleset_uuid] = 5
            question_results['ruleset:%s:category:yes:gender:f' % poll_question1.ruleset_uuid] = 10
            question_results['ruleset:%s:category:no:gender:m' % poll_question1.ruleset_uuid] = 12
            question_results['ruleset:%s:nocategory:gender:f' % poll_question1.ruleset_uuid] = 8

            mock.return_value = question_results

            gender_results = poll_question1.calculate_results(segment=dict(gender='Gender'))

            self.assertEqual(gender_results[0]['set'], 10)
            self.assertEqual(gender_results[0]['unset'], 8)
            self.assertEqual(gender_results[0]['label'].title(), 'Female')
            self.assertEqual(gender_results[0]['categories'][0]['count'], 10)
            self.assertEqual(gender_results[0]['categories'][0]['label'], 'Yes')
            self.assertEqual(gender_results[0]['categories'][1]['count'], 0)
            self.assertEqual(gender_results[0]['categories'][1]['label'], 'No')

            self.assertEqual(gender_results[1]['set'], 17)
            self.assertEqual(gender_results[1]['unset'], 0)
            self.assertEqual(gender_results[1]['label'].title(), 'Male')
            self.assertEqual(gender_results[1]['categories'][0]['count'], 5)
            self.assertEqual(gender_results[1]['categories'][0]['label'], 'Yes')
            self.assertEqual(gender_results[1]['categories'][1]['count'], 12)
            self.assertEqual(gender_results[1]['categories'][1]['label'], 'No')

            poll1.poll_date = datetime.now().replace(year=2015)
            poll1.save()

            question_results['ruleset:%s:category:yes:born:3' % poll_question1.ruleset_uuid] = 5
            question_results['ruleset:%s:category:yes:born:2000' % poll_question1.ruleset_uuid] = 10
            question_results['ruleset:%s:category:yes:born:2010' % poll_question1.ruleset_uuid] = 25
            question_results['ruleset:%s:category:no:born:1990' % poll_question1.ruleset_uuid] = 12
            question_results['ruleset:%s:nocategory:born:28990' % poll_question1.ruleset_uuid] = 8
            question_results['ruleset:%s:nocategory:born:1995' % poll_question1.ruleset_uuid] = 100

            age_results = poll_question1.calculate_results(segment=dict(age='Age'))

            self.assertEqual(age_results, [dict(set=25, unset=0,
                                                categories=[dict(count=25, label='yes'), dict(count=0, label='no')],
                                                label='0-14'),
                                           dict(set=10, unset=0,
                                                categories=[dict(count=10, label='yes'), dict(count=0, label='no')],
                                                label='15-19'),
                                           dict(set=0, unset=100,
                                                categories=[dict(count=0, label='yes'), dict(count=0, label='no')],
                                                label='20-24'),
                                           dict(set=12, unset=0,
                                                categories=[dict(count=0, label='yes'), dict(count=12, label='no')],
                                                label='25-30'),
                                           dict(set=0, unset=0,
                                                categories=[dict(count=0, label='yes'), dict(count=0, label='no')],
                                                label='31-34'),
                                           dict(set=0, unset=0,
                                                categories=[dict(count=0, label='yes'), dict(count=0, label='no')],
                                                label='35+'),
                                           ])

    def test_tasks(self):
        self.org = self.create_org("burundi", pytz.timezone('Africa/Bujumbura'), self.admin)

        self.education = Category.objects.create(org=self.org,
                                                 name="Education",
                                                 created_by=self.admin,
                                                 modified_by=self.admin)

        self.poll = self.create_poll(self.org, "Poll 1", "uuid-1", self.education, self.admin)

        with patch('ureport.polls.tasks.fetch_flows') as mock_fetch_flows:
            mock_fetch_flows.return_value = 'FETCHED'

            refresh_org_flows(self.org.pk)
            mock_fetch_flows.assert_called_once_with(self.org)

        with patch('ureport.polls.tasks.fetch_old_sites_count') as mock_fetch_old_sites_count:
            mock_fetch_old_sites_count.return_value = 'FETCHED'

            fetch_old_sites_count()
            mock_fetch_old_sites_count.assert_called_once_with()

        with patch('ureport.polls.tasks.update_poll_flow_data') as mock_update_poll_flow_data:
            mock_update_poll_flow_data.return_value = 'RECHECKED'

            recheck_poll_flow_data(self.org.pk)
            mock_update_poll_flow_data.assert_called_once_with(self.org)

        with patch('ureport.polls.models.Poll.pull_results') as mock_pull_results:
            mock_pull_results.return_value = "Pulled"

            pull_refresh(self.poll.pk)
            mock_pull_results.assert_called_once_with(self.poll.pk)

        with patch('ureport.polls.models.Poll.rebuild_poll_results_counts') as mock_rebuild_counts:
            mock_rebuild_counts.return_value = "Rebuilt"

            rebuild_counts()
            self.assertEqual(mock_rebuild_counts.call_count, Poll.objects.all().count())

        with patch('ureport.polls.models.Poll.update_or_create_questions') as mock_update_or_create_questions:
            mock_update_or_create_questions.side_effect = None

            update_or_create_questions([self.poll.pk])
            mock_update_or_create_questions.assert_called_once()
            mock_update_or_create_questions.reset_mock()

            poll2 = self.create_poll(self.uganda, "Poll 2", "flow-uuid-2", self.health_uganda, self.admin)
            update_or_create_questions([self.poll.pk, poll2.pk])
            self.assertEqual(mock_update_or_create_questions.call_count, 2)

        with patch('ureport.polls.models.Poll.rebuild_poll_results_counts') as mock_rebuild_counts:
            mock_rebuild_counts.return_value = "Rebuilt"

            with patch('ureport.polls.tasks.populate_age_and_gender_poll_results') as mock_populate_age_gender_results:
                mock_populate_age_gender_results.return_value = 'Populated'

                update_results_age_gender(self.nigeria.pk)

                mock_populate_age_gender_results.assert_called_once_with(self.nigeria)
                self.assertEqual(mock_rebuild_counts.call_count, Poll.objects.filter(org=self.nigeria).count())


class PollResultsTest(UreportTest):
    def setUp(self):
        super(PollResultsTest, self).setUp()
        self.nigeria.set_config('reporter_group', "Ureporters")

        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

        self.poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        self.poll_question = PollQuestion.objects.create(poll=self.poll, title='question 1', ruleset_uuid='step-uuid',
                                                         created_by=self.admin, modified_by=self.admin)

        self.now = timezone.now()
        self.last_week = self.now - timedelta(days=7)
        self.last_month = self.now - timedelta(days=30)

    def test_poll_results_counters(self):
        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), dict())

        poll_result = PollResult.objects.create(org=self.nigeria, flow=self.poll.flow_uuid,
                                                ruleset=self.poll_question.ruleset_uuid, date=self.now,
                                                contact='contact-uuid', completed=False)

        self.poll.rebuild_poll_results_counts()

        expected = dict()
        expected["ruleset:%s:total-ruleset-polled" % self.poll_question.ruleset_uuid] = 1

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

        poll_result.state = 'R-LAGOS'
        poll_result.save()
        self.poll.rebuild_poll_results_counts()

        expected['ruleset:%s:nocategory:state:R-LAGOS' % self.poll_question.ruleset_uuid] = 1
        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

        poll_result.category = 'Yes'
        poll_result.save()
        self.poll.rebuild_poll_results_counts()

        expected = dict()
        expected["ruleset:%s:total-ruleset-polled" % self.poll_question.ruleset_uuid] = 1
        expected['ruleset:%s:category:yes:state:R-LAGOS' % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:category:yes" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:total-ruleset-responded" % self.poll_question.ruleset_uuid] = 1

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

        PollResult.objects.create(org=self.nigeria, flow=self.poll.flow_uuid, ruleset=self.poll_question.ruleset_uuid,
                                  contact='contact-uuid', category='No', text='Nah', completed=False, date=self.now,
                                  state='R-LAGOS', district='R-oyo', ward='R-IKEJA')

        self.poll.rebuild_poll_results_counts()

        expected = dict()
        expected["ruleset:%s:total-ruleset-polled" % self.poll_question.ruleset_uuid] = 2
        expected["ruleset:%s:total-ruleset-responded" % self.poll_question.ruleset_uuid] = 2
        expected["ruleset:%s:category:yes" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:category:no" % self.poll_question.ruleset_uuid] = 1
        expected['ruleset:%s:category:yes:state:R-LAGOS' % self.poll_question.ruleset_uuid] = 1
        expected['ruleset:%s:category:no:state:R-LAGOS' % self.poll_question.ruleset_uuid] = 1
        expected['ruleset:%s:category:no:district:R-OYO' % self.poll_question.ruleset_uuid] = 1
        expected['ruleset:%s:category:no:ward:R-IKEJA' % self.poll_question.ruleset_uuid] = 1

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

    def test_poll_results_without_category(self):

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), dict())

        PollResult.objects.create(org=self.nigeria, flow=self.poll.flow_uuid,
                                  ruleset=self.poll_question.ruleset_uuid, date=self.now,
                                  contact='contact-uuid', completed=False, state='R-LAGOS',
                                  district='R-OYO', ward='R-IKEJA')

        self.poll.rebuild_poll_results_counts()

        expected = dict()
        expected["ruleset:%s:total-ruleset-polled" % self.poll_question.ruleset_uuid] = 1
        expected['ruleset:%s:nocategory:state:R-LAGOS' % self.poll_question.ruleset_uuid] = 1
        expected['ruleset:%s:nocategory:district:R-OYO' % self.poll_question.ruleset_uuid] = 1
        expected['ruleset:%s:nocategory:ward:R-IKEJA' % self.poll_question.ruleset_uuid] = 1

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

    def test_poll_result_generate_counters(self):
        poll_result1 = PollResult.objects.create(org=self.nigeria, flow=self.poll.flow_uuid,
                                                 ruleset=self.poll_question.ruleset_uuid, date=self.now,
                                                 contact='contact-uuid', completed=False)

        gen_counters = poll_result1.generate_counters()
        self.assertEqual(len(gen_counters.keys()), 1)
        self.assertTrue('ruleset:%s:total-ruleset-polled' % self.poll_question.ruleset_uuid in gen_counters.keys())

        poll_result2 = PollResult.objects.create(org=self.nigeria, flow=self.poll.flow_uuid,
                                                 ruleset='other-uuid',
                                                 contact='contact-uuid', category='No', text='Nah', completed=False,
                                                 date=self.now, state='R-LAGOS', district='R-oyo', ward='R-IKEJA')

        gen_counters = poll_result2.generate_counters()

        ruleset = poll_result2.ruleset.lower()
        category = poll_result2.category.lower()
        state = poll_result2.state.upper()
        district = poll_result2.district.upper()
        ward = poll_result2.ward.upper()

        self.assertEqual(len(gen_counters.keys()), 6)

        self.assertTrue('ruleset:%s:total-ruleset-polled' % ruleset in gen_counters.keys())

        self.assertTrue('ruleset:%s:total-ruleset-responded' % ruleset in gen_counters.keys())

        self.assertTrue('ruleset:%s:category:%s' % (ruleset, category) in gen_counters.keys())

        self.assertTrue('ruleset:%s:category:%s:state:%s' % (ruleset, category, state) in gen_counters.keys())

        self.assertTrue('ruleset:%s:category:%s:district:%s' % (ruleset, category, district) in gen_counters.keys())

        self.assertTrue('ruleset:%s:category:%s:ward:%s' % (ruleset, category, ward) in gen_counters.keys())

        poll_result3 = PollResult.objects.create(org=self.nigeria, flow=self.poll.flow_uuid,
                                                 ruleset='other-uuid',
                                                 contact='contact-uuid', category='No Response', text='None', completed=False,
                                                 date=self.now, state='R-LAGOS', district='R-oyo', ward='R-IKEJA')

        gen_counters = poll_result3.generate_counters()

        ruleset = poll_result3.ruleset.lower()
        state = poll_result3.state.upper()
        district = poll_result3.district.upper()
        ward = poll_result3.ward.upper()

        self.assertEqual(len(gen_counters.keys()), 4)

        self.assertTrue('ruleset:%s:total-ruleset-polled' % ruleset in gen_counters.keys())
        self.assertFalse('ruleset:%s:total-ruleset-responded' % ruleset in gen_counters.keys())  # no response ignored
        self.assertTrue('ruleset:%s:nocategory:state:%s' % (ruleset, state) in gen_counters.keys())
        self.assertTrue('ruleset:%s:nocategory:district:%s' % (ruleset, district) in gen_counters.keys())
        self.assertTrue('ruleset:%s:nocategory:ward:%s' % (ruleset, ward) in gen_counters.keys())

        poll_result4 = PollResult.objects.create(org=self.nigeria, flow=self.poll.flow_uuid,
                                                 ruleset='other-uuid',
                                                 contact='contact-uuid', category='No Response', text='Some text',
                                                 completed=False,
                                                 date=self.now, state='R-LAGOS', district='R-oyo', ward='R-IKEJA')

        gen_counters = poll_result4.generate_counters()

        ruleset = poll_result4.ruleset.lower()
        state = poll_result4.state.upper()
        district = poll_result4.district.upper()
        ward = poll_result4.ward.upper()

        self.assertEqual(len(gen_counters.keys()), 5)

        self.assertTrue('ruleset:%s:total-ruleset-polled' % ruleset in gen_counters.keys())
        self.assertTrue('ruleset:%s:total-ruleset-responded' % ruleset in gen_counters.keys())  # not ignored by text
        self.assertTrue('ruleset:%s:nocategory:state:%s' % (ruleset, state) in gen_counters.keys())
        self.assertTrue('ruleset:%s:nocategory:district:%s' % (ruleset, district) in gen_counters.keys())
        self.assertTrue('ruleset:%s:nocategory:ward:%s' % (ruleset, ward) in gen_counters.keys())

        poll_result5 = PollResult.objects.create(org=self.nigeria, flow=self.poll.flow_uuid,
                                                 ruleset='other-uuid',
                                                 contact='contact-uuid', category='Other', text='Some suprise',
                                                 completed=False,
                                                 date=self.now, state='R-LAGOS', district='R-oyo', ward='R-IKEJA')

        gen_counters = poll_result5.generate_counters()

        ruleset = poll_result5.ruleset.lower()
        state = poll_result5.state.upper()
        district = poll_result5.district.upper()
        ward = poll_result5.ward.upper()

        self.assertEqual(len(gen_counters.keys()), 4)

        self.assertTrue('ruleset:%s:total-ruleset-polled' % ruleset in gen_counters.keys())
        self.assertFalse('ruleset:%s:total-ruleset-responded' % ruleset in gen_counters.keys())  # Other ignored
        self.assertTrue('ruleset:%s:nocategory:state:%s' % (ruleset, state) in gen_counters.keys())
        self.assertTrue('ruleset:%s:nocategory:district:%s' % (ruleset, district) in gen_counters.keys())
        self.assertTrue('ruleset:%s:nocategory:ward:%s' % (ruleset, ward) in gen_counters.keys())


class PollsTasksTest(UreportTest):
    def setUp(self):
        super(PollsTasksTest, self).setUp()
        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)
        self.poll = self.create_poll(self.nigeria, "Poll 1", "uuid-1", self.education_nigeria, self.admin)

        self.poll_same_flow = self.create_poll(self.nigeria, "Poll Same Flow", "uuid-1", self.education_nigeria, self.admin,
                                               has_synced=True)

        self.polls_query = Poll.objects.filter(pk__in=[self.poll.pk, self.poll_same_flow.pk]).order_by('-created_on')

    @patch('ureport.tests.TestBackend.pull_results')
    @patch('ureport.polls.models.Poll.get_main_poll')
    def test_pull_results_main_poll(self, mock_get_main_poll, mock_pull_results):
        mock_get_main_poll.return_value = self.poll
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

        pull_results_main_poll(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key='results-pull-main-poll')
        self.assertEqual(task_state.get_last_results()['flow-%s' % self.poll.flow_uuid],
                         {"num_val_created": 1, "num_val_updated": 2, "num_val_ignored": 3,
                          "num_path_created": 4, "num_path_updated": 5, "num_path_ignored": 6})

    @patch('ureport.tests.TestBackend.pull_results')
    @patch('ureport.polls.models.Poll.get_brick_polls')
    def test_pull_results_brick_polls(self, mock_get_brick_polls, mock_pull_results):
        mock_get_brick_polls.return_value = list(self.polls_query)
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

        pull_results_brick_polls(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key='results-pull-brick-polls')
        self.assertEqual(task_state.get_last_results()['flow-%s' % self.poll.flow_uuid],
                         {"num_val_created": 1, "num_val_updated": 2, "num_val_ignored": 3,
                          "num_path_created": 4, "num_path_updated": 5, "num_path_ignored": 6})

        mock_pull_results.assert_called_once()

    @patch('ureport.tests.TestBackend.pull_results')
    @patch('ureport.polls.models.Poll.get_other_polls')
    def test_pull_results_other_polls(self, mock_get_other_polls, mock_pull_results):
        mock_get_other_polls.return_value = self.polls_query
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

        pull_results_other_polls(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key='results-pull-other-polls')
        self.assertEqual(task_state.get_last_results()['flow-%s' % self.poll.flow_uuid],
                         {"num_val_created": 1, "num_val_updated": 2, "num_val_ignored": 3,
                          "num_path_created": 4, "num_path_updated": 5, "num_path_ignored": 6})

        mock_pull_results.assert_called_once()

    @patch('ureport.tests.TestBackend.pull_results')
    @patch('ureport.polls.models.Poll.get_recent_other_polls')
    def test_pull_results_other_polls(self, mock_get_recent_other_polls, mock_pull_results):
        mock_get_recent_other_polls.return_value = self.polls_query
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

        pull_results_recent_other_polls(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key='results-pull-recent-other-polls')
        self.assertEqual(task_state.get_last_results()['flow-%s' % self.poll.flow_uuid],
                         {"num_val_created": 1, "num_val_updated": 2, "num_val_ignored": 3,
                          "num_path_created": 4, "num_path_updated": 5, "num_path_ignored": 6})

        mock_pull_results.assert_called_once()

    @patch('ureport.tests.TestBackend.pull_results')
    def test_backfill_poll_results(self, mock_pull_results):
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

        self.poll.has_synced = True
        self.poll.save()

        backfill_poll_results(self.nigeria.pk)
        self.assertFalse(mock_pull_results.called)

        self.poll.has_synced = False
        self.poll.save()

        backfill_poll_results(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key='backfill-poll-results')
        self.assertEqual(task_state.get_last_results()['flow-%s' % self.poll.flow_uuid],
                         {"num_val_created": 1, "num_val_updated": 2, "num_val_ignored": 3,
                          "num_path_created": 4, "num_path_updated": 5, "num_path_ignored": 6})

        mock_pull_results.assert_called_once()
