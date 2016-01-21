# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from datetime import datetime
from django.utils import timezone

from mock import patch
import pytz
from ureport.contacts.models import ContactField, Contact, ReportersCounter
from ureport.contacts.tasks import fetch_contacts_task
from ureport.locations.models import Boundary
from ureport.tests import DashTest, TembaContactField, MockTembaClient, TembaContact
from temba_client.v1.types import Group as TembaGroup
from ureport.utils import json_date_to_datetime


class ContactFieldTest(DashTest):
    def setUp(self):
        super(ContactFieldTest, self).setUp()
        self.nigeria = self.create_org('nigeria', self.admin)

    def test_kwargs_from_temba(self):
        temba_contact_field = TembaContactField.create(key='foo', label='Bar', value_type='T')

        kwargs = ContactField.kwargs_from_temba(self.nigeria, temba_contact_field)
        self.assertEqual(kwargs, dict(org=self.nigeria, key='foo', label='Bar', value_type='T'))

        # try creating contact from them
        ContactField.objects.create(**kwargs)

    @patch('dash.orgs.models.TembaClient1', MockTembaClient)
    def test_fetch_contact_fields(self):
        ContactField.objects.create(org=self.nigeria, key='old', label='Old', value_type='T')

        field_keys = ContactField.fetch_contact_fields(self.nigeria)

        self.assertEqual(field_keys, ['occupation'])

        self.assertIsNone(ContactField.objects.filter(key='old', org=self.nigeria).first())

        contact_field = ContactField.objects.get()

        self.assertEqual(contact_field.org, self.nigeria)
        self.assertEqual(contact_field.key, 'occupation')
        self.assertEqual(contact_field.label, 'Activité')
        self.assertEqual(contact_field.value_type, 'T')

    @patch('dash.orgs.models.TembaClient1', MockTembaClient)
    def test_get_contact_fields(self):

        field_keys = ContactField.get_contact_fields(self.nigeria)
        self.assertEqual(field_keys, ['occupation'])

        with patch('django.core.cache.cache.get') as cache_get_mock:
            cache_get_mock.return_value = None

            field_keys = ContactField.get_contact_fields(self.nigeria)
            self.assertEqual(field_keys, ['occupation'])

            cache_get_mock.return_value = ['occupation']
            with patch('ureport.contacts.models.ContactField.fetch_contact_fields') as mock_fetch:

                ContactField.get_contact_fields(self.nigeria)
                self.assertFalse(mock_fetch.called)


class ContactTest(DashTest):
    def setUp(self):
        super(ContactTest, self).setUp()
        self.nigeria = self.create_org('nigeria', self.admin)
        self.nigeria.set_config('reporter_group', "Ureporters")
        self.nigeria.set_config('registration_label', "Registration Date")
        self.nigeria.set_config('state_label', "State")
        self.nigeria.set_config('district_label', "LGA")
        self.nigeria.set_config('occupation_label', "Activité")
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

        self.registration_date = ContactField.objects.create(org=self.nigeria, key='registration_date',
                                                             label='Registration Date', value_type='T')

        self.state_field = ContactField.objects.create(org=self.nigeria, key='state', label='State', value_type='S')
        self.district_field = ContactField.objects.create(org=self.nigeria, key='lga', label='LGA', value_type='D')
        self.occupation_field = ContactField.objects.create(org=self.nigeria, key='occupation', label='Activité',
                                                            value_type='T')

        self.born_field = ContactField.objects.create(org=self.nigeria, key='born', label='Born', value_type='T')
        self.gender_field = ContactField.objects.create(org=self.nigeria, key='gender', label='Gender', value_type='T')

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

    def test_fetch_contacts(self):
        self.nigeria.set_config('reporter_group', 'Reporters')

        tz = pytz.timezone('UTC')
        with patch.object(timezone, 'now', return_value=tz.localize(datetime(2015, 9, 29, 10, 20, 30, 40))):

            with patch('dash.orgs.models.TembaClient1.get_groups') as mock_groups:
                group = TembaGroup.create(uuid="uuid-8", name='reporters', size=120)
                mock_groups.return_value = [group]

                with patch('dash.orgs.models.TembaClient1.get_contacts') as mock_contacts:
                    mock_contacts.return_value = [
                        TembaContact.create(uuid='000-001', name="Ann", urns=['tel:1234'], groups=['000-002'],
                                            fields=dict(state="Lagos", lga="Oyo", gender='Female', born="1990"),
                                            language='eng',
                                            modified_on=datetime(2015, 9, 20, 10, 20, 30, 400000, pytz.utc))]

                    seen_uuids = Contact.fetch_contacts(self.nigeria)

                    self.assertEqual(seen_uuids, [])

                group = TembaGroup.create(uuid="000-002", name='reporters', size=120)
                mock_groups.return_value = [group]

                with patch('dash.orgs.models.TembaClient1.get_contacts') as mock_contacts:
                    mock_contacts.return_value = [
                        TembaContact.create(uuid='000-001', name="Ann",urns=['tel:1234'], groups=['000-002'],
                                            fields=dict(state="Lagos", lga="Oyo",gender='Female', born="1990"),
                                            language='eng',
                                            modified_on=datetime(2015, 9, 20, 10, 20, 30, 400000, pytz.utc))]

                    seen_uuids = Contact.fetch_contacts(self.nigeria)
                    self.assertTrue('000-001' in seen_uuids)

                    contact = Contact.objects.get()
                    self.assertEqual(contact.uuid, '000-001')
                    self.assertEqual(contact.org, self.nigeria)
                    self.assertEqual(contact.state, 'R-LAGOS')
                    self.assertEqual(contact.district, 'R-OYO')
                    self.assertEqual(contact.gender, 'F')
                    self.assertEqual(contact.born, 1990)

                    Contact.fetch_contacts(self.nigeria, after=datetime(2014, 12, 01, 22, 34, 36, 123000, pytz.utc))
                    self.assertTrue('000-001' in seen_uuids)

                # delete the contacts
                Contact.objects.all().delete()

                group1 = TembaGroup.create(uuid="000-001", name='reporters too', size=10)
                group2 = TembaGroup.create(uuid="000-002", name='reporters', size=120)
                mock_groups.return_value = [group1, group2]

                with patch('dash.orgs.models.TembaClient1.get_contacts') as mock_contacts:
                    mock_contacts.return_value = [
                        TembaContact.create(uuid='000-001', name="Ann",urns=['tel:1234'], groups=['000-002'],
                                            fields=dict(state="Lagos", lga="Oyo",gender='Female', born="1990"),
                                            language='eng',
                                            modified_on=datetime(2015, 9, 20, 10, 20, 30, 400000, pytz.utc))]

                    seen_uuids = Contact.fetch_contacts(self.nigeria)
                    self.assertTrue('000-001' in seen_uuids)

                    contact = Contact.objects.get()
                    self.assertEqual(contact.uuid, '000-001')
                    self.assertEqual(contact.org, self.nigeria)
                    self.assertEqual(contact.state, 'R-LAGOS')
                    self.assertEqual(contact.district, 'R-OYO')
                    self.assertEqual(contact.gender, 'F')
                    self.assertEqual(contact.born, 1990)

                    Contact.fetch_contacts(self.nigeria, after=datetime(2014, 12, 01, 22, 34, 36, 123000, pytz.utc))
                    self.assertTrue('000-001' in seen_uuids)


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

    @patch('dash.orgs.models.TembaClient1', MockTembaClient)
    def test_tasks(self):

        with self.settings(CACHES={'default': {'BACKEND': 'redis_cache.cache.RedisCache',
                                               'LOCATION': '127.0.0.1:6379:1',
                                               'OPTIONS': {'CLIENT_CLASS': 'redis_cache.client.DefaultClient'}
                                               }}):
            with patch('ureport.contacts.tasks.Contact.fetch_contacts') as mock_fetch_contacts:
                with patch('ureport.contacts.tasks.Boundary.fetch_boundaries') as mock_fetch_boundaries:
                    with patch('ureport.contacts.tasks.ContactField.fetch_contact_fields') as mock_fetch_contact_fields:

                        mock_fetch_contacts.return_value = 'FETCHED'
                        mock_fetch_boundaries.return_value = 'FETCHED'
                        mock_fetch_contact_fields.return_value = 'FETCHED'

                        fetch_contacts_task(self.nigeria.pk, True)
                        mock_fetch_contacts.assert_called_once_with(self.nigeria, after=None)
                        mock_fetch_boundaries.assert_called_with(self.nigeria)
                        mock_fetch_contact_fields.assert_called_with(self.nigeria)
                        self.assertEqual(mock_fetch_boundaries.call_count, 2)
                        self.assertEqual(mock_fetch_contact_fields.call_count, 2)

                        mock_fetch_contacts.reset_mock()
                        mock_fetch_boundaries.reset_mock()
                        mock_fetch_contact_fields.reset_mock()

                        with patch('django.core.cache.cache.get') as cache_get_mock:
                            date_str = '2014-01-02T01:04:05.000Z'
                            d1 = json_date_to_datetime(date_str)

                            cache_get_mock.return_value = date_str

                            fetch_contacts_task(self.nigeria.pk)
                            mock_fetch_contacts.assert_called_once_with(self.nigeria, after=d1)
                            self.assertFalse(mock_fetch_boundaries.called)
                            self.assertFalse(mock_fetch_contact_fields.called)
