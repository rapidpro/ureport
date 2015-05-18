from datetime import datetime
from django.utils import timezone
from mock import patch
import pycountry
import pytz
import redis
from ureport.tests import DashTest


class UtilsTest(DashTest):

    def setUp(self):
        super(UtilsTest, self).setUp()
        self.org = self.create_org("uganda", self.admin)

    def clear_cache(self):
        # hardcoded to localhost
        r = redis.StrictRedis(host='localhost', db=1)
        r.flushdb()

    def test_get_most_active_regions(self):
        self.org.set_config('gender_label', 'Gender')

        with patch('dash.api.API.get_contact_field_results') as mock:
            mock.return_value = [dict(label='LABEL_1', set=15, unset=5),
                                 dict(label='LABEL_2', set=100, unset=200),
                                 dict(label='LABEL_3', set=50, unset=30)]

            self.assertEquals(self.org.get_most_active_regions(), ['LABEL_2', 'LABEL_3', 'LABEL_1'])
            mock.assert_called_once_with('Gender', dict(location='State'))

        with patch('dash.api.API.get_contact_field_results') as mock:
            self.clear_cache()
            mock.return_value = None

            self.assertEquals(self.org.get_most_active_regions(), [])
            mock.assert_called_once_with('Gender', dict(location='State'))

        self.org.set_config("is_global", True)
        self.org.set_config("state_label", "Province")

        with patch('dash.api.API.get_contact_field_results') as mock:
            mock.return_value = [dict(label='UG', set=15, unset=5),
                                 dict(label='RW', set=100, unset=200),
                                 dict(label='US', set=50, unset=30)]

            self.assertEquals(self.org.get_most_active_regions(), ['Rwanda', 'United States', 'Uganda'])
            segment = dict()
            segment["contact_field"] = "Province"
            segment["values"] = [elt.alpha2 for elt in pycountry.countries.objects]

            mock.assert_called_once_with('Gender', segment)

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

