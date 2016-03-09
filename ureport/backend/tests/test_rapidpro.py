# coding=utf-8
from __future__ import unicode_literals

import json

from django.test import override_settings
from mock import patch

from temba_client.v1.types import Boundary as TembaBoundary, Geometry as TembaGeometry
from temba_client.v2.types import Field as TembaField, ObjectRef, Contact as TembaContact

from dash.test import MockClientQuery
from ureport.backend.rapidpro import FieldSyncer, BoundarySyncer, ContactSyncer, RapidProBackend
from ureport.contacts.models import ContactField, Contact
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

        remote = TembaBoundary.create(boundary='OLD123', name='OLD', parent=None, level=0, geometry=geometry)

        self.assertFalse(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        remote = TembaBoundary.create(boundary='OLD123', name='NEW', parent=None, level=0, geometry=geometry)

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        remote = TembaBoundary.create(boundary='OLD123', name='NEW',parent=None, level=1, geometry=geometry)

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=[[1, 3]])
        remote = TembaBoundary.create(boundary='OLD123', name='OLD', parent=None, level=0, geometry=geometry)

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

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


@override_settings(CACHES={'default': {'BACKEND': 'redis_cache.cache.RedisCache', 'LOCATION': '127.0.0.1:6379:1',
                                       'OPTIONS': {'CLIENT_CLASS': 'redis_cache.client.DefaultClient', }}})
class RapidProBackendTest(DashTest):
    def setUp(self):
        super(RapidProBackendTest, self).setUp()
        self.backend = RapidProBackend()
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

        with self.assertNumQueries(8):
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

        with self.assertNumQueries(9):
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

        with self.assertNumQueries(10):
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

        with self.assertNumQueries(8):
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
        remote = TembaBoundary.create(boundary='OLD123', name='OLD', parent=None, level=0, geometry=geometry)

        mock_get_boundaries.return_value = [remote]

        with self.assertNumQueries(4):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (1, 0, 0, 0))

        Boundary.objects.all().delete()
        mock_get_boundaries.return_value = [
            TembaBoundary.create(boundary='OLD123', name='OLD', parent=None, level=0, geometry=geometry),
            TembaBoundary.create(boundary='NEW123', name='NEW', parent=None, level=0, geometry=geometry)
        ]

        with self.assertNumQueries(7):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (2, 0, 0, 0))

        mock_get_boundaries.return_value = [
            TembaBoundary.create(boundary='OLD123', name='CHANGED', parent=None, level=0, geometry=geometry),
            TembaBoundary.create(boundary='NEW123', name='NEW', parent=None, level=0, geometry=geometry)
        ]

        with self.assertNumQueries(6):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (0, 1, 0, 1))

        mock_get_boundaries.return_value = [
            TembaBoundary.create(boundary='OLD123', name='CHANGED2', parent=None, level=0, geometry=geometry),
            TembaBoundary.create(boundary='NEW123', name='NEW_CHANGE', parent=None, level=0, geometry=geometry)
        ]

        with self.assertNumQueries(7):
            num_created, num_updated, num_deleted, num_ignored = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual((num_created, num_updated, num_deleted, num_ignored), (0, 2, 0, 0))