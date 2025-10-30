# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import gzip
import io
import json
import logging
from datetime import timedelta

from mock import PropertyMock, patch
from temba_client.exceptions import TembaRateExceededError
from temba_client.v2.types import (
    Archive as TembaArchive,
    Boundary as TembaBoundary,
    Contact as TembaContact,
    Field as TembaField,
    ObjectRef,
    Run as TembaRun,
)

from django.db import connection, reset_queries
from django.test import override_settings
from django.utils import timezone

from dash.categories.models import Category
from dash.test import MockClientQuery
from dash.utils.sync import SyncOutcome
from ureport.backend.rapidpro import BoundarySyncer, ContactSyncer, FieldSyncer, RapidProBackend
from ureport.contacts.models import Contact, ContactField
from ureport.flows.models import FlowResult, FlowResultCategory
from ureport.locations.models import Boundary
from ureport.polls.models import Poll, PollQuestion, PollResponseCategory, PollResult
from ureport.stats.models import ContactActivity
from ureport.tests import MockResponse, UreportTest
from ureport.utils import datetime_to_json_date, json_date_to_datetime

logger = logging.getLogger(__name__)


class FieldSyncerTest(UreportTest):
    def setUp(self):
        super(FieldSyncerTest, self).setUp()
        self.syncer = FieldSyncer(backend=self.rapidpro_backend)
        self.syncer2 = FieldSyncer(backend=self.floip_backend)

    def test_local_kwargs(self):
        kwargs = self.syncer.local_kwargs(self.nigeria, TembaField.create(key="foo", name="Bar", type="text"))

        self.assertEqual(
            kwargs,
            {"backend": self.rapidpro_backend, "org": self.nigeria, "key": "foo", "label": "Bar", "value_type": "T"},
        )

        kwargs = self.syncer2.local_kwargs(self.nigeria, TembaField.create(key="foo", name="Bar", type="text"))

        self.assertEqual(
            kwargs,
            {"backend": self.floip_backend, "org": self.nigeria, "key": "foo", "label": "Bar", "value_type": "T"},
        )

    def test_update_required(self):
        local = ContactField.objects.create(
            org=self.nigeria, key="foo", label="Bar", value_type="T", backend=self.rapidpro_backend
        )

        remote = TembaField.create(key="foo", name="Bar", type="text")
        self.assertFalse(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))
        self.assertFalse(self.syncer.update_required(local, remote, self.syncer2.local_kwargs(self.nigeria, remote)))

        remote = TembaField.create(key="foo", name="Baz", type="text")

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))
        self.assertFalse(self.syncer.update_required(local, remote, self.syncer2.local_kwargs(self.nigeria, remote)))

        remote = TembaField.create(key="foo", name="Bar", type="numeric")
        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))
        self.assertFalse(self.syncer.update_required(local, remote, self.syncer2.local_kwargs(self.nigeria, remote)))

        remote = TembaField.create(key="foo", name="Baz", type="numeric")

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))
        self.assertFalse(self.syncer.update_required(local, remote, self.syncer2.local_kwargs(self.nigeria, remote)))


class BoundarySyncerTest(UreportTest):
    def setUp(self):
        super(BoundarySyncerTest, self).setUp()
        self.syncer = BoundarySyncer(self.rapidpro_backend)
        self.syncer2 = BoundarySyncer(self.floip_backend)

    def test_local_kwargs(self):
        country = TembaBoundary.create(
            osm_id="R12345", name="Nigeria", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=None, aliases=None
        )

        kwargs = self.syncer.local_kwargs(self.nigeria, country)
        self.assertEqual(
            kwargs,
            {
                "backend": self.rapidpro_backend,
                "org": self.nigeria,
                "geometry": json.dumps(dict()),
                "parent": None,
                "level": 0,
                "name": "Nigeria",
                "osm_id": "R12345",
            },
        )

        geometry = TembaBoundary.Geometry.create(type="MultiPolygon", coordinates=["COORDINATES"])
        country = TembaBoundary.create(
            osm_id="R12345", name="Nigeria", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry, aliases=None
        )

        kwargs = self.syncer.local_kwargs(self.nigeria, country)
        self.assertEqual(
            kwargs,
            {
                "backend": self.rapidpro_backend,
                "org": self.nigeria,
                "geometry": json.dumps(dict(type=geometry.type, coordinates=geometry.coordinates)),
                "parent": None,
                "level": 0,
                "name": "Nigeria",
                "osm_id": "R12345",
            },
        )

        # try creating an object from the kwargs
        country_boundary = Boundary.objects.create(**kwargs)
        parent = TembaBoundary.BoundaryRef.create(osm_id=country.osm_id, name=country.name)
        state = TembaBoundary.create(
            osm_id="R23456", name="Lagos", parent=parent, level=Boundary.STATE_LEVEL, geometry=geometry, aliases=None
        )
        kwargs = self.syncer.local_kwargs(self.nigeria, state)
        self.assertEqual(
            kwargs,
            {
                "backend": self.rapidpro_backend,
                "org": self.nigeria,
                "osm_id": "R23456",
                "name": "Lagos",
                "level": Boundary.STATE_LEVEL,
                "parent": country_boundary,
                "geometry": json.dumps(dict(type="MultiPolygon", coordinates=["COORDINATES"])),
            },
        )

        kwargs = self.syncer2.local_kwargs(self.nigeria, state)
        self.assertEqual(
            kwargs,
            {
                "backend": self.floip_backend,
                "org": self.nigeria,
                "osm_id": "R23456",
                "name": "Lagos",
                "level": Boundary.STATE_LEVEL,
                "parent": country_boundary,
                "geometry": json.dumps(dict(type="MultiPolygon", coordinates=["COORDINATES"])),
            },
        )

    def test_update_required(self):
        geometry = TembaBoundary.Geometry.create(type="MultiPolygon", coordinates=[[1, 2]])

        local = Boundary.objects.create(
            org=self.nigeria,
            osm_id="OLD123",
            name="OLD",
            parent=None,
            level=Boundary.COUNTRY_LEVEL,
            backend=self.rapidpro_backend,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        remote = TembaBoundary.create(
            osm_id="OLD123", name="OLD", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
        )

        self.assertFalse(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))
        self.assertFalse(self.syncer.update_required(local, remote, self.syncer2.local_kwargs(self.nigeria, remote)))

        remote = TembaBoundary.create(
            osm_id="OLD123", name="NEW", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
        )

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        remote = TembaBoundary.create(
            osm_id="OLD123", name="NEW", parent=None, level=Boundary.STATE_LEVEL, geometry=geometry
        )

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        geometry = TembaBoundary.Geometry.create(type="MultiPolygon", coordinates=[[1, 3]])
        remote = TembaBoundary.create(
            osm_id="OLD123", name="OLD", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
        )

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        local = Boundary.objects.create(
            org=self.nigeria,
            osm_id="SOME123",
            name="Location",
            parent=None,
            level=Boundary.COUNTRY_LEVEL,
            geometry="{}",
        )

        remote = TembaBoundary.create(
            osm_id="SOME123", name="Location", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=None
        )

        self.assertFalse(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))

        local = Boundary.objects.create(
            org=self.nigeria,
            osm_id="SOME124",
            name="Location",
            parent=None,
            backend=self.rapidpro_backend,
            level=Boundary.STATE_LEVEL,
            geometry="{}",
        )

        remote = TembaBoundary.create(
            osm_id="SOME124", name="Location", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=None
        )

        self.assertTrue(self.syncer.update_required(local, remote, self.syncer.local_kwargs(self.nigeria, remote)))
        self.assertFalse(self.syncer.update_required(local, remote, self.syncer2.local_kwargs(self.nigeria, remote)))

    def test_delete_local(self):
        local = Boundary.objects.create(
            org=self.nigeria,
            osm_id="OLD123",
            name="OLD",
            parent=None,
            level=Boundary.COUNTRY_LEVEL,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        self.syncer.delete_local(local)
        self.assertFalse(Boundary.objects.filter(pk=local.pk))


class ContactSyncerTest(UreportTest):
    def setUp(self):
        super(ContactSyncerTest, self).setUp()
        self.syncer = ContactSyncer(self.rapidpro_backend)
        self.nigeria.set_config("rapidpro.reporter_group", "Ureporters")
        self.nigeria.set_config("rapidpro.registration_label", "Registration Date")
        self.nigeria.set_config("rapidpro.state_label", "State")
        self.nigeria.set_config("rapidpro.district_label", "LGA")
        self.nigeria.set_config("rapidpro.ward_label", "Ward")
        self.nigeria.set_config("rapidpro.occupation_label", "Activité")
        self.nigeria.set_config("rapidpro.born_label", "Born")
        self.nigeria.set_config("rapidpro.gender_label", "Gender")
        self.nigeria.set_config("rapidpro.female_label", "Female")
        self.nigeria.set_config("rapidpro.male_label", "Male")

        # boundaries fetched
        self.country = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-NIGERIA",
            name="Nigeria",
            level=Boundary.COUNTRY_LEVEL,
            parent=None,
            backend=self.rapidpro_backend,
            geometry='{"foo":"bar-country"}',
        )
        self.state = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-LAGOS",
            name="Lagos",
            level=Boundary.STATE_LEVEL,
            backend=self.rapidpro_backend,
            parent=self.country,
            geometry='{"foo":"bar-state"}',
        )
        self.district = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-OYO",
            name="Oyo",
            level=Boundary.DISTRICT_LEVEL,
            backend=self.rapidpro_backend,
            parent=self.state,
            geometry='{"foo":"bar-state"}',
        )
        self.ward = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-IKEJA",
            name="Ikeja",
            level=Boundary.WARD_LEVEL,
            parent=self.district,
            geometry='{"foo":"bar-ward"}',
            backend=self.rapidpro_backend,
        )

        self.registration_date = ContactField.objects.create(
            org=self.nigeria,
            key="registration_date",
            backend=self.rapidpro_backend,
            label="Registration Date",
            value_type="T",
        )

        self.state_field = ContactField.objects.create(
            org=self.nigeria, key="state", label="State", value_type="S", backend=self.rapidpro_backend
        )
        self.district_field = ContactField.objects.create(
            org=self.nigeria, key="lga", label="LGA", value_type="D", backend=self.rapidpro_backend
        )
        self.ward_field = ContactField.objects.create(
            org=self.nigeria, key="ward", label="Ward", value_type="T", backend=self.rapidpro_backend
        )
        self.occupation_field = ContactField.objects.create(
            org=self.nigeria, key="occupation", label="Activité", value_type="T", backend=self.rapidpro_backend
        )

        self.born_field = ContactField.objects.create(
            org=self.nigeria, key="born", label="Born", value_type="T", backend=self.rapidpro_backend
        )
        self.gender_field = ContactField.objects.create(
            org=self.nigeria, key="gender", label="Gender", value_type="T", backend=self.rapidpro_backend
        )

    def test_local_kwargs(self):
        temba_contact = TembaContact.create(
            uuid="C-006",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="Musicians"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": None,
                "state": None,
                "lga": None,
                "occupation": None,
                "born": None,
                "gender": None,
            },
            language="eng",
        )

        self.assertIsNone(self.syncer.local_kwargs(self.nigeria, temba_contact))

        temba_contact = TembaContact.create(
            uuid="C-006",
            name="Jan",
            urns=[],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": None,
                "state": None,
                "lga": None,
                "occupation": None,
                "born": None,
                "gender": None,
            },
            language="eng",
            created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
        )

        self.assertIsNone(self.syncer.local_kwargs(self.nigeria, temba_contact))

        temba_contact = TembaContact.create(
            uuid="C-006",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": None,
                "state": None,
                "lga": None,
                "occupation": None,
                "born": None,
                "gender": None,
            },
            language="eng",
            created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.rapidpro_backend,
                "org": self.nigeria,
                "uuid": "C-006",
                "gender": "",
                "born": 0,
                "occupation": "",
                "registered_on": json_date_to_datetime("2013-01-02T03:04:05.000"),
                "scheme": "tel",
                "state": "",
                "district": "",
                "ward": "",
            },
        )

        temba_contact = TembaContact.create(
            uuid="C-007",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Kigali",
                "lga": "Oyo",
                "occupation": "Student",
                "born": "1990",
                "gender": "Male",
            },
            language="eng",
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.rapidpro_backend,
                "org": self.nigeria,
                "uuid": "C-007",
                "gender": "M",
                "born": 1990,
                "occupation": "Student",
                "registered_on": json_date_to_datetime("2014-01-02T03:04:05.000"),
                "scheme": "tel",
                "state": "",
                "district": "",
                "ward": "",
            },
        )

        temba_contact = TembaContact.create(
            uuid="C-008",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Lagos",
                "lga": "Oyo",
                "ward": "Ikeja",
                "occupation": "Student",
                "born": "1990",
                "gender": "Male",
            },
            language="eng",
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.rapidpro_backend,
                "org": self.nigeria,
                "uuid": "C-008",
                "gender": "M",
                "born": 1990,
                "occupation": "Student",
                "registered_on": json_date_to_datetime("2014-01-02T03:04:05.000"),
                "scheme": "tel",
                "state": "R-LAGOS",
                "district": "R-OYO",
                "ward": "R-IKEJA",
            },
        )

        temba_contact = TembaContact.create(
            uuid="C-008",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Lagos",
                "lga": "Oyo",
                "occupation": "Student",
                "born": "-1",
                "gender": "Male",
            },
            language="eng",
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.rapidpro_backend,
                "org": self.nigeria,
                "uuid": "C-008",
                "gender": "M",
                "born": 0,
                "occupation": "Student",
                "registered_on": json_date_to_datetime("2014-01-02T03:04:05.000"),
                "scheme": "tel",
                "state": "R-LAGOS",
                "district": "R-OYO",
                "ward": "",
            },
        )

        temba_contact = TembaContact.create(
            uuid="C-008",
            name="Jan",
            urns=["tel:*******"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Lagos",
                "lga": "Oyo",
                "occupation": "Student",
                "born": "2147483648",
                "gender": "Male",
            },
            language="eng",
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.rapidpro_backend,
                "org": self.nigeria,
                "uuid": "C-008",
                "gender": "M",
                "born": 0,
                "occupation": "Student",
                "registered_on": json_date_to_datetime("2014-01-02T03:04:05.000"),
                "scheme": "tel",
                "state": "R-LAGOS",
                "district": "R-OYO",
                "ward": "",
            },
        )

    @patch("django.utils.timezone.now")
    def test_create_local(self, mock_timezone_now):
        now_date = json_date_to_datetime("2020-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date

        remote = TembaContact.create(
            uuid="C-008",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Lagos",
                "lga": "Oyo",
                "ward": "Ikeja",
                "occupation": "Student",
                "born": "1990",
                "gender": "Male",
            },
            language="eng",
        )

        result = PollResult.objects.create(
            org=self.nigeria,
            flow="flow-uuid",
            ruleset="ruleset-uuid",
            contact="C-008",
            completed=False,
            date=json_date_to_datetime("2014-01-02T03:04:05.000Z"),
        )

        result.refresh_from_db()
        self.assertFalse(result.state)

        contact = self.syncer.create_local(self.syncer.local_kwargs(self.nigeria, remote))

        self.assertEqual(contact.org, self.nigeria)
        self.assertEqual(contact.uuid, "C-008")
        self.assertEqual(contact.registered_on, json_date_to_datetime("2014-01-02T03:04:05.000000Z"))
        self.assertEqual(contact.state, "R-LAGOS")

        result.refresh_from_db()
        self.assertFalse(result.state)

        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date

        remote = TembaContact.create(
            uuid="C-009",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2015-04-09T12:48:44.320Z",
                "state": "Lagos",
                "lga": "Oyo",
                "ward": "Ikeja",
                "occupation": "Student",
                "born": "1990",
                "gender": "Male",
            },
            language="eng",
        )

        result = PollResult.objects.create(
            org=self.nigeria,
            flow="flow-uuid",
            ruleset="ruleset-uuid",
            contact="C-009",
            completed=False,
            date=json_date_to_datetime("2015-04-09T12:48:44.320Z"),
        )
        self.assertFalse(result.state)

        contact = self.syncer.create_local(self.syncer.local_kwargs(self.nigeria, remote))

        self.assertEqual(contact.org, self.nigeria)
        self.assertEqual(contact.uuid, "C-009")
        self.assertEqual(contact.registered_on, json_date_to_datetime("2015-04-09T12:48:44.320Z"))
        self.assertEqual(contact.state, "R-LAGOS")

        result.refresh_from_db()
        self.assertFalse(result.state)  # removed updating existing results

    @patch("django.utils.timezone.now")
    def test_update_local(self, mock_timezone_now):
        now_date = json_date_to_datetime("2020-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date

        remote = TembaContact.create(
            uuid="C-008",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
            },
            language="eng",
        )

        result = PollResult.objects.create(
            org=self.nigeria,
            flow="flow-uuid",
            ruleset="ruleset-uuid",
            contact="C-008",
            completed=False,
            category="Yes",
            date=timezone.now() - timedelta(days=180),
        )

        result.refresh_from_db()
        self.assertFalse(result.state)

        contact = self.syncer.create_local(self.syncer.local_kwargs(self.nigeria, remote))

        self.assertEqual(contact.org, self.nigeria)
        self.assertEqual(contact.uuid, "C-008")
        self.assertEqual(contact.registered_on, json_date_to_datetime("2014-01-02T03:04:05.000000Z"))
        self.assertNotEqual(contact.state, "R-LAGOS")

        self.assertEqual(ContactActivity.objects.filter(contact="C-008").count(), 12)
        self.assertFalse(
            ContactActivity.objects.filter(contact="C-008").exclude(state="").exclude(state=None).exists()
        )
        self.assertFalse(
            ContactActivity.objects.filter(contact="C-008").exclude(gender="").exclude(gender=None).exists()
        )
        self.assertFalse(ContactActivity.objects.filter(contact="C-008").exclude(born=None).exists())
        self.assertFalse(
            ContactActivity.objects.filter(contact="C-008").exclude(district="").exclude(district=None).exists()
        )

        remote = TembaContact.create(
            uuid="C-008",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Lagos",
                "lga": "Oyo",
                "ward": "Ikeja",
                "occupation": "Student",
                "born": "1990",
                "gender": "Male",
            },
            language="eng",
        )

        contact = self.syncer.update_local(contact, self.syncer.local_kwargs(self.nigeria, remote))

        self.assertEqual(contact.org, self.nigeria)
        self.assertEqual(contact.uuid, "C-008")
        self.assertEqual(contact.registered_on, json_date_to_datetime("2014-01-02T03:04:05.000000Z"))
        self.assertEqual(contact.state, "R-LAGOS")

        base_qs = ContactActivity.objects.filter(contact="C-008")
        self.assertEqual(base_qs.count(), 12)
        self.assertTrue(base_qs.exclude(state="").exclude(state=None).exists())
        self.assertTrue(base_qs.exclude(gender="").exclude(gender=None).exists())
        self.assertTrue(base_qs.exclude(born=None).exists())
        self.assertTrue(base_qs.exclude(district="").exclude(district=None).exists())
        self.assertTrue(base_qs.filter(state="R-LAGOS").exists())

        self.assertEqual(base_qs.exclude(state="").exclude(state=None).count(), 6)
        self.assertEqual(base_qs.exclude(gender="").exclude(gender=None).count(), 6)
        self.assertEqual(base_qs.exclude(born=None).count(), 6)
        self.assertEqual(base_qs.exclude(district="").exclude(district=None).count(), 6)
        self.assertEqual(base_qs.filter(state="R-LAGOS").count(), 6)


class RapidProBackendTest(UreportTest):
    def setUp(self):
        super(RapidProBackendTest, self).setUp()
        self.backend = RapidProBackend(self.rapidpro_backend)
        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

        self.nigeria.set_config("rapidpro.reporter_group", "Ureporters")
        self.nigeria.set_config("rapidpro.registration_label", "Registration Date")
        self.nigeria.set_config("rapidpro.state_label", "State")
        self.nigeria.set_config("rapidpro.district_label", "LGA")
        self.nigeria.set_config("rapidpro.ward_label", "Ward")
        self.nigeria.set_config("rapidpro.occupation_label", "Activité")
        self.nigeria.set_config("rapidpro.born_label", "Born")
        self.nigeria.set_config("rapidpro.gender_label", "Gender")
        self.nigeria.set_config("rapidpro.female_label", "Female")
        self.nigeria.set_config("rapidpro.male_label", "Male")

        # boundaries fetched
        self.country = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-NIGERIA",
            name="Nigeria",
            backend=self.rapidpro_backend,
            level=Boundary.COUNTRY_LEVEL,
            parent=None,
            geometry='{"foo":"bar-country"}',
        )
        self.state = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-LAGOS",
            name="Lagos",
            backend=self.rapidpro_backend,
            level=Boundary.STATE_LEVEL,
            parent=self.country,
            geometry='{"foo":"bar-state"}',
        )
        self.district = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-OYO",
            name="Oyo",
            backend=self.rapidpro_backend,
            level=Boundary.DISTRICT_LEVEL,
            parent=self.state,
            geometry='{"foo":"bar-state"}',
        )
        self.ward = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-IKEJA",
            name="Ikeja",
            backend=self.rapidpro_backend,
            level=Boundary.WARD_LEVEL,
            parent=self.district,
            geometry='{"foo":"bar-state"}',
        )

        self.registration_date = ContactField.objects.create(
            org=self.nigeria,
            key="registration_date",
            backend=self.rapidpro_backend,
            label="Registration Date",
            value_type="T",
        )

        self.state_field = ContactField.objects.create(
            org=self.nigeria, key="state", label="State", value_type="S", backend=self.rapidpro_backend
        )
        self.district_field = ContactField.objects.create(
            org=self.nigeria, key="lga", label="LGA", value_type="D", backend=self.rapidpro_backend
        )
        self.ward_field = ContactField.objects.create(
            org=self.nigeria, key="ward", label="Ward", value_type="W", backend=self.rapidpro_backend
        )
        self.occupation_field = ContactField.objects.create(
            org=self.nigeria, key="occupation", label="Activité", value_type="T", backend=self.rapidpro_backend
        )

        self.born_field = ContactField.objects.create(
            org=self.nigeria, key="born", label="Born", value_type="T", backend=self.rapidpro_backend
        )
        self.gender_field = ContactField.objects.create(
            org=self.nigeria, key="gender", label="Gender", value_type="T", backend=self.rapidpro_backend
        )

    @patch("dash.orgs.models.TembaClient.get_contacts")
    def test_pull_contacts(self, mock_get_contacts):
        Contact.objects.all().delete()

        # empty fetches
        mock_get_contacts.side_effect = [
            # first call to get active contacts
            MockClientQuery([]),
            # second call to get deleted contacts
            MockClientQuery([]),
        ]

        with self.assertNumQueries(1):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        # fecthed contact not in configured group get ignored
        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Bob McFlow",
                        language="eng",
                        urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="Customers")],
                        fields={"age": "34"},
                        status="active",
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-002", name="Spammers")],
                        fields={"age": "67"},
                        status="active",
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003",
                        name="Ann McPoll",
                        language="eng",
                        urns=["tel:+250783835664"],
                        groups=[],
                        fields={"age": "35"},
                        status="stopped",
                    )
                ],
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status=None,
                    )
                ]
            ),
        ]

        with self.assertNumQueries(5):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 3},
        )

        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Bob McFlow",
                        language="eng",
                        urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "34"},
                        status="active",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-002", name="Spammers")],
                        fields={"age": "67"},
                        status="active",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003",
                        name="Ann McPoll",
                        language="eng",
                        urns=["tel:+250783835664"],
                        groups=[],
                        fields={"age": "35"},
                        status="stopped",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    )
                ],
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status=None,
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    )
                ]
            ),
        ]

        with self.assertNumQueries(10):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 1, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 2},
        )

        Contact.objects.all().delete()

        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Bob McFlow",
                        language="eng",
                        urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "34"},
                        status="active",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "67"},
                        status="active",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003",
                        name="Ann McPoll",
                        language="eng",
                        urns=["tel:+250783835664"],
                        groups=[],
                        fields={"age": "35"},
                        status="stopped",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    )
                ],
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status=None,
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    )
                ]
            ),
        ]

        with self.assertNumQueries(11):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 2, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 1},
        )

        Contact.objects.all().delete()

        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            # all included in the reporters
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Bob McFlow",
                        language="eng",
                        urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "34"},
                        status="active",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "67"},
                        status="active",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003",
                        name="Ann McPoll",
                        language="eng",
                        urns=["tel:+250783835664"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "35"},
                        status="stopped",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    )
                ],
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status=None,
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    )
                ]
            ),
        ]

        with self.assertNumQueries(12):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 3, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        contact_jan = Contact.objects.filter(uuid="C-001").first()
        self.assertFalse(contact_jan.born)
        self.assertFalse(contact_jan.state)

        mock_get_contacts.side_effect = [
            # first call to get active contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Jan",
                        urns=["tel:123"],
                        groups=[
                            ObjectRef.create(uuid="G-001", name="ureporters"),
                            ObjectRef.create(uuid="G-007", name="Actors"),
                        ],
                        fields={
                            "registration_date": "2014-01-02T03:04:05.000000Z",
                            "state": "Nigeria > Lagos",
                            "lga": "Nigeria > Lagos > Oyo",
                            "occupation": "Student",
                            "born": "1990",
                            "gender": "Male",
                        },
                        language="eng",
                        status="active",
                        created_on="2013-01-02T03:04:05.000000Z",
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "67", "born": "1992"},
                        status="active",
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    ),
                ]
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status=None,
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    )
                ]
            ),
        ]

        with self.assertNumQueries(14):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 2, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        contact_jan = Contact.objects.filter(uuid="C-001").first()

        self.assertTrue(contact_jan.born)
        self.assertEqual(contact_jan.born, 1990)
        self.assertTrue(contact_jan.state)
        self.assertEqual(contact_jan.state, "R-LAGOS")

        self.assertTrue(Contact.objects.filter(uuid="C-002", is_active=True))

        mock_get_contacts.side_effect = [
            # first call to get active contacts
            MockClientQuery([]),
            # second call to get deleted contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-002",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status=None,
                        created_on=json_date_to_datetime("2013-01-02T03:04:05.000"),
                    )
                ]
            ),
        ]

        with self.assertNumQueries(4):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 1, SyncOutcome.ignored: 0},
        )

        self.assertFalse(Contact.objects.filter(uuid="C-002", is_active=True))

    @patch("dash.orgs.models.TembaClient.get_fields")
    def test_pull_fields(self, mock_get_fields):
        ContactField.objects.all().delete()

        mock_get_fields.return_value = MockClientQuery(
            [
                TembaField.create(key="nick_name", name="Nickname", type="text"),
                TembaField.create(key="age", name="Age", type="numeric"),
            ]
        )

        with self.assertNumQueries(6):
            field_results = self.backend.pull_fields(self.nigeria)

        self.assertEqual(
            field_results,
            {SyncOutcome.created: 2, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        ContactField.objects.get(key="nick_name", label="Nickname", value_type="T", is_active=True)
        ContactField.objects.get(key="age", label="Age", value_type="N", is_active=True)

        mock_get_fields.return_value = MockClientQuery(
            [
                TembaField.create(key="age", name="Age (Years)", type="numeric"),
                TembaField.create(key="homestate", name="Homestate", type="state"),
            ]
        )

        with self.assertNumQueries(8):
            field_results = self.backend.pull_fields(self.nigeria)

        self.assertEqual(
            field_results,
            {SyncOutcome.created: 1, SyncOutcome.updated: 1, SyncOutcome.deleted: 1, SyncOutcome.ignored: 0},
        )

        self.assertFalse(
            ContactField.objects.filter(org=self.nigeria, key="nick_name", label="Nickname", value_type="T")
        )
        ContactField.objects.get(key="age", label="Age (Years)", value_type="N", is_active=True)
        ContactField.objects.get(key="homestate", label="Homestate", value_type="S", is_active=True)

        # check that no changes means no updates
        with self.assertNumQueries(6):
            field_results = self.backend.pull_fields(self.nigeria)

        self.assertEqual(
            field_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 2},
        )

    @patch("dash.orgs.models.TembaClient.get_boundaries")
    def test_pull_boundaries(self, mock_get_boundaries):
        def release_boundary(boundary):
            for child in boundary.children.all():
                release_boundary(child)

            boundary.delete()

        for boundary in Boundary.objects.all():
            release_boundary(boundary)

        geometry = TembaBoundary.Geometry.create(type="MultiPolygon", coordinates=[[1, 2]])
        parent = TembaBoundary.BoundaryRef.create(osm_id="R123", name="Location")
        remote = TembaBoundary.create(
            osm_id="OLD123", name="OLD", parent=parent, level=Boundary.COUNTRY_LEVEL, geometry=geometry
        )

        mock_get_boundaries.return_value = MockClientQuery([remote])

        with self.assertNumQueries(5):
            boundaries_results = self.backend.pull_boundaries(self.nigeria)

        mock_get_boundaries.assert_called_once_with(geometry=True)

        self.assertEqual(
            boundaries_results,
            {SyncOutcome.created: 1, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        for boundary in Boundary.objects.all():
            release_boundary(boundary)
        mock_get_boundaries.return_value = MockClientQuery(
            [
                TembaBoundary.create(
                    osm_id="OLD123", name="OLD", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
                ),
                TembaBoundary.create(
                    osm_id="NEW123", name="NEW", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
                ),
            ]
        )

        with self.assertNumQueries(6):
            boundaries_results = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual(
            boundaries_results,
            {SyncOutcome.created: 2, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        mock_get_boundaries.return_value = MockClientQuery(
            [
                TembaBoundary.create(
                    osm_id="OLD123", name="CHANGED", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
                ),
                TembaBoundary.create(
                    osm_id="NEW123", name="NEW", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
                ),
            ]
        )

        with self.assertNumQueries(7):
            boundaries_results = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual(
            boundaries_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 1, SyncOutcome.deleted: 0, SyncOutcome.ignored: 1},
        )

        mock_get_boundaries.return_value = MockClientQuery(
            [
                TembaBoundary.create(
                    osm_id="OLD123", name="CHANGED2", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
                ),
                TembaBoundary.create(
                    osm_id="NEW123", name="NEW_CHANGE", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
                ),
            ]
        )

        with self.assertNumQueries(8):
            boundaries_results = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual(
            boundaries_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 2, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        mock_get_boundaries.return_value = MockClientQuery(
            [
                TembaBoundary.create(
                    osm_id="OLD123", name="CHANGED2", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
                )
            ]
        )

        with self.assertNumQueries(7):
            boundaries_results = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual(
            boundaries_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 1, SyncOutcome.ignored: 1},
        )

        mock_get_boundaries.return_value = MockClientQuery(
            [
                TembaBoundary.create(
                    osm_id="OLD123", name="CHANGED2", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
                ),
                TembaBoundary.create(
                    osm_id="NEW123",
                    name="NEW_CHANGE",
                    parent=TembaBoundary.BoundaryRef.create(osm_id="OLD123", name="CHANGED2"),
                    level=Boundary.STATE_LEVEL,
                    geometry=geometry,
                ),
            ]
        )

        with self.assertNumQueries(7):
            boundaries_results = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual(
            boundaries_results,
            {SyncOutcome.created: 1, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 1},
        )

        mock_get_boundaries.return_value = MockClientQuery(
            [
                TembaBoundary.create(
                    osm_id="SOME123", name="Rwanda", parent=None, level=Boundary.COUNTRY_LEVEL, geometry=geometry
                ),
                TembaBoundary.create(
                    osm_id="OTHER123",
                    name="Kigali",
                    parent=TembaBoundary.BoundaryRef.create(osm_id="SOME123", name="Rwanda"),
                    level=Boundary.STATE_LEVEL,
                    geometry=geometry,
                ),
            ]
        )

        with self.assertNumQueries(13):
            boundaries_results = self.backend.pull_boundaries(self.nigeria)

        self.assertEqual(
            boundaries_results,
            {SyncOutcome.created: 2, SyncOutcome.updated: 0, SyncOutcome.deleted: 2, SyncOutcome.ignored: 0},
        )

    @patch("valkey.client.StrictValkey.lock")
    @patch("dash.orgs.models.TembaClient.get_runs")
    @patch("django.utils.timezone.now")
    @patch("django.core.cache.cache.get")
    def test_pull_results(self, mock_cache_get, mock_timezone_now, mock_get_runs, mock_valkey_lock):
        mock_cache_get.return_value = None

        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date

        PollResult.objects.all().delete()
        contact = Contact.objects.create(
            org=self.nigeria, uuid="C-001", gender="M", born=1990, state="R-LAGOS", district="R-OYO"
        )
        poll = self.create_poll(self.nigeria, "Flow 1", "flow-uuid", self.education_nigeria, self.admin)
        self.create_poll_question(self.admin, poll, "question 1", "ruleset-uuid")

        self.create_poll_question(self.admin, poll, "question 2", "ruleset-uuid-2")

        now = timezone.now()
        temba_run = TembaRun.create(
            uuid=1234,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-001", name="Wiz Kid"),
            responded=True,
            values={
                "win": TembaRun.Value.create(value="We'll win today", category="Win", node="ruleset-uuid", time=now)
            },
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, 0, 0, 0, 1),
        )
        mock_get_runs.assert_called_with(flow="flow-uuid", after=None, reverse=True, paths=True)
        mock_valkey_lock.assert_called_once_with(
            Poll.POLL_PULL_RESULTS_TASK_LOCK % (poll.org.pk, poll.flow_uuid), timeout=7200
        )

        poll_result = PollResult.objects.filter(flow="flow-uuid", ruleset="ruleset-uuid", contact="C-001").first()
        self.assertEqual(poll_result.state, "R-LAGOS")
        self.assertEqual(poll_result.district, "R-OYO")
        self.assertEqual(poll_result.contact, "C-001")
        self.assertEqual(poll_result.ruleset, "ruleset-uuid")
        self.assertEqual(poll_result.flow, "flow-uuid")
        self.assertEqual(poll_result.category, "Win")
        self.assertEqual(poll_result.text, "We'll win today")

        temba_run_1 = TembaRun.create(
            uuid=1235,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-002", name="Davido"),
            responded=True,
            values={"sing": TembaRun.Value.create(value="I sing", category="Sing", node="ruleset-uuid", time=now)},
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        temba_run_2 = TembaRun.create(
            uuid=1236,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-003", name="Lebron"),
            responded=True,
            values={
                "play": TembaRun.Value.create(
                    value="I play basketball",
                    category="Play",
                    node="ruleset-uuid",
                    time=now,
                )
            },
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run_1, temba_run_2])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (2, 0, 0, 0, 0, 2),
        )
        self.assertEqual(3, PollResult.objects.all().count())
        self.assertEqual(1, Contact.objects.all().count())

        contact.state = "R-KIGALI"
        contact.district = "R-GASABO"
        contact.save()

        temba_run_3 = TembaRun.create(
            uuid=1234,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-001", name="Wiz Kid"),
            responded=True,
            values={
                "party": TembaRun.Value.create(
                    value="We'll celebrate today",
                    category="Party",
                    node="ruleset-uuid",
                    time=now + timedelta(minutes=1),
                )
            },
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run_3])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 1, 0, 0, 0, 1),
        )

        poll_result = PollResult.objects.filter(flow="flow-uuid", ruleset="ruleset-uuid", contact="C-001").first()
        self.assertEqual(poll_result.state, "R-KIGALI")
        self.assertEqual(poll_result.district, "R-GASABO")
        self.assertEqual(poll_result.contact, "C-001")
        self.assertEqual(poll_result.ruleset, "ruleset-uuid")
        self.assertEqual(poll_result.flow, "flow-uuid")
        self.assertEqual(poll_result.category, "Party")
        self.assertEqual(poll_result.text, "We'll celebrate today")

        mock_get_runs.side_effect = [MockClientQuery([temba_run_3])]
        with self.assertNumQueries(5):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 0, 1, 0, 0, 1),
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run_1, temba_run_2])]

        with self.assertNumQueries(5):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 0, 2, 0, 0, 2),
        )

        PollResult.objects.all().delete()

        # actionset uuid are ignored
        temba_run_4 = TembaRun.create(
            uuid=1234,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-001", name="Wiz Kid"),
            responded=True,
            values={
                "dance": TembaRun.Value.create(
                    value="We'll dance today",
                    category="Dance",
                    node="ruleset-uuid",
                    time=now,
                )
            },
            path=[
                TembaRun.Step.create(node="ruleset-uuid", time=now),
                TembaRun.Step.create(node="actionset-uuid", time=now),
            ],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run_4])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, 0, 0, 0, 2),
        )

        PollResult.objects.all().delete()

        # ruleset without values are considered
        temba_run_4 = TembaRun.create(
            uuid=1234,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-001", name="Wiz Kid"),
            responded=True,
            values={
                "dance": TembaRun.Value.create(
                    value="We'll dance today",
                    category="Dance",
                    node="ruleset-uuid",
                    time=now,
                )
            },
            path=[
                TembaRun.Step.create(node="ruleset-uuid", time=now),
                TembaRun.Step.create(node="actionset-uuid", time=now),
                TembaRun.Step.create(node="ruleset-uuid-2", time=now),
            ],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run_4])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, 0, 1, 0, 2),
        )

        poll_result = PollResult.objects.filter(flow="flow-uuid", ruleset="ruleset-uuid-2", contact="C-001").first()
        self.assertEqual(poll_result.state, "R-KIGALI")
        self.assertEqual(poll_result.district, "R-GASABO")
        self.assertEqual(poll_result.contact, "C-001")
        self.assertEqual(poll_result.ruleset, "ruleset-uuid-2")
        self.assertEqual(poll_result.flow, "flow-uuid")
        self.assertIsNone(poll_result.category)
        self.assertEqual(poll_result.text, "")

        PollResult.objects.filter(ruleset="ruleset-uuid-2").update(date=None)
        mock_get_runs.side_effect = [MockClientQuery([temba_run_4])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 0, 1, 0, 1, 2),
        )

        PollResult.objects.filter(ruleset="ruleset-uuid").update(date=None)
        mock_get_runs.side_effect = [MockClientQuery([temba_run_4])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 1, 0, 0, 0, 3),
        )

        long_text = "Long Text moree " * 100000
        temba_run_long_text = TembaRun.create(
            uuid=1234,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-007", name="Lebron James"),
            responded=True,
            values={
                "party": TembaRun.Value.create(
                    value=long_text,
                    category="Party",
                    node="ruleset-uuid",
                    time=now + timedelta(minutes=1),
                )
            },
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run_long_text])]
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, 0, 0, 0, 1),
        )

        temba_run_none_value = TembaRun.create(
            uuid=1234,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-008", name="James Harden"),
            responded=True,
            values={
                "party": TembaRun.Value.create(
                    value=None, category="Party", node="ruleset-uuid", time=now + timedelta(minutes=1)
                )
            },
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run_none_value])]
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, 0, 0, 0, 1),
        )

        PollResult.objects.all().delete()

        # no response
        temba_run_no_response = TembaRun.create(
            uuid=1234,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-001", name="Wiz Kid"),
            responded=True,
            values={
                "dance": TembaRun.Value.create(value="Whatever", category="No Response", node="ruleset-uuid", time=now)
            },
            path=[
                TembaRun.Step.create(node="ruleset-uuid", time=now),
                TembaRun.Step.create(node="actionset-uuid", time=now),
            ],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run_no_response])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, 0, 0, 0, 2),
        )

        poll_result = PollResult.objects.filter(flow="flow-uuid", ruleset="ruleset-uuid", contact="C-001").first()
        self.assertEqual(poll_result.text, "Whatever")

        poll.stopped_syncing = True
        poll.save()

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 0, 0, 0, 0, 0),
        )

        PollResult.objects.all().delete()
        poll.stopped_syncing = False
        poll.save()

        # When a contact loops into the same node, prevent overwriting the result with a set category
        # with one from path unless they are more that 5 seconds older
        temba_run = TembaRun.create(
            uuid=1234,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-001", name="Wiz Kid"),
            responded=True,
            values={
                "win": TembaRun.Value.create(value="We'll win today", category="Win", node="ruleset-uuid", time=now)
            },
            path=[
                TembaRun.Step.create(node="ruleset-uuid", time=now),
                TembaRun.Step.create(node="ruleset-uuid", time=now + timedelta(seconds=1)),
            ],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, 0, 0, 0, 2),
        )

        poll_result = PollResult.objects.filter(flow="flow-uuid", ruleset="ruleset-uuid", contact="C-001").first()
        self.assertEqual(poll_result.contact, "C-001")
        self.assertEqual(poll_result.ruleset, "ruleset-uuid")
        self.assertEqual(poll_result.flow, "flow-uuid")
        self.assertEqual(poll_result.category, "Win")
        self.assertEqual(poll_result.text, "We'll win today")

    @patch("valkey.client.StrictValkey.lock")
    @patch("ureport.polls.models.Poll.get_flow_date")
    @patch("dash.orgs.models.TembaClient.get_archives")
    @patch("django.utils.timezone.now")
    @patch("requests.get")
    def test_pull_results_from_archives(
        self, mock_request_get, mock_timezone_now, mock_get_archives, mock_poll_flow_date, mock_valkey_lock
    ):
        def gzipped_records(records):
            stream = io.BytesIO()
            gz = gzip.GzipFile(fileobj=stream, mode="wb")

            for record in records:
                gz.write(json.dumps(record).encode("utf-8"))
                gz.write(b"\n")
            gz.close()
            stream.seek(0)
            return MockResponse(200, stream.read())

        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date

        mock_poll_flow_date.return_value = None

        PollResult.objects.all().delete()
        Contact.objects.create(
            org=self.nigeria, uuid="C-001", gender="M", born=1990, state="R-LAGOS", district="R-OYO"
        )
        poll = self.create_poll(self.nigeria, "Flow 1", "flow-uuid", self.education_nigeria, self.admin)
        poll.poll_date = now_date
        poll.save()

        self.create_poll_question(self.admin, poll, "question 1", "ruleset-uuid")

        self.create_poll_question(self.admin, poll, "question 2", "ruleset-uuid-2")

        now = timezone.now()
        temba_run = TembaRun.create(
            uuid=1234,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-001", name="Wiz Kid"),
            responded=True,
            values={
                "win": TembaRun.Value.create(value="We'll win today", category="Win", node="ruleset-uuid", time=now)
            },
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_request_get.side_effect = gzipped_records([temba_run.serialize()])
        mock_get_archives.side_effect = [
            MockClientQuery(
                *[
                    [
                        TembaArchive.create(
                            type="run",
                            start_date=poll.created_on,
                            period="daily",
                            record_count=12,
                            size=23,
                            hash="f0d79988b7772c003d04a28bd7417a62",
                            download_url="http://s3-bucket.aws.com/my/archive.jsonl.gz",
                        )
                    ]
                ]
            )
        ]

        with self.assertNumQueries(5):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results_from_archives(poll)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, 0, 0, 0, 1),
        )

        mock_get_archives.assert_called_with(type="run", after=None)
        mock_valkey_lock.assert_called_once_with(Poll.POLL_PULL_RESULTS_TASK_LOCK % (poll.org.pk, poll.flow_uuid))

        poll_result = PollResult.objects.filter(flow="flow-uuid", ruleset="ruleset-uuid", contact="C-001").first()
        self.assertEqual(poll_result.state, "R-LAGOS")
        self.assertEqual(poll_result.district, "R-OYO")
        self.assertEqual(poll_result.contact, "C-001")
        self.assertEqual(poll_result.ruleset, "ruleset-uuid")
        self.assertEqual(poll_result.flow, "flow-uuid")
        self.assertEqual(poll_result.category, "Win")
        self.assertEqual(poll_result.text, "We'll win today")

        temba_run_1 = TembaRun.create(
            uuid=1235,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-002", name="Davido"),
            responded=True,
            values={"sing": TembaRun.Value.create(value="I sing", category="Sing", node="ruleset-uuid", time=now)},
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        temba_run_2 = TembaRun.create(
            uuid=1236,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid="C-003", name="Lebron"),
            responded=True,
            values={
                "play": TembaRun.Value.create(
                    value="I play basketball",
                    category="Play",
                    node="ruleset-uuid",
                    time=now,
                )
            },
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_request_get.side_effect = gzipped_records([temba_run_1.serialize(), temba_run_2.serialize()])
        mock_get_archives.side_effect = [
            MockClientQuery(
                *[
                    [
                        TembaArchive.create(
                            type="run",
                            start_date=poll.created_on,
                            period="daily",
                            record_count=12,
                            size=23,
                            hash="f0d79988b7772c003d04a28bd7417a62",
                            download_url="http://s3-bucket.aws.com/my/archive.jsonl.gz",
                        )
                    ]
                ]
            )
        ]

        with self.assertNumQueries(5):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results_from_archives(poll)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (2, 0, 0, 0, 0, 2),
        )
        self.assertEqual(3, PollResult.objects.all().count())
        self.assertEqual(1, Contact.objects.all().count())

        poll.stopped_syncing = True
        poll.save()

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results_from_archives(poll)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 0, 0, 0, 0, 0),
        )

    @patch("dash.orgs.models.TembaClient.get_runs")
    @patch("django.utils.timezone.now")
    @patch("django.core.cache.cache.get")
    def test_poll_ward_field(self, mock_cache_get, mock_timezone_now, mock_get_runs):
        mock_cache_get.return_value = None

        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date

        PollResult.objects.all().delete()
        Contact.objects.create(
            org=self.nigeria, uuid="C-021", gender="M", born=1971, state="R-LAGOS", district="R-OYO", ward="R-IKEJA"
        )

        poll = self.create_poll(self.nigeria, "Flow 1", "flow-uuid-3", self.education_nigeria, self.admin)

        self.create_poll_question(self.admin, poll, "question 1", "ruleset-uuid")

        now = timezone.now()
        temba_run = TembaRun.create(
            uuid=4321,
            flow=ObjectRef.create(uuid="flow-uuid-3", name="Flow 2"),
            contact=ObjectRef.create(uuid="C-021", name="Hyped"),
            responded=True,
            values={
                "win": TembaRun.Value.create(value="We'll win today", category="Win", node="ruleset-uuid", time=now)
            },
            path=[TembaRun.Step.create(node="ruleset-uuid", time=now)],
            created_on=now,
            modified_on=now,
            exited_on=now,
            exit_type="completed",
        )

        mock_get_runs.side_effect = [MockClientQuery([temba_run])]

        with self.assertNumQueries(6):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, 0, 0, 0, 1),
        )
        mock_get_runs.assert_called_with(flow="flow-uuid-3", after=None, reverse=True, paths=True)

        poll_result = PollResult.objects.filter(flow="flow-uuid-3", ruleset="ruleset-uuid", contact="C-021").first()
        self.assertEqual(poll_result.ward, "R-IKEJA")

    @patch("ureport.polls.models.Poll.get_flow")
    def test_update_poll_questions(self, mock_poll_flow):
        mock_poll_flow.return_value = dict(
            uuid="uuid-1",
            results=[
                dict(
                    key="color",
                    name="Color",
                    categories=["Orange", "Blue", "Other", "Nothing"],
                    node_uuids=["uuid-101"],
                )
            ],
        )

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.education_nigeria, self.admin, has_synced=True)

        self.backend.update_poll_questions(self.nigeria, poll1, self.admin)

        self.assertEqual(PollQuestion.objects.filter(poll=poll1).count(), 1)
        self.assertEqual(FlowResult.objects.filter(flow_uuid=poll1.flow_uuid).count(), 1)
        question = PollQuestion.objects.filter(poll=poll1).first()
        flow_result = FlowResult.objects.filter(flow_uuid=poll1.flow_uuid).first()

        self.assertEqual(PollResponseCategory.objects.filter(question=question).count(), 4)
        self.assertEqual(FlowResultCategory.objects.filter(flow_result=flow_result).count(), 4)
        self.assertEqual(PollResponseCategory.objects.filter(question=question, is_active=True).count(), 4)
        self.assertEqual(FlowResultCategory.objects.filter(flow_result=flow_result, is_active=True).count(), 4)
        mock_poll_flow.return_value = dict(
            uuid="uuid-1",
            results=[
                dict(
                    key="color",
                    name="Color",
                    categories=["Orange", "Green", "Other", "Nothing"],
                    node_uuids=["uuid-101"],
                )
            ],
        )
        self.backend.update_poll_questions(self.nigeria, poll1, self.admin)

        self.assertEqual(PollQuestion.objects.filter(poll=poll1).count(), 1)
        self.assertEqual(FlowResult.objects.filter(flow_uuid=poll1.flow_uuid).count(), 1)
        question = PollQuestion.objects.filter(poll=poll1).first()
        flow_result = FlowResult.objects.filter(flow_uuid=poll1.flow_uuid).first()

        self.assertEqual(PollResponseCategory.objects.filter(question=question).count(), 5)
        self.assertEqual(FlowResultCategory.objects.filter(flow_result=flow_result).count(), 5)
        self.assertEqual(PollResponseCategory.objects.filter(question=question, is_active=True).count(), 4)
        self.assertEqual(FlowResultCategory.objects.filter(flow_result=flow_result, is_active=True).count(), 4)


class PerfTest(UreportTest):
    def setUp(self):
        super(PerfTest, self).setUp()

        self.backend = RapidProBackend(self.rapidpro_backend)

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

        self.nigeria.set_config("rapidpro.reporter_group", "Ureporters")
        self.nigeria.set_config("rapidpro.registration_label", "Registration Date")
        self.nigeria.set_config("rapidpro.state_label", "State")
        self.nigeria.set_config("rapidpro.district_label", "LGA")
        self.nigeria.set_config("rapidpro.ward_label", "Ward")
        self.nigeria.set_config("rapidpro.occupation_label", "Activité")
        self.nigeria.set_config("rapidpro.born_label", "Born")
        self.nigeria.set_config("rapidpro.gender_label", "Gender")
        self.nigeria.set_config("rapidpro.female_label", "Female")
        self.nigeria.set_config("rapidpro.male_label", "Male")

        # boundaries fetched
        self.country = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-NIGERIA",
            name="Nigeria",
            level=Boundary.COUNTRY_LEVEL,
            parent=None,
            geometry='{"foo":"bar-country"}',
        )
        self.state = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-LAGOS",
            name="Lagos",
            level=Boundary.STATE_LEVEL,
            parent=self.country,
            geometry='{"foo":"bar-state"}',
        )
        self.district = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-OYO",
            name="Oyo",
            level=Boundary.DISTRICT_LEVEL,
            parent=self.state,
            geometry='{"foo":"bar-state"}',
        )
        self.ward = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-IKEJA",
            name="Ikeja",
            level=Boundary.WARD_LEVEL,
            parent=self.district,
            geometry='{"foo":"bar-ward"}',
        )

        self.registration_date = ContactField.objects.create(
            org=self.nigeria, key="registration_date", label="Registration Date", value_type="T"
        )

        self.state_field = ContactField.objects.create(org=self.nigeria, key="state", label="State", value_type="S")
        self.district_field = ContactField.objects.create(org=self.nigeria, key="lga", label="LGA", value_type="D")
        self.occupation_field = ContactField.objects.create(
            org=self.nigeria, key="occupation", label="Activité", value_type="T"
        )

        self.born_field = ContactField.objects.create(org=self.nigeria, key="born", label="Born", value_type="T")
        self.gender_field = ContactField.objects.create(org=self.nigeria, key="gender", label="Gender", value_type="T")

    @override_settings(DEBUG=True)
    @patch("dash.orgs.models.TembaClient.get_runs")
    @patch("django.utils.timezone.now")
    @patch("ureport.polls.models.Poll.get_pull_cached_params")
    def test_pull_results(self, mock_get_pull_cached_params, mock_timezone_now, mock_get_runs):
        mock_get_pull_cached_params.return_value = (None, None)

        from django_valkey import get_valkey_connection

        valkey_client = get_valkey_connection()

        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date

        PollResult.objects.all().delete()

        poll = self.create_poll(self.nigeria, "Flow 1", "flow-uuid", self.education_nigeria, self.admin)

        key = Poll.POLL_PULL_RESULTS_TASK_LOCK % (poll.org.pk, poll.flow_uuid)
        valkey_client.delete(key)

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
                batch.append(
                    TembaRun.create(
                        uuid=num,
                        flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
                        contact=ObjectRef.create(uuid="C-00%d" % num, name=names[num % len(names)]),
                        responded=True,
                        path=[],
                        values={
                            key: val
                            for (key, val) in [
                                (
                                    "category %s" % s,
                                    TembaRun.Value.create(
                                        value="Text %s" % s,
                                        category="Category %s" % s,
                                        node="ruleset-uuid-%d" % s,
                                        time=now,
                                    ),
                                )
                                for s in range(0, num_steps)
                            ]
                        },
                        created_on=now,
                        modified_on=now,
                        exited_on=now,
                        exit_type="",
                    )
                )

            active_fetches.append(batch)

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        mock_get_runs.assert_called_once_with(flow=poll.flow_uuid, after=None, reverse=True, paths=True)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (num_fetches * fetch_size * num_steps, 0, 0, 0, 0, 0),
        )

        slowest_queries = sorted(connection.queries, key=lambda q: q["time"], reverse=True)[:10]
        for q in slowest_queries:
            logger.info("=" * 60)
            logger.info("\n\n\n")
            logger.info("%s -- %s" % (q["time"], q["sql"]))

        reset_queries()

        # simulate a subsequent sync with no changes
        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        valkey_client.delete(key)
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 0, num_fetches * fetch_size * num_steps, 0, 0, 0),
        )

        slowest_queries = sorted(connection.queries, key=lambda q: q["time"], reverse=True)[:10]
        for q in slowest_queries:
            logger.info("%s -- %s" % (q["time"], q["sql"]))

        reset_queries()

        # simulate ignore of 1 value change from older runs
        for batch in active_fetches:
            for r in batch:
                r.values["category 0"] = TembaRun.Value.create(
                    value="Txt 0", category="CAT 0", node="ruleset-uuid-0", time=now - timedelta(minutes=1)
                )
        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        valkey_client.delete(key)
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 0, num_fetches * fetch_size * num_steps, 0, 0, 0),
        )

        slowest_queries = sorted(connection.queries, key=lambda q: q["time"], reverse=True)[:10]
        for q in slowest_queries:
            logger.info("=" * 60)
            logger.info("\n\n\n")
            logger.info("%s -- %s" % (q["time"], q["sql"]))

        reset_queries()

        # simulate an update of 1 value
        for batch in active_fetches:
            for r in batch:
                r.values["category 0"] = TembaRun.Value.create(
                    value="Txt 0", category="CAT 0", node="ruleset-uuid-0", time=now + timedelta(minutes=1)
                )

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        valkey_client.delete(key)
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, num_fetches * fetch_size, num_fetches * fetch_size * (num_steps - 1), 0, 0, 0),
        )

        slowest_queries = sorted(connection.queries, key=lambda q: q["time"], reverse=True)[:10]
        for q in slowest_queries:
            logger.info("=" * 60)
            logger.info("\n\n\n")
            logger.info("%s -- %s" % (q["time"], q["sql"]))

        PollResult.objects.all().update(date=now)
        reset_queries()

        # Test we update the existing map correctly
        for batch in active_fetches:
            for r in batch:
                r.values["category 0"] = TembaRun.Value.create(
                    value="Txt 0", category="CAT 1", node="ruleset-uuid-0", time=now + timedelta(minutes=1)
                )

                r.values["category 1"] = TembaRun.Value.create(
                    value="Txt 0", category="CAT 1", node="ruleset-uuid-0", time=now + timedelta(minutes=1)
                )

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        valkey_client.delete(key)
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, num_fetches * fetch_size, num_fetches * fetch_size * (num_steps - 1), 0, 0, 0),
        )

        slowest_queries = sorted(connection.queries, key=lambda q: q["time"], reverse=True)[:10]
        for q in slowest_queries:
            logger.info("=" * 60)
            logger.info("\n\n\n")
            logger.info("%s -- %s" % (q["time"], q["sql"]))

        PollResult.objects.all().update(date=now)
        reset_queries()

        for batch in active_fetches:
            for r in batch:
                r.values["category 0"] = TembaRun.Value.create(
                    value="Txt 0", category="CAT 2", node="ruleset-uuid-0", time=now + timedelta(minutes=1)
                )

                r.values["category 1"] = TembaRun.Value.create(
                    value="Txt 0", category="CAT 0", node="ruleset-uuid-0", time=now + timedelta(minutes=2)
                )

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        valkey_client.delete(key)
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, num_fetches * fetch_size * 2, num_fetches * fetch_size * (num_steps - 2), 0, 0, 0),
        )

        slowest_queries = sorted(connection.queries, key=lambda q: q["time"], reverse=True)[:10]
        for q in slowest_queries:
            logger.info("=" * 60)
            logger.info("\n\n\n")
            logger.info("%s -- %s" % (q["time"], q["sql"]))

        reset_queries()

        # simulate ignoring actionset nodes
        for batch in active_fetches:
            for r in batch:
                r.path = [TembaRun.Step.create(node="actionset-uuid-0", time=now)]

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        valkey_client.delete(key)
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 0, num_fetches * fetch_size * num_steps, 0, 0, num_fetches * fetch_size),
        )

        slowest_queries = sorted(connection.queries, key=lambda q: q["time"], reverse=True)[:10]
        for q in slowest_queries:
            logger.info("=" * 60)
            logger.info("\n\n\n")
            logger.info("%s -- %s" % (q["time"], q["sql"]))

        PollResult.objects.all().update(date=now)
        reset_queries()

        # simulate an update of 1 value
        for batch in active_fetches:
            for r in batch:
                r.path = []
                r.values = {
                    key: val
                    for key, val in [
                        (
                            "category %s" % s,
                            TembaRun.Value.create(
                                value="T %s" % s,
                                category="C %s" % s,
                                node="ruleset-uuid-0",
                                time=now + timedelta(minutes=int("%d" % (s + 1))),
                            ),
                        )
                        for s in range(0, num_steps)
                    ]
                }

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        valkey_client.delete(key)
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, num_fetches * fetch_size * num_steps, 0, 0, 0, 0),
        )

        slowest_queries = sorted(connection.queries, key=lambda q: q["time"], reverse=True)[:10]
        for q in slowest_queries:
            logger.info("=" * 60)
            logger.info("\n\n\n")
            logger.info("%s -- %s" % (q["time"], q["sql"]))

        reset_queries()

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        valkey_client.set(key, "lock-taken")

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (0, 0, 0, 0, 0, 0),
        )

        valkey_client.delete(key)

        PollResult.objects.all().delete()

        # same contact, same ruleset, same or previous time should all be ignored, only insert one, ignore others
        active_fetches = []
        for b in range(0, num_fetches):
            batch = []
            for r in range(0, fetch_size):
                num = b * fetch_size + r
                batch.append(
                    TembaRun.create(
                        uuid=num,
                        flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
                        contact=ObjectRef.create(uuid="C-001", name="Will"),
                        responded=True,
                        path=[],
                        values={
                            key: val
                            for (key, val) in [
                                (
                                    "category %s" % s,
                                    TembaRun.Value.create(
                                        value="Text %s" % s,
                                        category="Category %s" % s,
                                        node="ruleset-uuid-0",
                                        time=now,
                                    ),
                                )
                                for s in range(0, num_steps)
                            ]
                        },
                        created_on=now,
                        modified_on=now,
                        exited_on=now,
                        exit_type="",
                    )
                )

            active_fetches.append(batch)

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (1, 0, num_fetches * fetch_size * num_steps - 1, 0, 0, 0),
        )

        valkey_client.delete(key)

        PollResult.objects.all().delete()

        with patch("ureport.polls.models.Poll.rebuild_poll_results_counts") as mock_rebuild_counts:
            with patch(
                "ureport.polls.models.Poll.POLL_RESULTS_MAX_SYNC_RUNS", new_callable=PropertyMock
            ) as mock_max_runs:
                mock_max_runs.return_value = 300
                mock_rebuild_counts.return_value = "REBUILT"

                mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

                (
                    num_val_created,
                    num_val_updated,
                    num_val_ignored,
                    num_path_created,
                    num_path_updated,
                    num_path_ignored,
                ) = self.backend.pull_results(poll, None, None)

                # we fetched two pages
                self.assertEqual(
                    (
                        num_val_created,
                        num_val_updated,
                        num_val_ignored,
                        num_path_created,
                        num_path_updated,
                        num_path_ignored,
                    ),
                    (1, 0, 2 * fetch_size * num_steps - 1, 0, 0, 0),
                )

                mock_rebuild_counts.assert_called_with()

                mock_max_runs.return_value = 200
                valkey_client.delete(key)

                PollResult.objects.all().delete()

                mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

                (
                    num_val_created,
                    num_val_updated,
                    num_val_ignored,
                    num_path_created,
                    num_path_updated,
                    num_path_ignored,
                ) = self.backend.pull_results(poll, None, None)

                # we fetched one pages
                self.assertEqual(
                    (
                        num_val_created,
                        num_val_updated,
                        num_val_ignored,
                        num_path_created,
                        num_path_updated,
                        num_path_ignored,
                    ),
                    (1, 0, fetch_size * num_steps - 1, 0, 0, 0),
                )
                mock_rebuild_counts.assert_called_with()

        now_date = datetime_to_json_date(now_date)
        mock_get_pull_cached_params.side_effect = [
            (None, None),
            (None, now_date),
        ]
        with patch("ureport.polls.models.Poll.delete_poll_results") as mock_delete_poll_results:
            mock_delete_poll_results.return_value = "Deleted"

            mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

            self.assertFalse(mock_delete_poll_results.called)

            valkey_client.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (poll.org_id, poll.pk), now_date, None)

            mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

            mock_delete_poll_results.assert_called_with()

    def get_mock_args_list(self, mock_obj):
        args_list = []
        for elt in mock_obj.call_args_list:
            args_list.append(elt[0])

        return args_list

    @override_settings(DEBUG=True)
    @patch("ureport.polls.tasks.pull_refresh.apply_async")
    @patch("django.core.cache.cache.delete")
    @patch("django.core.cache.cache.set")
    @patch("dash.orgs.models.TembaClient.get_runs")
    @patch("django.utils.timezone.now")
    @patch("ureport.polls.models.Poll.get_pull_cached_params")
    @patch("ureport.polls.models.Poll.rebuild_poll_results_counts")
    @patch("ureport.polls.models.Poll.POLL_RESULTS_MAX_SYNC_RUNS", new_callable=PropertyMock)
    def test_pull_results_batching(
        self,
        mock_max_runs,
        mock_rebuild_counts,
        mock_get_pull_cached_params,
        mock_timezone_now,
        mock_get_runs,
        mock_cache_set,
        mock_cache_delete,
        mock_pull_refresh,
    ):
        mock_max_runs.return_value = 300
        mock_rebuild_counts.return_value = "REBUILT"
        mock_get_pull_cached_params.side_effect = [(None, None)]

        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        day_ago = now_date - timedelta(hours=24)
        two_days_ago = now_date - timedelta(hours=24)

        mock_timezone_now.return_value = now_date

        PollResult.objects.all().delete()

        poll = self.create_poll(self.nigeria, "Flow 1", "flow-uuid", self.education_nigeria, self.admin)

        now = timezone.now()

        fetch_size = 250
        num_fetches = 4
        num_steps = 5
        names = ["Ann", "Bob", "Cat"]
        dates = [day_ago, day_ago, two_days_ago, two_days_ago]

        active_fetches = []
        for b in range(0, num_fetches):
            batch = []
            for r in range(0, fetch_size):
                num = b * fetch_size + r
                batch.append(
                    TembaRun.create(
                        uuid=num,
                        flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
                        contact=ObjectRef.create(uuid="C-00%d" % num, name=names[num % len(names)]),
                        responded=True,
                        path=[],
                        values={
                            key: val
                            for (key, val) in [
                                (
                                    "category %s" % s,
                                    TembaRun.Value.create(
                                        value="Text %s" % s,
                                        category="Category %s" % s,
                                        node="ruleset-uuid-%d" % s,
                                        time=now,
                                    ),
                                )
                                for s in range(0, num_steps)
                            ]
                        },
                        created_on=dates[b],
                        modified_on=dates[b],
                        exited_on=now,
                        exit_type="",
                    )
                )

            active_fetches.append(batch)

        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        expected_args = [
            (
                Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-07T12:48:44.320Z",
                None,
            ),
        ]

        self.assertEqual(set(expected_args), set(self.get_mock_args_list(mock_cache_set)))
        self.assertFalse(mock_cache_delete.called)
        mock_pull_refresh.assert_called_once_with((poll.pk,), countdown=300, queue="sync")

        mock_max_runs.return_value = 10000
        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]
        mock_get_pull_cached_params.side_effect = [(None, None)]

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        expected_args = [
            (
                Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-07T12:48:44.320Z",
                None,
            ),
            (
                Poll.POLL_RESULTS_LAST_SYNC_TIME_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-08T12:48:44.320Z",
                None,
            ),
            (
                Poll.POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-08T12:48:44.320Z",
                60 * 60 * 24 * 2,
            ),
        ]

        self.assertEqual(set(expected_args), set(self.get_mock_args_list(mock_cache_set)))

        mock_cache_set.reset_mock()
        mock_max_runs.return_value = 10000
        mock_get_pull_cached_params.side_effect = [(None, None)]
        mock_get_runs.side_effect = [MockClientQuery(*active_fetches)]
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        expected_args = [
            (
                Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-07T12:48:44.320Z",
                None,
            ),
            (
                Poll.POLL_RESULTS_LAST_SYNC_TIME_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-08T12:48:44.320Z",
                None,
            ),
            (
                Poll.POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-08T12:48:44.320Z",
                60 * 60 * 24 * 2,
            ),
        ]

        self.assertEqual(set(expected_args), set(self.get_mock_args_list(mock_cache_set)))
        mock_cache_set.reset_mock()

        mock_get_pull_cached_params.side_effect = [("2015-04-05T12:48:44.320Z", None)]
        mock_get_runs.side_effect = [MockClientQuery(*[])]

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        expected_args = [
            (
                Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-05T12:48:44.320Z",
                None,
            ),
            (
                Poll.POLL_RESULTS_LAST_SYNC_TIME_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-08T12:48:44.320Z",
                None,
            ),
            (
                Poll.POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid),
                "2015-04-08T12:48:44.320Z",
                60 * 60 * 24 * 2,
            ),
        ]

        self.assertEqual(set(expected_args), set(self.get_mock_args_list(mock_cache_set)))
        mock_get_runs.reset_mock()
        mock_get_pull_cached_params.side_effect = [
            (
                "2015-04-05T12:48:44.320Z",
                "2015-04-07T12:48:44.320Z",
            )
        ]
        mock_get_runs.side_effect = [MockClientQuery(*[])]

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        expected_args = [
            (Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (poll.org_id, poll.pk),),
            (Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (poll.org.pk, poll.flow_uuid),),
        ]

        self.assertEqual(set(expected_args), set(self.get_mock_args_list(mock_cache_delete)))
        mock_get_runs.assert_called_once_with(flow=poll.flow_uuid, after=None, reverse=True, paths=True)

    @override_settings(DEBUG=True)
    @patch("dash.orgs.models.TembaClient._request")
    @patch("ureport.polls.tasks.pull_refresh.apply_async")
    @patch("django.core.cache.cache.set")
    @patch("django.utils.timezone.now")
    @patch("ureport.polls.models.Poll.get_pull_cached_params")
    def test_pull_results_batching_error(
        self,
        mock_get_pull_cached_params,
        mock_timezone_now,
        mock_cache_set,
        mock_pull_refresh,
        mock_base_client_request,
    ):
        now_date = json_date_to_datetime("2015-04-08T12:48:44.320Z")
        mock_timezone_now.return_value = now_date

        PollResult.objects.all().delete()

        poll = self.create_poll(self.nigeria, "Flow 1", "flow-uuid", self.education_nigeria, self.admin)

        mock_get_pull_cached_params.side_effect = [(None, None)]
        mock_base_client_request.side_effect = [TembaRateExceededError(0)]

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = self.backend.pull_results(poll, None, None)

        expected_args = [
            (Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, poll.flow_uuid), None, None),
        ]

        self.assertEqual(set(expected_args), set(self.get_mock_args_list(mock_cache_set)))
        mock_pull_refresh.assert_called_once_with((poll.pk,), countdown=300, queue="sync")
