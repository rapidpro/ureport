from datetime import datetime
import json
from dash.categories.models import Category
from dash_test_runner.tests import MockResponse
from django.utils import timezone
from mock import patch
import pycountry
import pytz
import redis
from temba_client.v1.types import Group
from ureport.assets.models import FLAG, Image
from ureport.contacts.models import ReportersCounter
from ureport.locations.models import Boundary
from ureport.polls.models import CACHE_ORG_REPORTER_GROUP_KEY, UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME, Poll, \
    CACHE_ORG_FLOWS_KEY
from ureport.tests import DashTest
from ureport.utils import get_linked_orgs,  clean_global_results_data, fetch_old_sites_count, \
    get_gender_stats, get_age_stats, get_registration_stats, get_ureporters_locations_stats, get_reporters_count, \
    get_occupation_stats, get_regions_stats, get_org_contacts_counts, ORG_CONTACT_COUNT_KEY, get_flows
from ureport.utils import datetime_to_json_date, json_date_to_datetime
from ureport.utils import get_global_count, fetch_main_poll_results, fetch_brick_polls_results, GLOBAL_COUNT_CACHE_KEY
from ureport.utils import fetch_other_polls_results, _fetch_org_polls_results


class UtilsTest(DashTest):

    def setUp(self):
        super(UtilsTest, self).setUp()
        self.org = self.create_org("burundi", self.admin)

        self.education = Category.objects.create(org=self.org,
                                                 name="Education",
                                                 created_by=self.admin,
                                                 modified_by=self.admin)

        self.poll = self.create_poll(self.org, "Poll 1", "uuid-1", self.education, self.admin)

    def clear_cache(self):
        # hardcoded to localhost
        r = redis.StrictRedis(host='localhost', db=1)
        r.flushdb()

    def test_datetime_to_json_date(self):
        d1 = datetime(2014, 1, 2, 3, 4, 5, tzinfo=pytz.utc)
        self.assertEqual(datetime_to_json_date(d1), '2014-01-02T03:04:05.000Z')
        self.assertEqual(json_date_to_datetime('2014-01-02T03:04:05.000Z'), d1)
        self.assertEqual(json_date_to_datetime('2014-01-02T03:04:05.000'), d1)

        tz = pytz.timezone("Africa/Kigali")
        d2 = tz.localize(datetime(2014, 1, 2, 3, 4, 5))
        self.assertEqual(datetime_to_json_date(d2), '2014-01-02T01:04:05.000Z')
        self.assertEqual(json_date_to_datetime('2014-01-02T01:04:05.000Z'), d2.astimezone(pytz.utc))
        self.assertEqual(json_date_to_datetime('2014-01-02T01:04:05.000'), d2.astimezone(pytz.utc))

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

                        old_site_values = fetch_old_sites_count()
                        self.assertEqual(old_site_values, [{'time': 500, 'results': dict(size=300)},
                                                           {'time': 500, 'results': dict(size=50)}])
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

    def test_get_gender_stats(self):

        self.assertEqual(get_gender_stats(self.org), dict(female_count=0, female_percentage="---",
                                                          male_count=0, male_percentage="---"))

        ReportersCounter.objects.create(org=self.org, type='gender:f', count=2)
        ReportersCounter.objects.create(org=self.org, type='gender:m', count=2)
        ReportersCounter.objects.create(org=self.org, type='gender:m', count=1)

        self.assertEqual(get_gender_stats(self.org), dict(female_count=2, female_percentage="40%",
                                                          male_count=3, male_percentage="60%"))

    def test_get_age_stats(self):

        expected = [dict(name='0-14', y=0), dict(name='15-19', y=0), dict(name='20-24', y=0),
                    dict(name='25-30', y=0), dict(name='31-34', y=0), dict(name='35+', y=0)]

        self.assertEqual(get_age_stats(self.org), json.dumps(expected))

        now = timezone.now()
        now_year = now.year

        two_years_ago = now_year - 2
        five_years_ago = now_year - 5
        twelve_years_ago = now_year - 12
        fifteen_years_ago = now_year - 15
        seventeen_years_ago = now_year - 17
        nineteen_years_ago = now_year - 19
        twenty_years_ago = now_year - 20
        thirty_years_ago = now_year - 30
        thirty_one_years_ago = now_year - 31
        forthy_five_years_ago = now_year - 45

        ReportersCounter.objects.create(org=self.org, type='born:%s' % two_years_ago, count=2)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % five_years_ago, count=1)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % twelve_years_ago, count=3)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % twelve_years_ago, count=2)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % fifteen_years_ago, count=25)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % seventeen_years_ago, count=40)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % nineteen_years_ago, count=110)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % twenty_years_ago, count=2)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % thirty_years_ago, count=12)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % thirty_one_years_ago, count=2)
        ReportersCounter.objects.create(org=self.org, type='born:%s' % forthy_five_years_ago, count=2)

        ReportersCounter.objects.create(org=self.org, type='born:10', count=10)
        ReportersCounter.objects.create(org=self.org, type='born:732837', count=20)

        # y is the percentage of count over the total count
        expected = [dict(name='0-14', y=4), dict(name='15-19', y=87), dict(name='20-24', y=1),
                    dict(name='25-30', y=6), dict(name='31-34', y=1), dict(name='35+', y=1)]

        self.assertEqual(get_age_stats(self.org), json.dumps(expected))

    def test_get_registration_stats(self):

        tz = pytz.timezone('UTC')
        with patch.object(timezone, 'now', return_value=tz.localize(datetime(2015, 9, 4, 3, 4, 5, 6))):

            stats = json.loads(get_registration_stats(self.org))

            for entry in stats:
                self.assertEqual(entry['count'], 0)

            ReportersCounter.objects.create(org=self.org, type='registered_on:2015-08-27', count=3)
            ReportersCounter.objects.create(org=self.org, type='registered_on:2015-08-25', count=2)
            ReportersCounter.objects.create(org=self.org, type='registered_on:2015-08-25', count=3)
            ReportersCounter.objects.create(org=self.org, type='registered_on:2015-08-25', count=1)
            ReportersCounter.objects.create(org=self.org, type='registered_on:2015-06-30', count=2)
            ReportersCounter.objects.create(org=self.org, type='registered_on:2015-06-30', count=2)
            ReportersCounter.objects.create(org=self.org, type='registered_on:2014-11-25', count=6)

            stats = json.loads(get_registration_stats(self.org))

            non_zero_keys = {'08/24/15': 9, '06/29/15': 4}

            for entry in stats:
                self.assertFalse(entry['label'].endswith('14'))
                if entry['count'] != 0:
                    self.assertTrue(entry['label'] in non_zero_keys.keys())
                    self.assertEqual(entry['count'], non_zero_keys[entry['label']])

    def test_get_ureporters_locations_stats(self):

        self.assertEqual(get_ureporters_locations_stats(self.org, dict()), [])
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location='map')), [])
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location='state')), [])
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location='district')), [])

        self.country = Boundary.objects.create(org=self.org, osm_id="R-COUNTRY", name="Country", level=0, parent=None,
                                               geometry='{"foo":"bar-country"}')
        self.state = Boundary.objects.create(org=self.org, osm_id="R-STATE", name="State", level=1,
                                             parent=self.country, geometry='{"foo":"bar-state"}')
        self.city = Boundary.objects.create(org=self.org, osm_id="R-CITY", name="City", level=1,
                                            parent=self.country, geometry='{"foo":"bar-city"}')
        self.district = Boundary.objects.create(org=self.org, osm_id="R-DISTRICT", name="District", level=2,
                                                parent=self.state, geometry='{"foo":"bar-district"}')

        ReportersCounter.objects.create(org=self.org, type='state:R-STATE', count=5)
        ReportersCounter.objects.create(org=self.org, type='district:R-DISTRICT', count=3)

        self.assertEqual(get_ureporters_locations_stats(self.org, dict()), [])
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location='map')), [])
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location='state')),
                         [dict(boundary='R-CITY', label='City', set=0), dict(boundary='R-STATE', label='State', set=5)])

        # district without parent
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location='district')), [])

        # district with wrong parent
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location='district', parent='BLABLA')), [])

        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location='district', parent='R-STATE')),
                         [dict(boundary='R-DISTRICT', label='District', set=3)])

    def test_get_regions_stats(self):

        self.assertEqual(get_regions_stats(self.org), [])

        Boundary.objects.create(org=self.org, osm_id='R-NIGERIA', name='Nigeria', parent=None, level=0,
                                geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        Boundary.objects.create(org=self.org, osm_id='R-LAGOS', name='Lagos', parent=None, level=1,
                                geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        Boundary.objects.create(org=self.org, osm_id='R-OYO', name='OYO', parent=None, level=1,
                                geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        Boundary.objects.create(org=self.org, osm_id='R-ABUJA', name='Abuja', parent=None, level=1,
                                geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        self.assertEqual(get_regions_stats(self.org), [])

        ReportersCounter.objects.create(org=self.org, type='state:R-LAGOS', count=5)

        self.assertEqual(get_regions_stats(self.org), [dict(name='Lagos', count=5)])

        ReportersCounter.objects.create(org=self.org, type='state:R-OYO', count=15)

        self.assertEqual(get_regions_stats(self.org), [dict(name='OYO', count=15), dict(name='Lagos', count=5)])

        self.org.set_config('is_global', True)

        self.assertEqual(get_regions_stats(self.org), [])

        ReportersCounter.objects.create(org=self.org, type='state:R-NIGERIA', count=30)
        self.assertEqual(get_regions_stats(self.org), [dict(name='Nigeria', count=30)])

    def test_get_org_contacts_counts(self):

        with patch('ureport.contacts.models.ReportersCounter.get_counts') as mock_get_counts:
            mock_get_counts.return_value = "Counts"
            with patch('django.core.cache.cache.get') as mock_cache_get:
                mock_cache_get.return_value = "Cached"

                self.assertEqual(get_org_contacts_counts(self.org), "Cached")
                mock_cache_get.assert_called_once_with(ORG_CONTACT_COUNT_KEY % self.org.pk, None)
                self.assertFalse(mock_get_counts.called)

                mock_cache_get.return_value = None

                self.assertEqual(get_org_contacts_counts(self.org), "Counts")
                mock_get_counts.assert_called_once_with(self.org)

    def test_get_flows(self):
        with patch('ureport.utils.fetch_flows') as mock_fetch_flows:
            mock_fetch_flows.return_value = "Fetched"
            with patch('django.core.cache.cache.get') as mock_cache_get:
                mock_cache_get.return_value = dict(results="Cached")

                self.assertEqual(get_flows(self.org), "Cached")
                mock_cache_get.assert_called_once_with(CACHE_ORG_FLOWS_KEY % self.org.pk, None)
                self.assertFalse(mock_fetch_flows.called)

                mock_cache_get.return_value = None
                self.assertEqual(get_flows(self.org), "Fetched")
                mock_fetch_flows.assert_called_once_with(self.org)

    def test_get_reporters_count(self):

        self.assertEqual(get_reporters_count(self.org), 0)

        ReportersCounter.objects.create(org=self.org, type='total-reporters', count=5)

        self.assertEqual(get_reporters_count(self.org), 5)

    def test_get_global_count(self):
        with self.settings(CACHES = {'default': {'BACKEND': 'redis_cache.cache.RedisCache',
                                                 'LOCATION': '127.0.0.1:6379:1',
                                                 'OPTIONS': {
                                                     'CLIENT_CLASS': 'redis_cache.client.DefaultClient',
                                                 }
                                                 }}):

            with patch('ureport.utils.fetch_old_sites_count') as mock_old_sites_count:
                mock_old_sites_count.return_value = []

                self.assertEqual(get_global_count(), 0)

                ReportersCounter.objects.create(org=self.org, type='total-reporters', count=5)

                # ignored if not on the global homepage
                self.assertEqual(get_global_count(), 0)

                # add the org to the homepage
                self.org.set_config('is_on_landing_page', True)
                self.assertEqual(get_global_count(), 5)

                mock_old_sites_count.return_value = [{'time': 500, 'results': dict(size=300)},
                                                     {'time': 500, 'results': dict(size=50)}]
                from django.core.cache import cache
                cache.delete(GLOBAL_COUNT_CACHE_KEY)
                self.assertEqual(get_global_count(), 355)

                cache.delete(GLOBAL_COUNT_CACHE_KEY)
                self.org.set_config('is_on_landing_page', False)
                self.assertEqual(get_global_count(), 350)

            with patch('django.core.cache.cache.get') as cache_get_mock:
                cache_get_mock.return_value = 20

                self.assertEqual(get_global_count(), 20)
                cache_get_mock.assert_called_once_with('global_count', None)

    def test_get_occupation_stats(self):

        self.assertEqual(get_occupation_stats(self.org), '[]')

        ReportersCounter.objects.create(org=self.org, type='occupation:student', count=5)
        ReportersCounter.objects.create(org=self.org, type='occupation:writer', count=2)
        ReportersCounter.objects.create(org=self.org, type='occupation:all responses', count=13)

        self.assertEqual(get_occupation_stats(self.org), json.dumps([dict(label='student', count=5),
                                                                     dict(label='writer', count=2)]))

        ReportersCounter.objects.create(org=self.org, type='occupation:fooAAA', count=1)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooBBB', count=1)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooCCC', count=10)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooDDD', count=11)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooEEE', count=12)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooFFF', count=13)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooGGG', count=8)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooGGG', count=6)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooHHH', count=15)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooIII', count=16)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooJJJ', count=2)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooJJJ', count=15)
        ReportersCounter.objects.create(org=self.org, type='occupation:fooKKK', count=18)

        self.assertEqual(get_occupation_stats(self.org), json.dumps([dict(label='fooKKK', count=18),
                                                                     dict(label='fooJJJ', count=17),
                                                                     dict(label='fooIII', count=16),
                                                                     dict(label='fooHHH', count=15),
                                                                     dict(label='fooGGG', count=14),
                                                                     dict(label='fooFFF', count=13),
                                                                     dict(label='fooEEE', count=12),
                                                                     dict(label='fooDDD', count=11),
                                                                     dict(label='fooCCC', count=10)]))