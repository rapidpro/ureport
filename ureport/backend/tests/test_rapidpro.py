# coding=utf-8
from __future__ import unicode_literals

import json

import time

from datetime import timedelta
from django.db import connection, reset_queries
from django.test import override_settings
from django.utils import timezone
from mock import patch

from temba_client.v1.types import Boundary as TembaBoundary, Geometry as TembaGeometry
from temba_client.v2.types import Field as TembaField, ObjectRef, Contact as TembaContact, Step as TembaStep
from temba_client.v2.types import Run as TembaRun

from dash.test import MockClientQuery

from dash.categories.models import Category
from ureport.backend.rapidpro import FieldSyncer, BoundarySyncer, ContactSyncer, RapidProBackend
from ureport.contacts.models import ContactField, Contact
from ureport.locations.models import Boundary
from ureport.polls.models import PollResult, Poll
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

        remote = TembaField.create(key='foo', label='Bar', value_type='text')
        self.assertFalse(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        remote = TembaField.create(key='foo', label='Baz', value_type='text')

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        remote = TembaField.create(key='foo', label='Bar', value_type='numeric')
        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        remote = TembaField.create(key='foo', label='Baz', value_type='numeric')

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))
        

class BoundarySyncerTest(DashTest):

    def setUp(self):
        super(BoundarySyncerTest, self).setUp()
        self.nigeria = self.create_org('nigeria', self.admin)
        self.syncer = BoundarySyncer()

    def test_local_kwargs(self):
        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=['COORDINATES'])
        country = TembaBoundary.create(boundary='R12345', name='Nigeria', parent=None, level=Boundary.COUNTRY_LEVEL,
                                       geometry=geometry)

        kwargs = self.syncer.local_kwargs(self.nigeria, country)
        self.assertEqual(kwargs, {'org': self.nigeria,
                                  'geometry': json.dumps(dict(type=geometry.type, coordinates=geometry.coordinates)),
                                  'parent': None, 'level': 0,
                                  'name': 'Nigeria', 'osm_id': 'R12345'})

        # try creating an object from the kwargs
        country_boundary = Boundary.objects.create(**kwargs)

        state = TembaBoundary.create(boundary='R23456', name='Lagos', parent="R12345", level=Boundary.STATE_LEVEL,
                                     geometry=geometry)
        kwargs = self.syncer.local_kwargs(self.nigeria, state)
        self.assertEqual(kwargs, {'org': self.nigeria, 'osm_id': "R23456", 'name': "Lagos",
                                  'level': Boundary.STATE_LEVEL, 'parent': country_boundary,
                                  'geometry':json.dumps(dict(type='MultiPolygon', coordinates=['COORDINATES']))})

    def test_update_required(self):
        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=[[1, 2]])

        local = Boundary.objects.create(org=self.nigeria, osm_id='OLD123', name='OLD', parent=None,
                                        level=Boundary.COUNTRY_LEVEL,
                                        geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        remote = TembaBoundary.create(boundary='OLD123', name='OLD', parent=None, level=Boundary.COUNTRY_LEVEL,
                                      geometry=geometry)

        self.assertFalse(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        remote = TembaBoundary.create(boundary='OLD123', name='NEW', parent=None, level=Boundary.COUNTRY_LEVEL,
                                      geometry=geometry)

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        remote = TembaBoundary.create(boundary='OLD123', name='NEW',parent=None, level=Boundary.STATE_LEVEL,
                                      geometry=geometry)

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=[[1, 3]])
        remote = TembaBoundary.create(boundary='OLD123', name='OLD', parent=None, level=Boundary.COUNTRY_LEVEL,
                                      geometry=geometry)

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

    def test_delete_local(self):

        local = Boundary.objects.create(org=self.nigeria, osm_id='OLD123', name='OLD', parent=None,
                                        level=Boundary.COUNTRY_LEVEL,
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
        self.nigeria.set_config('ward_label', "Ward")
        self.nigeria.set_config('occupation_label', "Activité")
        self.nigeria.set_config('born_label', "Born")
        self.nigeria.set_config('gender_label', 'Gender')
        self.nigeria.set_config('female_label', "Female")
        self.nigeria.set_config('male_label', 'Male')

        # boundaries fetched
        self.country = Boundary.objects.create(org=self.nigeria, osm_id="R-NIGERIA", name="Nigeria",
                                               level=Boundary.COUNTRY_LEVEL, parent=None,
                                               geometry='{"foo":"bar-country"}')
        self.state = Boundary.objects.create(org=self.nigeria, osm_id="R-LAGOS", name="Lagos",
                                             level=Boundary.STATE_LEVEL,
                                             parent=self.country, geometry='{"foo":"bar-state"}')
        self.district = Boundary.objects.create(org=self.nigeria, osm_id="R-OYO", name="Oyo",
                                                level=Boundary.DISTRICT_LEVEL,
                                                parent=self.state, geometry='{"foo":"bar-state"}')
        self.ward = Boundary.objects.create(org=self.nigeria, osm_id="R-IKEJA", name="Ikeja", level=Boundary.WARD_LEVEL,
                                            parent=self.district, geometry='{"foo":"bar-ward"}')

        self.registration_date = ContactField.objects.create(org=self.nigeria, key='registration_date',
                                                             label='Registration Date', value_type='T')

        self.state_field = ContactField.objects.create(org=self.nigeria, key='state', label='State', value_type='S')
        self.district_field = ContactField.objects.create(org=self.nigeria, key='lga', label='LGA', value_type='D')
        self.ward_field = ContactField.objects.create(org=self.nigeria, key='ward', label='Ward', value_type='T')
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
                          'district': '',
                          'ward': ''})

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
                          'district': '',
                          'ward': ''})

        temba_contact = TembaContact.create(uuid='C-008', name="Jan", urns=['tel:123'],
                                            groups=[ObjectRef.create(uuid='G-001', name='ureporters'),
                                                    ObjectRef.create(uuid='G-007', name='Actors')],
                                            fields={'registration_date': '2014-01-02T03:04:05.000000Z', 'state':'Lagos',
                                                    'lga': 'Oyo', 'ward': 'Ikeja', 'occupation': 'Student', 'born': '1990',
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
                          'district': 'R-OYO',
                          'ward': 'R-IKEJA'})

        temba_contact = TembaContact.create(uuid='C-008', name="Jan", urns=['tel:123'],
                                            groups=[ObjectRef.create(uuid='G-001', name='ureporters'),
                                                    ObjectRef.create(uuid='G-007', name='Actors')],
                                            fields={'registration_date': '2014-01-02T03:04:05.000000Z', 'state':'Lagos',
                                                    'lga': 'Oyo', 'occupation': 'Student', 'born': '-1',
                                                    'gender': 'Male'},
                                            language='eng')

        self.assertEqual(self.syncer.local_kwargs(self.nigeria, temba_contact),
                         {'org': self.nigeria,
                          'uuid': 'C-008',
                          'gender': 'M',
                          'born': 0,
                          'occupation': 'Student',
                          'registered_on': json_date_to_datetime('2014-01-02T03:04:05.000'),
                          'state': 'R-LAGOS',
                          'district': 'R-OYO',
                          'ward': ''})

        temba_contact = TembaContact.create(uuid='C-008', name="Jan", urns=['tel:123'],
                                            groups=[ObjectRef.create(uuid='G-001', name='ureporters'),
                                                    ObjectRef.create(uuid='G-007', name='Actors')],
                                            fields={'registration_date': '2014-01-02T03:04:05.000000Z', 'state':'Lagos',
                                                    'lga': 'Oyo', 'occupation': 'Student', 'born': '2147483648',
                                                    'gender': 'Male'},
                                            language='eng')

        self.assertEqual(self.syncer.local_kwargs(self.nigeria, temba_contact),
                         {'org': self.nigeria,
                          'uuid': 'C-008',
                          'gender': 'M',
                          'born': 0,
                          'occupation': 'Student',
                          'registered_on': json_date_to_datetime('2014-01-02T03:04:05.000'),
                          'state': 'R-LAGOS',
                          'district': 'R-OYO',
                          'ward': ''})


@override_settings(CACHES={'default': {'BACKEND': 'redis_cache.cache.RedisCache', 'LOCATION': '127.0.0.1:6379:1',
                                       'OPTIONS': {'CLIENT_CLASS': 'redis_cache.client.DefaultClient', }}})
class RapidProBackendTest(DashTest):
    def setUp(self):
        super(RapidProBackendTest, self).setUp()
        self.backend = RapidProBackend()
        self.nigeria = self.create_org('nigeria', self.admin)
        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

        self.nigeria.set_config('reporter_group', "Ureporters")
        self.nigeria.set_config('registration_label', "Registration Date")
        self.nigeria.set_config('state_label', "State")
        self.nigeria.set_config('district_label', "LGA")
        self.nigeria.set_config('ward_label', "Ward")
        self.nigeria.set_config('occupation_label', "Activité")
        self.nigeria.set_config('born_label', "Born")
        self.nigeria.set_config('gender_label', 'Gender')
        self.nigeria.set_config('female_label', "Female")
        self.nigeria.set_config('male_label', 'Male')

        # boundaries fetched
        self.country = Boundary.objects.create(org=self.nigeria, osm_id="R-NIGERIA", name="Nigeria",
                                               level=Boundary.COUNTRY_LEVEL, parent=None,
                                               geometry='{"foo":"bar-country"}')
        self.state = Boundary.objects.create(org=self.nigeria, osm_id="R-LAGOS", name="Lagos",
                                             level=Boundary.STATE_LEVEL,
                                             parent=self.country, geometry='{"foo":"bar-state"}')
        self.district = Boundary.objects.create(org=self.nigeria, osm_id="R-OYO", name="Oyo",
                                                level=Boundary.DISTRICT_LEVEL,
                                                parent=self.state, geometry='{"foo":"bar-state"}')
        self.ward = Boundary.objects.create(org=self.nigeria, osm_id="R-IKEJA", name="Ikeja",
                                            level=Boundary.WARD_LEVEL,
                                            parent=self.district, geometry='{"foo":"bar-state"}')

        self.registration_date = ContactField.objects.create(org=self.nigeria, key='registration_date',
                                                             label='Registration Date', value_type='T')

        self.state_field = ContactField.objects.create(org=self.nigeria, key='state', label='State', value_type='S')
        self.district_field = ContactField.objects.create(org=self.nigeria, key='lga', label='LGA', value_type='D')
        self.ward_field = ContactField.objects.create(org=self.nigeria, key='ward', label='Ward', value_type='W')
        self.occupation_field = ContactField.objects.create(org=self.nigeria, key='occupation', label='Activité',
                                                            value_type='T')

        self.born_field = ContactField.objects.create(org=self.nigeria, key='born', label='Born', value_type='T')
        self.gender_field = ContactField.objects.create(org=self.nigeria, key='gender', label='Gender', value_type='T')

    @patch('dash.orgs.models.TembaClient2.get_contacts')
    def test_pull_contacts(self, mock_get_contacts):

        Contact.objects.all().delete()

        # empty fetches
        mock_get_contacts.side_effect = [
            # first call to get active contacts
            MockClientQuery([]),

            # second call to get deleted contacts
            MockClientQuery([])
        ]

        with self.assertNumQueries(0):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (0, 0, 0, 0))

        # fecthed contact not in configured group get ignored
        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001", name="Bob McFlow", language="eng", urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="Customers")],
                        fields={'age': "34"}, failed=False, blocked=False
                    ),
                    TembaContact.create(
                        uuid="C-002", name="Jim McMsg", language="fre", urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-002", name="Spammers")],
                        fields={'age': "67"}, failed=False, blocked=False
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003", name="Ann McPoll", language="eng", urns=["tel:+250783835664"],
                        groups=[],
                        fields={'age': "35"}, failed=True, blocked=False
                    ),
                ]
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004", name=None, language=None, urns=[], groups=[],
                        fields=None, failed=True, blocked=False
                    ),
                ]
            )
        ]

        with self.assertNumQueries(4):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (0, 0, 0, 3))

        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001", name="Bob McFlow", language="eng", urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={'age': "34"}, failed=False, blocked=False
                    ),
                    TembaContact.create(
                        uuid="C-002", name="Jim McMsg", language="fre", urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-002", name="Spammers")],
                        fields={'age': "67"}, failed=False, blocked=False
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003", name="Ann McPoll", language="eng", urns=["tel:+250783835664"],
                        groups=[],
                        fields={'age': "35"}, failed=True, blocked=False
                    ),
                ]
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004", name=None, language=None, urns=[], groups=[],
                        fields=None, failed=True, blocked=False
                    ),
                ]
            )
        ]

        with self.assertNumQueries(9):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (1, 0, 0, 2))

        Contact.objects.all().delete()

        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001", name="Bob McFlow", language="eng", urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={'age': "34"}, failed=False, blocked=False
                    ),
                    TembaContact.create(
                        uuid="C-002", name="Jim McMsg", language="fre", urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={'age': "67"}, failed=False, blocked=False
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003", name="Ann McPoll", language="eng", urns=["tel:+250783835664"],
                        groups=[],
                        fields={'age': "35"}, failed=True, blocked=False
                    ),
                ]
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004", name=None, language=None, urns=[], groups=[],
                        fields=None, failed=True, blocked=False
                    ),
                ]
            )
        ]

        with self.assertNumQueries(10):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (2, 0, 0, 1))

        Contact.objects.all().delete()

        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            # all included in the reporters
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001", name="Bob McFlow", language="eng", urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={'age': "34"}, failed=False, blocked=False
                    ),
                    TembaContact.create(
                        uuid="C-002", name="Jim McMsg", language="fre", urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={'age': "67"}, failed=False, blocked=False
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003", name="Ann McPoll", language="eng", urns=["tel:+250783835664"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={'age': "35"}, failed=True, blocked=False
                    ),
                ]
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004", name=None, language=None, urns=[], groups=[],
                        fields=None, failed=True, blocked=False
                    ),
                ]
            )
        ]

        with self.assertNumQueries(11):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (3, 0, 0, 0))

        contact_jan = Contact.objects.filter(uuid='C-001').first()
        self.assertFalse(contact_jan.born)
        self.assertFalse(contact_jan.state)

        mock_get_contacts.side_effect = [
            # first call to get active contacts
            MockClientQuery(
                [
                    TembaContact.create(uuid='C-001', name="Jan", urns=['tel:123'],
                                        groups=[ObjectRef.create(uuid='G-001', name='ureporters'),
                                                ObjectRef.create(uuid='G-007', name='Actors')],
                                        fields={'registration_date': '2014-01-02T03:04:05.000000Z', 'state':'Lagos',
                                                'lga': 'Oyo', 'occupation': 'Student', 'born': '1990',
                                                'gender': 'Male'},
                                        language='eng'),
                    TembaContact.create(
                        uuid="C-002", name="Jim McMsg", language="fre", urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={'age': "67", "born": "1992"}, failed=False, blocked=False
                    ),
                ]
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004", name=None, language=None, urns=[], groups=[],
                        fields=None, failed=True, blocked=False
                    ),
                ]
            )
        ]

        with self.assertNumQueries(9):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (0, 2, 0, 0))

        contact_jan = Contact.objects.filter(uuid='C-001').first()

        self.assertTrue(contact_jan.born)
        self.assertEqual(contact_jan.born, 1990)
        self.assertTrue(contact_jan.state)
        self.assertEqual(contact_jan.state, 'R-LAGOS')

        self.assertTrue(Contact.objects.filter(uuid='C-002', is_active=True))

        mock_get_contacts.side_effect = [
            # first call to get active contacts
            MockClientQuery([]
            ),
            # second call to get deleted contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-002", name=None, language=None, urns=[], groups=[],
                        fields=None, failed=True, blocked=False
                    ),
                ]
            )
        ]

        with self.assertNumQueries(2):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (0, 0, 1, 0))

        self.assertFalse(Contact.objects.filter(uuid='C-002', is_active=True))

    @patch('dash.orgs.models.TembaClient2.get_fields')
    def test_pull_fields(self, mock_get_fields):

        ContactField.objects.all().delete()

        mock_get_fields.return_value = MockClientQuery([
            TembaField.create(key="nick_name", label="Nickname", value_type="text"),
            TembaField.create(key="age", label="Age", value_type="numeric"),
        ])

        with self.assertNumQueries(5):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_fields(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (2, 0, 0, 0))

        ContactField.objects.get(key="nick_name", label="Nickname", value_type="T", is_active=True)
        ContactField.objects.get(key="age", label="Age", value_type="N", is_active=True)

        mock_get_fields.return_value = MockClientQuery([
            TembaField.create(key="age", label="Age (Years)", value_type="numeric"),
            TembaField.create(key="homestate", label="Homestate", value_type="state"),
        ])

        with self.assertNumQueries(6):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_fields(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (1, 1, 1, 0))

        ContactField.objects.get(key="nick_name", label="Nickname", value_type="T", is_active=False)
        ContactField.objects.get(key="age", label="Age (Years)", value_type="N", is_active=True)
        ContactField.objects.get(key="homestate", label="Homestate", value_type="S", is_active=True)

        # check that no changes means no updates
        with self.assertNumQueries(3):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_fields(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (0, 0, 0, 2))

    @patch('dash.orgs.models.TembaClient1.get_boundaries')
    def test_pull_boundaries(self, mock_get_boundaries):

        Boundary.objects.all().delete()
        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=[[1, 2]])
        remote = TembaBoundary.create(boundary='OLD123', name='OLD', parent=None,
                                      level=Boundary.COUNTRY_LEVEL, geometry=geometry)

        mock_get_boundaries.return_value = [remote]

        with self.assertNumQueries(4):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (1, 0, 0, 0))

        Boundary.objects.all().delete()
        mock_get_boundaries.return_value = [
            TembaBoundary.create(boundary='OLD123', name='OLD', parent=None, level=Boundary.COUNTRY_LEVEL,
                                 geometry=geometry),
            TembaBoundary.create(boundary='NEW123', name='NEW', parent=None, level=Boundary.COUNTRY_LEVEL,
                                 geometry=geometry)
        ]

        with self.assertNumQueries(7):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (2, 0, 0, 0))

        mock_get_boundaries.return_value = [
            TembaBoundary.create(boundary='OLD123', name='CHANGED', parent=None, level=Boundary.COUNTRY_LEVEL,
                                 geometry=geometry),
            TembaBoundary.create(boundary='NEW123', name='NEW', parent=None, level=Boundary.COUNTRY_LEVEL,
                                 geometry=geometry)
        ]

        with self.assertNumQueries(6):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (0, 1, 0, 1))

        mock_get_boundaries.return_value = [
            TembaBoundary.create(boundary='OLD123', name='CHANGED2', parent=None, level=Boundary.COUNTRY_LEVEL,
                                 geometry=geometry),
            TembaBoundary.create(boundary='NEW123', name='NEW_CHANGE', parent=None, level=Boundary.COUNTRY_LEVEL,
                                 geometry=geometry)
        ]

        with self.assertNumQueries(7):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (0, 2, 0, 0))

    @patch('dash.orgs.models.TembaClient2.get_runs')
    @patch('django.utils.timezone.now')
    @patch('django.core.cache.cache.get')
    def test_pull_results(self, mock_cache_get, mock_timezone_now, mock_get_runs):
        mock_cache_get.return_value = None

        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date


        PollResult.objects.all().delete()
        contact = Contact.objects.create(org=self.nigeria, uuid='C-001', gender='M', born=1990, state='R-LAGOS',
                                         district='R-OYO')
        poll = self.create_poll(self.nigeria, "Flow 1", 'flow-uuid', self.education_nigeria, self.admin)

        now = timezone.now()
        temba_run = TembaRun.create(id=1234, flow=ObjectRef.create(uuid='flow-uuid', name="Flow 1"),
                                    contact=ObjectRef.create(uuid='C-001', name='Wiz Kid'), responded=True,
                                    steps=[TembaStep.create(node='ruleset-uuid', text="We'll win today", value="win",
                                                            category='Win', type='ruleset',
                                                            arrived_on=now, left_on=now)],
                                    created_on=now, modified_on=now, exited_on=now,
                                    exit_type='completed')

        mock_get_runs.side_effect = [MockClientQuery([temba_run])]

        with self.assertNumQueries(3):
            num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (1, 0, 0))
        mock_get_runs.assert_called_with(flow='flow-uuid', after=None, before=now)

        poll_result = PollResult.objects.filter(flow='flow-uuid', ruleset='ruleset-uuid', contact='C-001').first()
        self.assertEqual(poll_result.state, 'R-LAGOS')
        self.assertEqual(poll_result.district, 'R-OYO')
        self.assertEqual(poll_result.contact, 'C-001')
        self.assertEqual(poll_result.ruleset, 'ruleset-uuid')
        self.assertEqual(poll_result.flow, 'flow-uuid')
        self.assertEqual(poll_result.category, 'Win')
        self.assertEqual(poll_result.text, "We'll win today")

        temba_run_1 = TembaRun.create(id=1235, flow=ObjectRef.create(uuid='flow-uuid', name="Flow 1"),
                                      contact=ObjectRef.create(uuid='C-002', name='Davido'), responded=True,
                                      steps=[TembaStep.create(node='ruleset-uuid', text="I sing", value="sing",
                                                              category='Sing', type='ruleset',
                                                              arrived_on=now, left_on=now)],
                                      created_on=now, modified_on=now, exited_on=now,
                                      exit_type='completed')

        temba_run_2 = TembaRun.create(id=1236, flow=ObjectRef.create(uuid='flow-uuid', name="Flow 1"),
                                      contact=ObjectRef.create(uuid='C-003', name='Lebron'), responded=True,
                                      steps=[TembaStep.create(node='ruleset-uuid', text="I play basketball",
                                                              value="play", category='Play', type='ruleset',
                                                              arrived_on=now, left_on=now)],
                                      created_on=now, modified_on=now, exited_on=now,
                                      exit_type='completed')

        mock_get_runs.side_effect = [MockClientQuery([temba_run_1, temba_run_2])]

        with self.assertNumQueries(3):
            num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (2, 0, 0))
        self.assertEqual(3, PollResult.objects.all().count())
        self.assertEqual(1, Contact.objects.all().count())

        contact.state = 'R-KIGALI'
        contact.district = 'R-GASABO'
        contact.save()

        temba_run_3 = TembaRun.create(id=1234, flow=ObjectRef.create(uuid='flow-uuid', name="Flow 1"),
                                      contact=ObjectRef.create(uuid='C-001', name='Wiz Kid'), responded=True,
                                      steps=[TembaStep.create(node='ruleset-uuid', text="We'll celebrate today",
                                                              value="celebrate", category='Party', type='ruleset',
                                                              arrived_on=now + timedelta(minutes=1), left_on=now)],
                                      created_on=now, modified_on=now, exited_on=now,
                                      exit_type='completed')

        mock_get_runs.side_effect = [MockClientQuery([temba_run_3])]

        with self.assertNumQueries(3):
            num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (0, 1, 0))

        poll_result = PollResult.objects.filter(flow='flow-uuid', ruleset='ruleset-uuid', contact='C-001').first()
        self.assertEqual(poll_result.state, 'R-KIGALI')
        self.assertEqual(poll_result.district, 'R-GASABO')
        self.assertEqual(poll_result.contact, 'C-001')
        self.assertEqual(poll_result.ruleset, 'ruleset-uuid')
        self.assertEqual(poll_result.flow, 'flow-uuid')
        self.assertEqual(poll_result.category, 'Party')
        self.assertEqual(poll_result.text, "We'll celebrate today")

        mock_get_runs.side_effect = [MockClientQuery([temba_run_3])]
        with self.assertNumQueries(2):
            num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (0, 0, 1))

        mock_get_runs.side_effect = [MockClientQuery([temba_run_1, temba_run_2])]

        with self.assertNumQueries(2):
            num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (0, 0, 2))

    @patch('dash.orgs.models.TembaClient2.get_runs')
    @patch('django.utils.timezone.now')
    @patch('django.core.cache.cache.get')
    def test_poll_ward_field(self, mock_cache_get, mock_timezone_now, mock_get_runs):
        mock_cache_get.return_value = None

        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date


        PollResult.objects.all().delete()
        contact = Contact.objects.create(org=self.nigeria, uuid='C-021', gender='M', born=1971, state='R-LAGOS',
                                         district='R-OYO', ward='R-IKEJA')

        poll = self.create_poll(self.nigeria, "Flow 1", 'flow-uuid-3', self.education_nigeria, self.admin)

        now = timezone.now()
        temba_run = TembaRun.create(id=4321, flow=ObjectRef.create(uuid='flow-uuid-3', name="Flow 2"),
                                    contact=ObjectRef.create(uuid='C-021', name='Hyped'), responded=True,
                                    steps=[TembaStep.create(node='ruleset-uuid', text="Doing it now", value="win",
                                                            category='Win', type='ruleset',
                                                            arrived_on=now, left_on=now)],
                                    created_on=now, modified_on=now, exited_on=now,
                                    exit_type='completed')

        mock_get_runs.side_effect = [MockClientQuery([temba_run])]

        with self.assertNumQueries(3):
            num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (1, 0, 0))
        mock_get_runs.assert_called_with(flow='flow-uuid-3', after=None, before=now)

        poll_result = PollResult.objects.filter(flow='flow-uuid-3', ruleset='ruleset-uuid', contact='C-021').first()
        self.assertEqual(poll_result.ward, 'R-IKEJA')


@override_settings(CACHES={'default': {'BACKEND': 'redis_cache.cache.RedisCache', 'LOCATION': '127.0.0.1:6379:1',
                                       'OPTIONS': {'CLIENT_CLASS': 'redis_cache.client.DefaultClient', }}})
class PerfTest(DashTest):

    def setUp(self):
        super(PerfTest, self).setUp()

        self.backend = RapidProBackend()

        self.nigeria = self.create_org('nigeria', self.admin)
        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

        self.nigeria.set_config('reporter_group', "Ureporters")
        self.nigeria.set_config('registration_label', "Registration Date")
        self.nigeria.set_config('state_label', "State")
        self.nigeria.set_config('district_label', "LGA")
        self.nigeria.set_config('ward_label', "Ward")
        self.nigeria.set_config('occupation_label', "Activité")
        self.nigeria.set_config('born_label', "Born")
        self.nigeria.set_config('gender_label', 'Gender')
        self.nigeria.set_config('female_label', "Female")
        self.nigeria.set_config('male_label', 'Male')

        # boundaries fetched
        self.country = Boundary.objects.create(org=self.nigeria, osm_id="R-NIGERIA", name="Nigeria",
                                               level=Boundary.COUNTRY_LEVEL, parent=None,
                                               geometry='{"foo":"bar-country"}')
        self.state = Boundary.objects.create(org=self.nigeria, osm_id="R-LAGOS", name="Lagos",
                                             level=Boundary.STATE_LEVEL,
                                             parent=self.country, geometry='{"foo":"bar-state"}')
        self.district = Boundary.objects.create(org=self.nigeria, osm_id="R-OYO", name="Oyo",
                                                level=Boundary.DISTRICT_LEVEL,
                                                parent=self.state, geometry='{"foo":"bar-state"}')
        self.ward = Boundary.objects.create(org=self.nigeria, osm_id="R-IKEJA", name="Ikeja",
                                            level=Boundary.WARD_LEVEL,
                                            parent=self.district, geometry='{"foo":"bar-ward"}')

        self.registration_date = ContactField.objects.create(org=self.nigeria, key='registration_date',
                                                             label='Registration Date', value_type='T')

        self.state_field = ContactField.objects.create(org=self.nigeria, key='state', label='State', value_type='S')
        self.district_field = ContactField.objects.create(org=self.nigeria, key='lga', label='LGA', value_type='D')
        self.occupation_field = ContactField.objects.create(org=self.nigeria, key='occupation', label='Activité',
                                                            value_type='T')

        self.born_field = ContactField.objects.create(org=self.nigeria, key='born', label='Born', value_type='T')
        self.gender_field = ContactField.objects.create(org=self.nigeria, key='gender', label='Gender', value_type='T')

    @override_settings(DEBUG=True)
    @patch('dash.orgs.models.TembaClient2.get_runs')
    @patch('django.utils.timezone.now')
    @patch('django.core.cache.cache.get')
    def test_pull_results(self, mock_cache_get, mock_timezone_now, mock_get_runs):
        mock_cache_get.return_value = None

        from django_redis import get_redis_connection
        redis_client = get_redis_connection()

        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date

        PollResult.objects.all().delete()

        poll = self.create_poll(self.nigeria, "Flow 1", 'flow-uuid', self.education_nigeria, self.admin)

        key = Poll.POLL_PULL_RESULTS_TASK_LOCK % (poll.org.pk, poll.flow_uuid)
        redis_client.delete(key)

        now = timezone.now()

        fetch_size = 250
        num_fetches = 4
        num_steps = 5
        names = ["Ann", "Bob", "Cat"]

        active_fetches = []
        for b in range(0, num_fetches):
            batch = []
            for r in range(0, fetch_size):
                num = b * fetch_size + r
                batch.append(TembaRun.create(
                    id=num,
                    flow=ObjectRef.create(uuid='flow-uuid', name="Flow 1"),
                    contact=ObjectRef.create(uuid='C-00%d' % num, name=names[num % len(names)]),
                    responded=True,
                    steps=[TembaStep.create(node='ruleset-uuid-%d' % s,
                                            text="Text %s" % s,
                                            value="Value %s" % s,
                                            category='Category %s' % s,
                                            type='ruleset',
                                            arrived_on=now, left_on=now)
                           for s in range(0, num_steps)],
                    created_on=now,
                    modified_on=now,
                    exited_on=now,
                    exit_type=''))

            active_fetches.append(batch)

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        start = time.time()

        num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        mock_get_runs.assert_called_once_with(flow=poll.flow_uuid, after=None, before=now)

        self.assertEqual((num_created, num_updated, num_ignored), (num_fetches * fetch_size * num_steps, 0, 0))

        slowest_queries = sorted(connection.queries, key=lambda q: q['time'], reverse=True)[:10]
        for q in slowest_queries:
            print "=" * 60
            print "\n\n\n"
            print "%s -- %s" % (q['time'], q['sql'])

        reset_queries()

        # simulate a subsequent sync with no changes
        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]
        start = time.time()

        redis_client.delete(key)
        num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (0, 0, num_fetches * fetch_size * num_steps))

        slowest_queries = sorted(connection.queries, key=lambda q: q['time'], reverse=True)[:10]
        for q in slowest_queries:
            print "%s -- %s" % (q['time'], q['sql'])

        reset_queries()

        # simulate ignore of 1 value change from older runs
        for batch in active_fetches:
            for r in batch:
                r.steps[0] = TembaStep.create(node='ruleset-uuid-0',
                                              text="Txt 0",
                                              value="Val 0",
                                              category='CAT 0',
                                              type='ruleset',
                                              arrived_on=now - timedelta(minutes=1), left_on=now)

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        start = time.time()

        redis_client.delete(key)
        num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (0, 0, num_fetches * fetch_size * num_steps))

        slowest_queries = sorted(connection.queries, key=lambda q: q['time'], reverse=True)[:10]
        for q in slowest_queries:
            print "=" * 60
            print "\n\n\n"
            print "%s -- %s" % (q['time'], q['sql'])

        reset_queries()

        # simulate an update of 1 value
        for batch in active_fetches:
            for r in batch:
                r.steps[0] = TembaStep.create(node='ruleset-uuid-0',
                                              text="Txt 0",
                                              value="Val 0",
                                              category='CAT 0',
                                              type='ruleset',
                                              arrived_on=now + timedelta(minutes=1), left_on=now)

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        start = time.time()

        redis_client.delete(key)
        num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (0, num_fetches * fetch_size,
                                                                   num_fetches * fetch_size * (num_steps - 1)))

        slowest_queries = sorted(connection.queries, key=lambda q: q['time'], reverse=True)[:10]
        for q in slowest_queries:
            print "=" * 60
            print "\n\n\n"
            print "%s -- %s" % (q['time'], q['sql'])

        reset_queries()

        # simulate ignoring actionset nodes
        for batch in active_fetches:
            for r in batch:
                r.steps[0] = TembaStep.create(node='actionset-uuid-0',
                                              text="What do you think?",
                                              value="",
                                              category='',
                                              type='actionset',
                                              arrived_on=now + timedelta(minutes=5), left_on=now)

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        start = time.time()

        redis_client.delete(key)
        num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (0, 0, num_fetches * fetch_size * num_steps))

        slowest_queries = sorted(connection.queries, key=lambda q: q['time'], reverse=True)[:10]
        for q in slowest_queries:
            print "=" * 60
            print "\n\n\n"
            print "%s -- %s" % (q['time'], q['sql'])

        reset_queries()

        # simulate an update of 1 value
        for batch in active_fetches:
            for r in batch:
                r.steps = [TembaStep.create(node='ruleset-uuid-0',
                                            text="T %s" % s ,
                                            value="V %s" % s,
                                            category='C %s' % s,
                                            type='ruleset',
                                            arrived_on=now + timedelta(minutes=1), left_on=now)
                           for s in range(0, num_steps)]

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        start = time.time()

        redis_client.delete(key)
        num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (0, num_fetches * fetch_size * num_steps, 0))

        slowest_queries = sorted(connection.queries, key=lambda q: q['time'], reverse=True)[:10]
        for q in slowest_queries:
            print "=" * 60
            print "\n\n\n"
            print "%s -- %s" % (q['time'], q['sql'])

        reset_queries()

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        redis_client.set(key, 'lock-taken')

        num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (0, 0, 0))

        redis_client.delete(key)

        PollResult.objects.all().delete()

        start = time.time()

        # same contact, same ruleset, same or previous time should all be ignored, only insert one, ignore others
        active_fetches = []
        for b in range(0, num_fetches):
            batch = []
            for r in range(0, fetch_size):
                num = b * fetch_size + r
                batch.append(TembaRun.create(
                    id=num,
                    flow=ObjectRef.create(uuid='flow-uuid', name="Flow 1"),
                    contact=ObjectRef.create(uuid='C-001', name='Will'),
                    responded=True,
                    steps=[TembaStep.create(node='ruleset-uuid-0',
                                            text="Text %s" % s,
                                            value="Value %s" % s,
                                            category='Category %s' % s,
                                            type='ruleset',
                                            arrived_on=now, left_on=now)
                           for s in range(0, num_steps)],
                    created_on=now,
                    modified_on=now,
                    exited_on=now,
                    exit_type=''))

            active_fetches.append(batch)

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        num_created, num_updated, num_ignored = self.backend.pull_results(poll, None, None)

        self.assertEqual((num_created, num_updated, num_ignored), (1, 0, num_fetches * fetch_size * num_steps - 1))