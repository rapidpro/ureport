from datetime import datetime
import json
from dash.categories.models import Category
from dash_test_runner.tests import MockResponse
from django.utils import timezone
from mock import patch
import pycountry
import pytz
import redis
from temba_client.client import Group
from ureport.assets.models import FLAG, Image
from ureport.polls.models import CACHE_ORG_REPORTER_GROUP_KEY, UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME, Poll
from ureport.tests import DashTest
from ureport.utils import get_linked_orgs, fetch_reporter_group, clean_global_results_data, fetch_old_sites_count
from ureport.utils import get_global_count, fetch_main_poll_results, fetch_brick_polls_results, GLOBAL_COUNT_CACHE_KEY
from ureport.utils import fetch_other_polls_results, get_reporter_group, _fetch_org_polls_results


class UtilsTest(DashTest):

    def setUp(self):
        super(UtilsTest, self).setUp()
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

    def clear_cache(self):
        # hardcoded to localhost
        r = redis.StrictRedis(host='localhost', db=1)
        r.flushdb()

    def test_get_linked_orgs(self):

        # we have 4 old org in the settings
        self.assertEqual(len(get_linked_orgs()), 3)
        for old_site in get_linked_orgs():
            self.assertFalse(old_site['name'].lower() == 'burundi')

        self.org.set_config('is_on_landing_page', True)

        # missing flag
        self.assertEqual(len(get_linked_orgs()), 3)
        for old_site in get_linked_orgs():
            self.assertFalse(old_site['name'].lower() == 'burundi')

        Image.objects.create(org=self.org, image_type=FLAG, name='burundi_flag',
                             image="media/image.jpg", created_by=self.admin, modified_by=self.admin)

        # burundi should be included and be the first; by alphetical order
        self.assertEqual(len(get_linked_orgs()), 4)
        self.assertEqual(get_linked_orgs()[0]['name'].lower(), 'burundi')
        with self.settings(HOSTNAME='localhost:8000'):
            self.assertEqual(get_linked_orgs()[0]['host'].lower(), 'http://burundi.localhost:8000')
            self.assertEqual(get_linked_orgs(True)[0]['host'].lower(), 'http://burundi.localhost:8000')

            self.org.domain = 'ureport.bi'
            self.org.save()

            self.assertEqual(get_linked_orgs()[0]['host'].lower(), 'http://burundi.localhost:8000')
            self.assertEqual(get_linked_orgs(True)[0]['host'].lower(), 'http://burundi.localhost:8000')

            with self.settings(SESSION_COOKIE_SECURE=True):
                self.assertEqual(get_linked_orgs()[0]['host'].lower(), 'http://ureport.bi')
                self.assertEqual(get_linked_orgs(True)[0]['host'].lower(), 'https://burundi.localhost:8000')

    def test_clean_global_results_data(self):
        results = [{"open_ended": False,
                    "set": 0,
                    "unset": 0,
                    "categories": [{"count": 0, "label": "Yes"},
                                   {"count": 0, "label": "No"}],
                    "label": "UG"},
                   {"open_ended": False,
                    "set": 0,
                    "unset": 0,
                    "categories": [{"count": 0, "label": "Yes"},
                                   {"count": 0, "label": "No"}],
                    "label": "RW"},
                   {"open_ended": False,
                    "set": 0,
                    "unset": 0,
                    "categories": [{"count": 0, "label": "Yes"},
                                   {"count": 0, "label": "No"}],
                    "label": "MX"}]

        # no segment
        self.assertEqual(clean_global_results_data(self.org, results, None), results)

        # no location in segment
        self.assertEqual(clean_global_results_data(self.org, results, dict(allo='State')), results)

        # org not global
        self.assertEqual(clean_global_results_data(self.org, results, dict(location='State')), results)

        self.org.set_config('is_global', True)
        cleaned_results = [{"open_ended": False,
                            "set": 0,
                            "unset": 0,
                            "categories": [{"count": 0, "label": "Yes"},
                                           {"count": 0, "label": "No"}],
                            "boundary": "UG",
                            "label": "Uganda"},
                           {"open_ended": False,
                            "set": 0,
                            "unset": 0,
                            "categories": [{"count": 0, "label": "Yes"},
                                           {"count": 0, "label": "No"}],
                            "boundary": "RW",
                            "label": "Rwanda"},
                           {"open_ended": False,
                            "set": 0,
                            "unset": 0,
                            "categories": [{"count": 0, "label": "Yes"},
                                           {"count": 0, "label": "No"}],
                            "boundary": "MX",
                            "label": "Mexico"}]

        self.assertEqual(clean_global_results_data(self.org, results, dict(location='State')), cleaned_results)

    def test_substitute_segment(self):
        self.assertIsNone(self.org.substitute_segment(None))

        self.org.set_config("state_label", "Province")
        input_segment = dict(location='State')
        self.assertEqual(self.org.substitute_segment(input_segment), json.dumps(dict(location="Province")))
        # make sure we did not change the input segment
        self.assertEqual(input_segment, dict(location='State'))

        self.assertEqual(self.org.substitute_segment(dict(location='State')), json.dumps(dict(location="Province")))

        self.org.set_config("district_label", "LGA")
        input_segment = dict(location='District')
        self.assertEqual(self.org.substitute_segment(input_segment), json.dumps(dict(location="LGA")))
        # make sure we did not change the input segment
        self.assertEqual(input_segment, dict(location='District'))

        self.org.set_config("is_global", True)
        expected = dict(contact_field="Province", values=[elt.alpha2 for elt in pycountry.countries.objects])

        global_segment = self.org.substitute_segment(dict(location='State'))
        self.assertEqual(global_segment, json.dumps(expected))
        self.assertFalse('location' in json.loads(global_segment))

        global_segment = self.org.substitute_segment(dict(location='State', parent="country"))
        self.assertFalse('location' in json.loads(global_segment))
        self.assertFalse('parent' in json.loads(global_segment))
        self.assertEqual(global_segment, json.dumps(expected))

    def test_get_most_active_regions(self):
        self.org.set_config('gender_label', 'Gender')
        self.org.set_config("state_label", "Province")

        with patch('dash.orgs.models.Org.get_contact_field_results') as mock:
            mock.return_value = [dict(label='LABEL_1', set=15, unset=5, categories=[], open_ended=None),
                                 dict(label='LABEL_2', set=100, unset=200, categories=[], open_ended=None),
                                 dict(label='LABEL_3', set=50, unset=30, categories=[], open_ended=None)]

            self.assertEquals(self.org.get_most_active_regions(), ['LABEL_2', 'LABEL_3', 'LABEL_1'])
            mock.assert_called_once_with('Gender', dict(location='State'))

        with patch('dash.orgs.models.Org.get_contact_field_results') as mock:
            self.clear_cache()
            mock.return_value = None

            self.assertEquals(self.org.get_most_active_regions(), [])
            mock.assert_called_once_with('Gender', dict(location='State'))

        self.org.set_config("is_global", True)

        with patch('dash.orgs.models.Org.get_contact_field_results') as mock:
            mock.return_value = [dict(label='UG', set=15, unset=5, categories=[], open_ended=None),
                                 dict(label='RW', set=100, unset=200, categories=[], open_ended=None),
                                 dict(label='US', set=50, unset=30, categories=[], open_ended=None)]

            self.assertEquals(self.org.get_most_active_regions(), ['Rwanda', 'United States', 'Uganda'])
            segment = dict()
            segment["contact_field"] = "Province"
            segment["values"] = [elt.alpha2 for elt in pycountry.countries.objects]

            mock.assert_called_once_with('Gender', dict(location='State'))

    def test_organize_categories_data(self):

        self.org.set_config('born_label', "Born")
        self.org.set_config('registration_label', "Registration")
        self.org.set_config('occupation_label', "Occupation")

        self.assertEquals(self.org.organize_categories_data('random_field', []), [])
        self.assertEquals(self.org.organize_categories_data('born', []), [])
        self.assertEquals(self.org.organize_categories_data('registration', []), [])
        self.assertEquals(self.org.organize_categories_data('occupation', []), [])
        self.assertEquals(self.org.organize_categories_data('random_field', ['random_api_data']), ['random_api_data'])

        tz = pytz.timezone('Africa/Kigali')
        with patch.object(timezone, 'now', return_value=tz.localize(datetime(2014, 9, 26, 10, 20, 30, 40))):

            self.assertEquals(self.org.organize_categories_data('born', [dict(categories=[])]), [dict(categories=[])])
            self.assertEquals(self.org.organize_categories_data('born', [dict(categories=[dict(label='123',
                                                                                               count=50)])]),
                              [dict(categories=[])])
            self.assertEquals(self.org.organize_categories_data('born', [dict(categories=[dict(label='12345',
                                                                                               count=50)])]),
                              [dict(categories=[])])
            self.assertEquals(self.org.organize_categories_data('born', [dict(categories=[dict(label='abcd',
                                                                                               count=50)])]),
                              [dict(categories=[])])
            self.assertEquals(self.org.organize_categories_data('born', [dict(categories=[dict(label='1899',
                                                                                               count=50)])]),
                              [dict(categories=[])])

            self.assertEquals(self.org.organize_categories_data('born', [dict(categories=[dict(label='2010',
                                                                                               count=50)])]),
                              [dict(categories=[dict(label='0-10', count=50)])])

            self.assertEquals(self.org.organize_categories_data('born', [dict(categories=[dict(label='2000',
                                                                                               count=50)])]),
                              [dict(categories=[dict(label='10-20', count=50)])])

            born_api_data = [dict(categories=[dict(label='1700', count=10),
                                              dict(label='1998', count=10),
                                              dict(label='123', count=10),
                                              dict(label='abcd', count=1),
                                              dict(label='2005', count=50),
                                              dict(label='97675', count=10),
                                              dict(label='1990', count=20),
                                              dict(label='1995', count=5),
                                              dict(label='2009', count=30),
                                              dict(label='2001', count=10),
                                              dict(label='2011', count=25)])]

            expected_born_data = [dict(categories=[dict(label='0-10', count=105),
                                                   dict(label='10-20', count=25),
                                                   dict(label='20-30', count=20)])]

            self.assertEquals(self.org.organize_categories_data('born', born_api_data), expected_born_data)

            self.assertEquals(self.org.organize_categories_data('registration', [dict(categories=[])]),
                              [dict(categories=[{'count': 0, 'label': '03/24/14'}, {'count': 0, 'label': '03/31/14'},
                                                {'count': 0, 'label': '04/07/14'}, {'count': 0, 'label': '04/14/14'},
                                                {'count': 0, 'label': '04/21/14'}, {'count': 0, 'label': '04/28/14'},
                                                {'count': 0, 'label': '05/05/14'}, {'count': 0, 'label': '05/12/14'},
                                                {'count': 0, 'label': '05/19/14'}, {'count': 0, 'label': '05/26/14'},
                                                {'count': 0, 'label': '06/02/14'}, {'count': 0, 'label': '06/09/14'},
                                                {'count': 0, 'label': '06/16/14'}, {'count': 0, 'label': '06/23/14'},
                                                {'count': 0, 'label': '06/30/14'}, {'count': 0, 'label': '07/07/14'},
                                                {'count': 0, 'label': '07/14/14'}, {'count': 0, 'label': '07/21/14'},
                                                {'count': 0, 'label': '07/28/14'}, {'count': 0, 'label': '08/04/14'},
                                                {'count': 0, 'label': '08/11/14'}, {'count': 0, 'label': '08/18/14'},
                                                {'count': 0, 'label': '08/25/14'}, {'count': 0, 'label': '09/01/14'},
                                                {'count': 0, 'label': '09/08/14'}, {'count': 0, 'label': '09/15/14'},
                                                {'count': 0, 'label': '09/22/14'}])])
            with self.assertRaises(ValueError):
                self.org.organize_categories_data('registration',
                                                  [dict(categories=[dict(label='26-9-2013 21:30', count=20)])])

            self.assertEquals(self.org.organize_categories_data('registration',
                                                                [dict(categories=[dict(label='2013-09-26T21:30:00Z',
                                                                                       count=20)])]),
                              [dict(categories=[{'count': 0, 'label': '03/24/14'}, {'count': 0, 'label': '03/31/14'},
                                                {'count': 0, 'label': '04/07/14'}, {'count': 0, 'label': '04/14/14'},
                                                {'count': 0, 'label': '04/21/14'}, {'count': 0, 'label': '04/28/14'},
                                                {'count': 0, 'label': '05/05/14'}, {'count': 0, 'label': '05/12/14'},
                                                {'count': 0, 'label': '05/19/14'}, {'count': 0, 'label': '05/26/14'},
                                                {'count': 0, 'label': '06/02/14'}, {'count': 0, 'label': '06/09/14'},
                                                {'count': 0, 'label': '06/16/14'}, {'count': 0, 'label': '06/23/14'},
                                                {'count': 0, 'label': '06/30/14'}, {'count': 0, 'label': '07/07/14'},
                                                {'count': 0, 'label': '07/14/14'}, {'count': 0, 'label': '07/21/14'},
                                                {'count': 0, 'label': '07/28/14'}, {'count': 0, 'label': '08/04/14'},
                                                {'count': 0, 'label': '08/11/14'}, {'count': 0, 'label': '08/18/14'},
                                                {'count': 0, 'label': '08/25/14'}, {'count': 0, 'label': '09/01/14'},
                                                {'count': 0, 'label': '09/08/14'}, {'count': 0, 'label': '09/15/14'},
                                                {'count': 0, 'label': '09/22/14'}])])

            self.assertEquals(self.org.organize_categories_data('registration',
                                                                [dict(categories=[dict(label='2014-03-31T21:30:00Z',
                                                                                       count=20)])]),
                              [dict(categories=[{'count': 0, 'label': '03/24/14'}, {'count': 20, 'label': '03/31/14'},
                                                {'count': 0, 'label': '04/07/14'}, {'count': 0, 'label': '04/14/14'},
                                                {'count': 0, 'label': '04/21/14'}, {'count': 0, 'label': '04/28/14'},
                                                {'count': 0, 'label': '05/05/14'}, {'count': 0, 'label': '05/12/14'},
                                                {'count': 0, 'label': '05/19/14'}, {'count': 0, 'label': '05/26/14'},
                                                {'count': 0, 'label': '06/02/14'}, {'count': 0, 'label': '06/09/14'},
                                                {'count': 0, 'label': '06/16/14'}, {'count': 0, 'label': '06/23/14'},
                                                {'count': 0, 'label': '06/30/14'}, {'count': 0, 'label': '07/07/14'},
                                                {'count': 0, 'label': '07/14/14'}, {'count': 0, 'label': '07/21/14'},
                                                {'count': 0, 'label': '07/28/14'}, {'count': 0, 'label': '08/04/14'},
                                                {'count': 0, 'label': '08/11/14'}, {'count': 0, 'label': '08/18/14'},
                                                {'count': 0, 'label': '08/25/14'}, {'count': 0, 'label': '09/01/14'},
                                                {'count': 0, 'label': '09/08/14'}, {'count': 0, 'label': '09/15/14'},
                                                {'count': 0, 'label': '09/22/14'}])])

            self.assertEquals(self.org.organize_categories_data('registration',
                                                                [dict(categories=[dict(label='2014-03-31T21:30:00Z',
                                                                                       count=20),
                                                                                  dict(label='2014-04-03T20:54:00Z',
                                                                                       count=15)])]),
                              [dict(categories=[{'count': 0, 'label': '03/24/14'}, {'count': 35, 'label': '03/31/14'},
                                                {'count': 0, 'label': '04/07/14'}, {'count': 0, 'label': '04/14/14'},
                                                {'count': 0, 'label': '04/21/14'}, {'count': 0, 'label': '04/28/14'},
                                                {'count': 0, 'label': '05/05/14'}, {'count': 0, 'label': '05/12/14'},
                                                {'count': 0, 'label': '05/19/14'}, {'count': 0, 'label': '05/26/14'},
                                                {'count': 0, 'label': '06/02/14'}, {'count': 0, 'label': '06/09/14'},
                                                {'count': 0, 'label': '06/16/14'}, {'count': 0, 'label': '06/23/14'},
                                                {'count': 0, 'label': '06/30/14'}, {'count': 0, 'label': '07/07/14'},
                                                {'count': 0, 'label': '07/14/14'}, {'count': 0, 'label': '07/21/14'},
                                                {'count': 0, 'label': '07/28/14'}, {'count': 0, 'label': '08/04/14'},
                                                {'count': 0, 'label': '08/11/14'}, {'count': 0, 'label': '08/18/14'},
                                                {'count': 0, 'label': '08/25/14'}, {'count': 0, 'label': '09/01/14'},
                                                {'count': 0, 'label': '09/08/14'}, {'count': 0, 'label': '09/15/14'},
                                                {'count': 0, 'label': '09/22/14'}])])

            self.assertEquals(self.org.organize_categories_data('registration',
                                                                [dict(categories=[dict(label='2014-03-31T21:30:00Z',
                                                                                       count=20),
                                                                                  dict(label='2014-04-03T20:54:00Z',
                                                                                       count=15),
                                                                                  dict(label='2014-04-08T18:43:00Z',
                                                                                       count=10)])]),
                              [dict(categories=[{'count': 0, 'label': '03/24/14'}, {'count': 35, 'label': '03/31/14'},
                                                {'count': 10, 'label': '04/07/14'}, {'count': 0, 'label': '04/14/14'},
                                                {'count': 0, 'label': '04/21/14'}, {'count': 0, 'label': '04/28/14'},
                                                {'count': 0, 'label': '05/05/14'}, {'count': 0, 'label': '05/12/14'},
                                                {'count': 0, 'label': '05/19/14'}, {'count': 0, 'label': '05/26/14'},
                                                {'count': 0, 'label': '06/02/14'}, {'count': 0, 'label': '06/09/14'},
                                                {'count': 0, 'label': '06/16/14'}, {'count': 0, 'label': '06/23/14'},
                                                {'count': 0, 'label': '06/30/14'}, {'count': 0, 'label': '07/07/14'},
                                                {'count': 0, 'label': '07/14/14'}, {'count': 0, 'label': '07/21/14'},
                                                {'count': 0, 'label': '07/28/14'}, {'count': 0, 'label': '08/04/14'},
                                                {'count': 0, 'label': '08/11/14'}, {'count': 0, 'label': '08/18/14'},
                                                {'count': 0, 'label': '08/25/14'}, {'count': 0, 'label': '09/01/14'},
                                                {'count': 0, 'label': '09/08/14'}, {'count': 0, 'label': '09/15/14'},
                                                {'count': 0, 'label': '09/22/14'}])])

            self.assertEquals(self.org.organize_categories_data('registration',
                                                                [dict(categories=[dict(label='2014-03-31T21:30:00Z',
                                                                                       count=20),
                                                                 dict(label='2014-04-03T20:54:00Z',  count=15),
                                                                 dict(label='2014-04-08T18:43:00Z', count=10),
                                                                 dict(label='2014-10-10T12:54:00Z', count=100)])]),
                              [dict(categories=[{'count': 0, 'label': '03/24/14'}, {'count': 35, 'label': '03/31/14'},
                                                {'count': 10, 'label': '04/07/14'}, {'count': 0, 'label': '04/14/14'},
                                                {'count': 0, 'label': '04/21/14'}, {'count': 0, 'label': '04/28/14'},
                                                {'count': 0, 'label': '05/05/14'}, {'count': 0, 'label': '05/12/14'},
                                                {'count': 0, 'label': '05/19/14'}, {'count': 0, 'label': '05/26/14'},
                                                {'count': 0, 'label': '06/02/14'}, {'count': 0, 'label': '06/09/14'},
                                                {'count': 0, 'label': '06/16/14'}, {'count': 0, 'label': '06/23/14'},
                                                {'count': 0, 'label': '06/30/14'}, {'count': 0, 'label': '07/07/14'},
                                                {'count': 0, 'label': '07/14/14'}, {'count': 0, 'label': '07/21/14'},
                                                {'count': 0, 'label': '07/28/14'}, {'count': 0, 'label': '08/04/14'},
                                                {'count': 0, 'label': '08/11/14'}, {'count': 0, 'label': '08/18/14'},
                                                {'count': 0, 'label': '08/25/14'}, {'count': 0, 'label': '09/01/14'},
                                                {'count': 0, 'label': '09/08/14'}, {'count': 0, 'label': '09/15/14'},
                                                {'count': 0, 'label': '09/22/14'}])])

            # support parsing of label from datetime fields
            self.assertEquals(self.org.organize_categories_data('registration',
                                                                [dict(categories=[dict(label='2014-03-31T21:30:00Z',
                                                                                       count=20),
                                                                                  dict(label='2014-04-03T20:54:00Z',
                                                                                       count=15),
                                                                                  dict(label='2014-04-08T18:43:00Z',
                                                                                       count=10),
                                                                                  dict(label='2014-10-10T12:54:00Z',
                                                                                       count=100)])]),
                              [dict(categories=[{'count': 0, 'label': '03/24/14'}, {'count': 35, 'label': '03/31/14'},
                                                {'count': 10, 'label': '04/07/14'}, {'count': 0, 'label': '04/14/14'},
                                                {'count': 0, 'label': '04/21/14'}, {'count': 0, 'label': '04/28/14'},
                                                {'count': 0, 'label': '05/05/14'}, {'count': 0, 'label': '05/12/14'},
                                                {'count': 0, 'label': '05/19/14'}, {'count': 0, 'label': '05/26/14'},
                                                {'count': 0, 'label': '06/02/14'}, {'count': 0, 'label': '06/09/14'},
                                                {'count': 0, 'label': '06/16/14'}, {'count': 0, 'label': '06/23/14'},
                                                {'count': 0, 'label': '06/30/14'}, {'count': 0, 'label': '07/07/14'},
                                                {'count': 0, 'label': '07/14/14'}, {'count': 0, 'label': '07/21/14'},
                                                {'count': 0, 'label': '07/28/14'}, {'count': 0, 'label': '08/04/14'},
                                                {'count': 0, 'label': '08/11/14'}, {'count': 0, 'label': '08/18/14'},
                                                {'count': 0, 'label': '08/25/14'}, {'count': 0, 'label': '09/01/14'},
                                                {'count': 0, 'label': '09/08/14'}, {'count': 0, 'label': '09/15/14'},
                                                {'count': 0, 'label': '09/22/14'}])])

            self.assertEquals(self.org.organize_categories_data('occupation', [dict(categories=[])]),
                              [dict(categories=[])])
            self.assertEquals(self.org.organize_categories_data('occupation',
                                                                [dict(categories=[dict(label='All Responses',
                                                                                       count=20)])]),
                              [dict(categories=[])])
            self.assertEquals(self.org.organize_categories_data('occupation',
                                                                [dict(categories=[dict(label='All Responses', count=20),
                                                                                  dict(label='Student', count=50)])]),
                              [dict(categories=[dict(label='Student', count=50)])])

            self.assertEquals(self.org.organize_categories_data('occupation',
                                                                [dict(categories=[dict(label='Student', count=500),
                                                                                  dict(label='Player', count=300),
                                                                                  dict(label='Journalist', count=50),
                                                                                  dict(label='Actor', count=30),
                                                                                  dict(label='Manager', count=150),
                                                                                  dict(label='All Responses', count=20),
                                                                                  dict(label='Teacher', count=10),
                                                                                  dict(label='Officer', count=8),
                                                                                  dict(label='Nurse', count=5),
                                                                                  dict(label='Cameraman', count=5),
                                                                                  dict(label='Writer', count=3),
                                                                                  dict(label='Photographer', count=2),
                                                                                  dict(label='DJ', count=1),
                                                                                  dict(label='Mechanic', count=1),
                                                                                  dict(label='Engineer', count=1),
                                                                                  dict(label='Professor', count=1)])]),


                              [dict(categories=[dict(label='Student', count=500),
                                                dict(label='Player', count=300),
                                                dict(label='Journalist', count=50),
                                                dict(label='Actor', count=30),
                                                dict(label='Manager', count=150),
                                                dict(label='Teacher', count=10),
                                                dict(label='Officer', count=8),
                                                dict(label='Nurse', count=5),
                                                dict(label='Cameraman', count=5)
                                                ])])

    def test_reporter_group(self):
        self.clear_cache()
        with patch("ureport.utils.datetime_to_ms") as mock_datetime_ms:
            mock_datetime_ms.return_value = 500

            with patch('dash.orgs.models.TembaClient.get_groups') as mock:
                group_dict = dict(uuid="group-uuid", name="reporters", size=25)
                mock.return_value = Group.deserialize_list([group_dict])

                with patch('django.core.cache.cache.set') as cache_set_mock:
                    cache_set_mock.return_value = "Set"

                    with patch('django.core.cache.cache.delete') as cache_delete_mock:
                        cache_delete_mock.return_value = "Deleted"

                        fetch_reporter_group(self.org)
                        self.assertFalse(mock.called)
                        self.assertFalse(cache_set_mock.called)
                        self.assertEqual(self.org.get_reporter_group(), dict())

                        self.org.set_config("reporter_group", "reporters")

                        fetch_reporter_group(self.org)
                        mock.assert_called_with(name='reporters')

                        key = CACHE_ORG_REPORTER_GROUP_KEY % (self.org.pk, "reporters")
                        cache_set_mock.assert_called_with(key,
                                                          {'time': 500, 'results': group_dict},
                                                          UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME)

                        cache_delete_mock.assert_called_with(GLOBAL_COUNT_CACHE_KEY)

                        with patch('django.core.cache.cache.get') as cache_get_mock:
                            cache_get_mock.return_value = {'time': 500, 'results': group_dict}

                            self.assertEqual(get_reporter_group(self.org), group_dict)

    def test_fetch_poll_results(self):
        with self.settings(CACHES = {'default': {'BACKEND': 'redis_cache.cache.RedisCache',
                                                 'LOCATION': '127.0.0.1:6379:1',
                                                 'OPTIONS': {
                                                     'CLIENT_CLASS': 'redis_cache.client.DefaultClient',
                                                 }
                                                 }}):
            with patch('ureport.polls.models.Poll.fetch_poll_results') as mock_poll_model_fetch_results:
                mock_poll_model_fetch_results.return_value = "DONE"

                polls = [self.poll]
                _fetch_org_polls_results(self.org, polls)
                mock_poll_model_fetch_results.assert_called_with()
                mock_poll_model_fetch_results.mock_reset()

            with patch('ureport.polls.models.Poll.get_main_poll') as mock_main_poll:
                mock_main_poll.return_value = self.poll

                fetch_main_poll_results(self.org)
                mock_poll_model_fetch_results.assert_called_once_with()
                mock_poll_model_fetch_results.mock_reset()

            with patch('ureport.polls.models.Poll.get_brick_polls') as mock_brick_polls:
                mock_brick_polls.return_value = [self.poll]

                fetch_brick_polls_results(self.org)
                mock_poll_model_fetch_results.assert_called_once_with()
                mock_poll_model_fetch_results.mock_reset()

            with patch('ureport.polls.models.Poll.get_other_polls') as mock_other_polls:
                mock_other_polls.return_value = [self.poll]

                fetch_other_polls_results(self.org)
                mock_poll_model_fetch_results.assert_called_once_with()
                mock_poll_model_fetch_results.mock_reset()

    def test_fetch_old_sites_count(self):
        self.clear_cache()
        with patch("ureport.utils.datetime_to_ms") as mock_datetime_ms:
            mock_datetime_ms.return_value = 500

            with patch('requests.get') as mock_get:
                mock_get.side_effect = [MockResponse(200, '300'), MockResponse(200, '50\n')]

                with patch('django.core.cache.cache.set') as cache_set_mock:
                    cache_set_mock.return_value = "Set"

                    with patch('django.core.cache.cache.delete') as cache_delete_mock:
                        cache_delete_mock.return_value = "Deleted"

                        fetch_old_sites_count()
                        self.assertEqual(mock_get.call_count, 2)
                        mock_get.assert_any_call('http://ureport.ug/count.txt')
                        mock_get.assert_any_call('http://www.zambiaureport.org/count.txt/')

                        self.assertEqual(cache_set_mock.call_count, 2)
                        cache_set_mock.assert_any_call('org:uganda:reporters:old-site',
                                                       {'time': 500, 'results': dict(size=300)},
                                                       UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME)

                        cache_set_mock.assert_any_call('org:zambia:reporters:old-site',
                                                       {'time': 500, 'results': dict(size=50)},
                                                       UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME)

                        cache_delete_mock.assert_called_once_with(GLOBAL_COUNT_CACHE_KEY)
