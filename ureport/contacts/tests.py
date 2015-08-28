from ureport.locations.models import Boundary
from ureport.tests import DashTest, MockTembaClient
from mock import patch
from .models import Contact, ReportersCounter
from temba.types import Contact as TembaContact
from ureport.utils import json_date_to_datetime


class ContactTest(DashTest):
    def setUp(self):
        super(ContactTest, self).setUp()
        self.nigeria = self.create_org('nigeria', self.admin)
        self.nigeria.set_config('reporter_group', "Ureporters")
        self.nigeria.set_config('registration_label', "Registration Date")
        self.nigeria.set_config('state_label', "State")
        self.nigeria.set_config('district_label', "LGA")
        self.nigeria.set_config('occupation_label', "Occupation")
        self.nigeria.set_config('born_label', "Born")
        self.nigeria.set_config('gender_label', 'Gender')
        self.nigeria.set_config('female_label', "Female")
        self.nigeria.set_config('male_label', 'Male')

        # boundaries fetched
        self.country = Boundary.objects.create(org=self.nigeria, osm_id="R-NIGERIA", name="Nigeria", level=0, parent=None,
                                               geometry='{"foo":"bar-country"}')
        self.state = Boundary.objects.create(org=self.nigeria, osm_id="R-LAGOS", name="Lagos", level=1,
                                             parent=self.country, geometry='{"foo":"bar-state"}')
        self.district = Boundary.objects.create(org=self.nigeria, osm_id="R-OYO", name="Oyo", level=2,
                                                parent=self.state, geometry='{"foo":"bar-state"}')

    def test_kwargs_from_temba(self):

        temba_contact = TembaContact.create(uuid='C-006', name="Jan", urns=['tel:123'],
                                            groups=['G-001', 'G-007'],
                                            fields={'registration_date': None, 'state': None,
                                                    'lga': None, 'occupation': None, 'born': None,
                                                    'gender': None},
                                            language='eng')

        kwargs = Contact.kwargs_from_temba(self.nigeria, temba_contact)

        self.assertEqual(kwargs, dict(uuid='C-006', org=self.nigeria, gender='', born=0, occupation='',
                                      registered_on=None, state='', district=''))

        # try creating contact from them
        Contact.objects.create(**kwargs)

        # Invalid boundaries become ''
        temba_contact = TembaContact.create(uuid='C-007', name="Jan", urns=['tel:123'],
                                            groups=['G-001', 'G-007'],
                                            fields={'registration_date': '2014-01-02T03:04:05.000000Z',
                                                    'state': 'Kigali', 'lga': 'Oyo', 'occupation': 'Student',
                                                    'born': '1990', 'gender': 'Male'},
                                            language='eng')

        kwargs = Contact.kwargs_from_temba(self.nigeria, temba_contact)

        self.assertEqual(kwargs, dict(uuid='C-007', org=self.nigeria, gender='M', born=1990, occupation='Student',
                                      registered_on=json_date_to_datetime('2014-01-02T03:04:05.000'), state='',
                                      district=''))

        # try creating contact from them
        Contact.objects.create(**kwargs)


        temba_contact = TembaContact.create(uuid='C-008', name="Jan", urns=['tel:123'],
                                            groups=['G-001', 'G-007'],
                                            fields={'registration_date': '2014-01-02T03:04:05.000000Z', 'state':'Lagos',
                                                    'lga': 'Oyo', 'occupation': 'Student', 'born': '1990',
                                                    'gender': 'Male'},
                                            language='eng')

        kwargs = Contact.kwargs_from_temba(self.nigeria, temba_contact)

        self.assertEqual(kwargs, dict(uuid='C-008', org=self.nigeria, gender='M', born=1990, occupation='Student',
                                      registered_on=json_date_to_datetime('2014-01-02T03:04:05.000'), state='R-LAGOS',
                                      district='R-OYO'))

        # try creating contact from them
        Contact.objects.create(**kwargs)

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
    def test_fetch_contacts(self):
        # contact no longer in ureporters
        Contact.objects.create(uuid='C-OLD', org=self.nigeria, gender='M', born=1985, occupation='Pirate',
                               registered_on=json_date_to_datetime('2014-01-02T03:04:05.000'), state='Lagos',
                               district='Oyo')

        Contact.fetch_contacts(self.nigeria)
        self.assertIsNone(Contact.objects.filter(org=self.nigeria, uuid='C-OLD').first())

        contact = Contact.objects.get()
        self.assertEqual(contact.uuid, '000-001')
        self.assertEqual(contact.org, self.nigeria)
        self.assertEqual(contact.state, 'R-LAGOS')
        self.assertEqual(contact.district, 'R-OYO')
        self.assertEqual(contact.gender, 'F')
        self.assertEqual(contact.born, 1990)

    def test_reporters_counter(self):
        self.assertEqual(ReportersCounter.get_counts(self.nigeria), dict())
        Contact.objects.create(uuid='C-007', org=self.nigeria, gender='M', born=1990, occupation='Student',
                               registered_on=json_date_to_datetime('2014-01-02T03:04:05.000'), state='R-LAGOS',
                               district='R-OYO')

        expected = dict()
        expected['total-reporters'] = 1
        expected['gender:m'] = 1
        expected['occupation:student'] = 1
        expected['born:1990'] = 1
        expected['registered_on:2014-01-02'] = 1
        expected['state:R-LAGOS'] = 1
        expected['district:R-OYO'] = 1

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

        Contact.objects.create(uuid='C-008', org=self.nigeria, gender='M', born=1980, occupation='Teacher',
                               registered_on=json_date_to_datetime('2014-01-02T03:07:05.000'), state='R-LAGOS',
                               district='R-OYO')

        expected = dict()
        expected['total-reporters'] = 2
        expected['gender:m'] = 2
        expected['occupation:student'] = 1
        expected['occupation:teacher'] = 1
        expected['born:1990'] = 1
        expected['born:1980'] = 1
        expected['registered_on:2014-01-02'] = 2
        expected['state:R-LAGOS'] = 2
        expected['district:R-OYO'] = 2

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

