# coding=utf-8
from __future__ import unicode_literals

import json

from temba_client.v1.types import Boundary as TembaBoundary, Geometry as TembaGeometry
from temba_client.v2.types import Field as TembaField, ObjectRef, Contact as TembaContact

from ureport.backend.rapidpro import FieldSyncer, BoundarySyncer, ContactSyncer
from ureport.contacts.models import ContactField
from ureport.locations.models import Boundary
from ureport.tests import DashTest
from ureport.utils import json_date_to_datetime


class FieldSyncerTest(DashTest):
    def setUp(self):
        super(FieldSyncerTest, self).setUp()
        self.nigeria = self.create_org('nigeria', self.admin)
        self.syncer = FieldSyncer()

    def test_local_kwargs(self):
        kwargs = self.syncer.local_kwargs(self.nigeria, TembaField.create(key='foo', label='Bar', value_type='text'))

        self.assertEqual(kwargs, {'org': self.nigeria, 'key': 'foo', 'label': 'Bar', 'value_type': 'T'})

    def test_update_required(self):
        local = ContactField.objects.create(org=self.nigeria, key='foo', label='Bar', value_type='T')

        self.assertFalse(self.syncer.update_required(local,
                                                     TembaField.create(key='foo', label='Bar', value_type='text')))

        self.assertTrue(self.syncer.update_required(local,
                                                     TembaField.create(key='foo', label='Baz', value_type='text')))

        self.assertTrue(self.syncer.update_required(local,
                                                     TembaField.create(key='foo', label='Bar', value_type='numeric')))

        self.assertTrue(self.syncer.update_required(local,
                                                     TembaField.create(key='foo', label='Baz', value_type='numeric')))


class BoundarySyncerTest(DashTest):

    def setUp(self):
        super(BoundarySyncerTest, self).setUp()
        self.nigeria = self.create_org('nigeria', self.admin)
        self.syncer = BoundarySyncer()

    def test_local_kwargs(self):
        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=['COORDINATES'])
        country = TembaBoundary.create(boundary='R12345', name='Nigeria', parent=None, level=0, geometry=geometry)

        kwargs = self.syncer.local_kwargs(self.nigeria, country)
        self.assertEqual(kwargs, {'org': self.nigeria,
                                  'geometry': json.dumps(dict(type=geometry.type, coordinates=geometry.coordinates)),
                                  'parent': None, 'level': 0,
                                  'name': 'Nigeria', 'osm_id': 'R12345'})

        # try creating an object from the kwargs
        country_boundary = Boundary.objects.create(**kwargs)

        state = TembaBoundary.create(boundary='R23456', name='Lagos', parent="R12345", level=1, geometry=geometry)
        kwargs = self.syncer.local_kwargs(self.nigeria, state)
        self.assertEqual(kwargs, {'org': self.nigeria, 'osm_id': "R23456", 'name': "Lagos", 'level': 1,
                                  'parent': country_boundary,
                                  'geometry':json.dumps(dict(type='MultiPolygon', coordinates=['COORDINATES']))})

    def test_update_required(self):
        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=[[1, 2]])

        local = Boundary.objects.create(org=self.nigeria, osm_id='OLD123', name='OLD', parent=None, level=0,
                                                   geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        self.assertFalse(self.syncer.update_required(local, TembaBoundary.create(boundary='OLD123', name='OLD',
                                                                                 parent=None, level=0,
                                                                                 geometry=geometry)))

        self.assertTrue(self.syncer.update_required(local, TembaBoundary.create(boundary='OLD123', name='NEW',
                                                                                parent=None, level=0,
                                                                                geometry=geometry)))

        self.assertTrue(self.syncer.update_required(local, TembaBoundary.create(boundary='OLD123', name='NEW',
                                                                                parent=None, level=1,
                                                                                geometry=geometry)))

        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=[[1, 3]])

        self.assertTrue(self.syncer.update_required(local, TembaBoundary.create(boundary='OLD123', name='OLD',
                                                                                 parent=None, level=0,
                                                                                 geometry=geometry)))

    def test_delete_local(self):

        local = Boundary.objects.create(org=self.nigeria, osm_id='OLD123', name='OLD', parent=None, level=0,
                                                   geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        self.syncer.delete_locale(local)
        self.assertFalse(Boundary.objects.filter(pk=local.pk))


class ContactSyncerTest(DashTest):
    def setUp(self):
        super(ContactSyncerTest, self).setUp()
        self.nigeria = self.create_org('nigeria', self.admin)
        self.syncer = ContactSyncer()
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

    def test_local_kwargs(self):

        temba_contact = TembaContact.create(uuid='C-006', name="Jan", urns=['tel:123'],
                                            groups=[ObjectRef.create(uuid='G-001', name='Musicians'),
                                                    ObjectRef.create(uuid='G-007', name='Actors')],
                                            fields={'registration_date': None, 'state': None,
                                                    'lga': None, 'occupation': None, 'born': None,
                                                    'gender': None},
                                            language='eng')

        self.assertIsNone(self.syncer.local_kwargs(self.nigeria, temba_contact))

        temba_contact = TembaContact.create(uuid='C-006', name="Jan", urns=['tel:123'],
                                            groups=[ObjectRef.create(uuid='G-001', name='ureporters'),
                                                    ObjectRef.create(uuid='G-007', name='Actors')],
                                            fields={'registration_date': None, 'state': None,
                                                    'lga': None, 'occupation': None, 'born': None,
                                                    'gender': None},
                                            language='eng')

        self.assertEqual(self.syncer.local_kwargs(self.nigeria, temba_contact),
                         {'org': self.nigeria,
                          'uuid': 'C-006',
                          'gender': '',
                          'born': 0,
                          'occupation': '',
                          'registered_on': None,
                          'state': '',
                          'district': ''})

        temba_contact = TembaContact.create(uuid='C-007', name="Jan", urns=['tel:123'],
                                            groups=[ObjectRef.create(uuid='G-001', name='ureporters'),
                                                    ObjectRef.create(uuid='G-007', name='Actors')],
                                            fields={'registration_date': '2014-01-02T03:04:05.000000Z',
                                                    'state': 'Kigali', 'lga': 'Oyo', 'occupation': 'Student',
                                                    'born': '1990', 'gender': 'Male'},
                                            language='eng')

        self.assertEqual(self.syncer.local_kwargs(self.nigeria, temba_contact),
                         {'org': self.nigeria,
                          'uuid': 'C-007',
                          'gender': 'M',
                          'born': 1990,
                          'occupation': 'Student',
                          'registered_on': json_date_to_datetime('2014-01-02T03:04:05.000'),
                          'state': '',
                          'district': ''})

        temba_contact = TembaContact.create(uuid='C-008', name="Jan", urns=['tel:123'],
                                            groups=[ObjectRef.create(uuid='G-001', name='ureporters'),
                                                    ObjectRef.create(uuid='G-007', name='Actors')],
                                            fields={'registration_date': '2014-01-02T03:04:05.000000Z', 'state':'Lagos',
                                                    'lga': 'Oyo', 'occupation': 'Student', 'born': '1990',
                                                    'gender': 'Male'},
                                            language='eng')

        self.assertEqual(self.syncer.local_kwargs(self.nigeria, temba_contact),
                         {'org': self.nigeria,
                          'uuid': 'C-008',
                          'gender': 'M',
                          'born': 1990,
                          'occupation': 'Student',
                          'registered_on': json_date_to_datetime('2014-01-02T03:04:05.000'),
                          'state': 'R-LAGOS',
                          'district': 'R-OYO'})



