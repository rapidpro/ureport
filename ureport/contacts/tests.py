# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from mock import patch
from ureport.contacts.models import ContactField
from ureport.tests import DashTest, TembaContactField, MockTembaClient


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

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
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

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
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

