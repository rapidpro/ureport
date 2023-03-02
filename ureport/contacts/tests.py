# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from mock import patch

from dash.orgs.models import TaskState
from dash.utils.sync import SyncOutcome
from ureport.contacts.models import Contact, ContactField, ReportersCounter
from ureport.contacts.tasks import check_contacts_count_mismatch, pull_contacts, update_org_contact_count
from ureport.locations.models import Boundary
from ureport.tests import TestBackend, UreportTest
from ureport.utils import json_date_to_datetime


class ContactTest(UreportTest):
    def setUp(self):
        super(ContactTest, self).setUp()
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
        self.ward_field = ContactField.objects.create(org=self.nigeria, key="ward", label="Ward", value_type="W")
        self.occupation_field = ContactField.objects.create(
            org=self.nigeria, key="occupation", label="Activité", value_type="T"
        )

        self.born_field = ContactField.objects.create(org=self.nigeria, key="born", label="Born", value_type="T")
        self.gender_field = ContactField.objects.create(org=self.nigeria, key="gender", label="Gender", value_type="T")

    def test_get_or_create(self):
        self.assertIsNone(Contact.objects.filter(org=self.nigeria, uuid="contact-uuid").first())

        created_contact = Contact.get_or_create(self.nigeria, "contact-uuid")

        self.assertTrue(created_contact)
        self.assertIsNone(created_contact.born)

        created_contact.born = "2000"
        created_contact.save()

        existing_contact = Contact.get_or_create(self.nigeria, "contact-uuid")
        self.assertEqual(created_contact.pk, existing_contact.pk)
        self.assertEqual(existing_contact.born, 2000)

    def test_create_users_in_different_orgs(self):
        self.assertIsNone(Contact.objects.filter(org=self.nigeria, uuid="contact-uuid").first())
        self.assertIsNone(Contact.objects.filter(org=self.uganda, uuid="contact-uuid").first())

        created_contact_nigeria = Contact.get_or_create(self.nigeria, "contact-uuid")
        created_contact_uganda = Contact.get_or_create(self.uganda, "contact-uuid")

        self.assertNotEqual(created_contact_uganda.id, created_contact_nigeria.id)
        self.assertEqual(created_contact_uganda.uuid, created_contact_nigeria.uuid)

        Contact.objects.all().delete()

        created_contact_nigeria_1 = Contact.get_or_create(self.nigeria, "contact-uuid")
        created_contact_nigeria_2 = Contact.get_or_create(self.nigeria, "contact-uuid")

        self.assertEqual(created_contact_nigeria_1.id, created_contact_nigeria_2.id)
        self.assertEqual(Contact.objects.filter(org=self.nigeria, uuid="contact-uuid").count(), 1)

    def test_contact_ward_field(self):
        self.assertEqual(ReportersCounter.get_counts(self.nigeria), dict())
        Contact.objects.create(
            uuid="C-007",
            org=self.nigeria,
            gender="M",
            born=1990,
            occupation="Student",
            registered_on=json_date_to_datetime("2014-01-02T03:04:05.000"),
            state="R-LAGOS",
            district="R-OYO",
            ward="R-IKEJA",
        )
        field_count = ReportersCounter.get_counts(self.nigeria)

        self.assertEqual(field_count["ward:R-IKEJA"], 1)

        Contact.objects.create(
            uuid="C-008",
            org=self.nigeria,
            gender="M",
            born=1980,
            occupation="Teacher",
            registered_on=json_date_to_datetime("2014-01-02T03:07:05.000"),
            state="R-LAGOS",
            district="R-OYO",
            ward="R-IKEJA",
        )

        field_count = ReportersCounter.get_counts(self.nigeria)
        self.assertEqual(field_count["ward:R-IKEJA"], 2)
        Contact.objects.all().delete()

    def test_recalculate_reporters_stats(self):
        self.assertEqual(ReportersCounter.get_counts(self.nigeria), dict())
        Contact.objects.create(
            uuid="C-007",
            org=self.nigeria,
            gender="M",
            born=1990,
            occupation="Student",
            registered_on=json_date_to_datetime("2014-01-02T03:04:05.000"),
            state="R-LAGOS",
            district="R-OYO",
            scheme="tel",
        )

        expected = dict()
        expected["total-reporters"] = 1
        expected["gender:m"] = 1
        expected["occupation:student"] = 1
        expected["born:1990"] = 1
        expected["registered_on:2014-01-02"] = 1
        expected["registered_gender:2014-01-02:m"] = 1
        expected["registered_born:2014-01-02:1990"] = 1
        expected["registered_state:2014-01-02:R-LAGOS"] = 1
        expected["registered_scheme:2014-01-02:tel"] = 1
        expected["state:R-LAGOS"] = 1
        expected["district:R-OYO"] = 1
        expected["scheme:tel"] = 1

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)
        Contact.recalculate_reporters_stats(self.nigeria)

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

        Contact.objects.create(
            uuid="C-008",
            org=self.nigeria,
            gender="M",
            born=1980,
            occupation="Teacher",
            registered_on=json_date_to_datetime("2014-01-02T03:07:05.000"),
            state="R-LAGOS",
            district="R-OYO",
            scheme="facebook",
        )

        expected = dict()
        expected["total-reporters"] = 2
        expected["gender:m"] = 2
        expected["occupation:student"] = 1
        expected["occupation:teacher"] = 1
        expected["born:1990"] = 1
        expected["born:1980"] = 1
        expected["registered_on:2014-01-02"] = 2
        expected["registered_gender:2014-01-02:m"] = 2
        expected["registered_born:2014-01-02:1990"] = 1
        expected["registered_born:2014-01-02:1980"] = 1
        expected["registered_state:2014-01-02:R-LAGOS"] = 2
        expected["registered_scheme:2014-01-02:tel"] = 1
        expected["registered_scheme:2014-01-02:facebook"] = 1
        expected["state:R-LAGOS"] = 2
        expected["district:R-OYO"] = 2
        expected["scheme:tel"] = 1
        expected["scheme:facebook"] = 1

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)
        Contact.recalculate_reporters_stats(self.nigeria)

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

        contact = Contact.objects.create(
            is_active=True,
            uuid="C-009",
            org=self.nigeria,
            gender="M",
            born=1980,
            occupation="Teacher",
            registered_on=json_date_to_datetime("2014-01-02T03:07:05.000"),
            state="R-LAGOS",
            district="R-OYO",
        )
        contact.is_active = False
        contact.save()

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)
        Contact.recalculate_reporters_stats(self.nigeria)

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

    def test_reporters_counter(self):
        self.assertEqual(ReportersCounter.get_counts(self.nigeria), dict())
        Contact.objects.create(
            uuid="C-007",
            org=self.nigeria,
            gender="M",
            born=1990,
            occupation="Student",
            registered_on=json_date_to_datetime("2014-01-02T03:04:05.000"),
            state="R-LAGOS",
            district="R-OYO",
            scheme="tel",
        )

        expected = dict()
        expected["total-reporters"] = 1
        expected["gender:m"] = 1
        expected["occupation:student"] = 1
        expected["born:1990"] = 1
        expected["registered_on:2014-01-02"] = 1
        expected["registered_gender:2014-01-02:m"] = 1
        expected["registered_born:2014-01-02:1990"] = 1
        expected["registered_state:2014-01-02:R-LAGOS"] = 1
        expected["registered_scheme:2014-01-02:tel"] = 1
        expected["state:R-LAGOS"] = 1
        expected["district:R-OYO"] = 1
        expected["scheme:tel"] = 1

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

        Contact.objects.create(
            uuid="C-008",
            org=self.nigeria,
            gender="M",
            born=1980,
            occupation="Teacher",
            registered_on=json_date_to_datetime("2014-01-02T03:07:05.000"),
            state="R-LAGOS",
            district="R-OYO",
            scheme="facebook",
        )

        expected = dict()
        expected["total-reporters"] = 2
        expected["gender:m"] = 2
        expected["occupation:student"] = 1
        expected["occupation:teacher"] = 1
        expected["born:1990"] = 1
        expected["born:1980"] = 1
        expected["registered_on:2014-01-02"] = 2
        expected["registered_gender:2014-01-02:m"] = 2
        expected["registered_born:2014-01-02:1990"] = 1
        expected["registered_born:2014-01-02:1980"] = 1
        expected["registered_state:2014-01-02:R-LAGOS"] = 2
        expected["registered_scheme:2014-01-02:tel"] = 1
        expected["registered_scheme:2014-01-02:facebook"] = 1
        expected["state:R-LAGOS"] = 2
        expected["district:R-OYO"] = 2
        expected["scheme:tel"] = 1
        expected["scheme:facebook"] = 1

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

        self.assertEqual(
            ReportersCounter.get_counts(self.nigeria, ["total-reporters", "gender:m"]),
            {"total-reporters": 2, "gender:m": 2},
        )

    @patch("redis.client.StrictRedis.get")
    def test_squash_reporters(self, mock_redis_get):
        mock_redis_get.return_value = None

        self.assertFalse(ReportersCounter.objects.all())

        counter1 = ReportersCounter.objects.create(org=self.nigeria, type="type-a", count=2)
        counter2 = ReportersCounter.objects.create(org=self.nigeria, type="type-b", count=1)
        counter3 = ReportersCounter.objects.create(org=self.nigeria, type="type-a", count=3)

        self.assertEqual(ReportersCounter.objects.all().count(), 3)
        self.assertEqual(ReportersCounter.objects.filter(type="type-a").count(), 2)

        ReportersCounter.squash_counts()

        self.assertEqual(ReportersCounter.objects.all().count(), 2)
        # type-a counters are squashed into one row
        self.assertFalse(ReportersCounter.objects.filter(pk__in=[counter1.pk, counter3.pk]))
        self.assertEqual(ReportersCounter.objects.filter(type="type-a").count(), 1)

        self.assertTrue(ReportersCounter.objects.filter(pk=counter2.pk))

        counter_type_a = ReportersCounter.objects.filter(type="type-a").first()

        self.assertTrue(counter_type_a.count, 5)


class ContactsTasksTest(UreportTest):
    def setUp(self):
        super(ContactsTasksTest, self).setUp()

    @patch("redis.client.StrictRedis.get")
    @patch("django.core.cache.cache.set")
    @patch("ureport.contacts.models.ReportersCounter.get_counts")
    def test_check_contacts_count_mismatch(self, mock_counter_counts, mock_cache_set, mock_redis_get):
        mock_redis_get.return_value = None
        mock_counter_counts.return_value = {"total-reporters": 1000}

        for i in range(1250):
            Contact.objects.create(
                org=self.nigeria, uuid=f"C-00{i}", gender="M", born=1990, state="R-LAGOS", district="R-OYO"
            )

        check_contacts_count_mismatch()

        mock_cache_set.assert_called_once_with(
            "contact_counts_status",
            {
                "mismatch_counts": {
                    f"{self.uganda.pk}": {"db": 0, "count": 1000, "count_diff": 1000, "pct_diff": 0},
                    f"{self.nigeria.pk}": {"db": 1250, "count": 1000, "count_diff": 250, "pct_diff": 0.2},
                },
                "error_counts": {
                    f"{self.uganda.pk}": {"db": 0, "count": 1000, "count_diff": 1000, "pct_diff": 0},
                    f"{self.nigeria.pk}": {"db": 1250, "count": 1000, "count_diff": 250, "pct_diff": 0.2},
                },
            },
            None,
        )

        mock_cache_set.reset_mock()
        mock_counter_counts.side_effect = [{"total-reporters": 0}, {"total-reporters": 1250}]

        check_contacts_count_mismatch()

        mock_cache_set.assert_called_once_with(
            "contact_counts_status", {"mismatch_counts": {}, "error_counts": {}}, None
        )

        mock_redis_get.side_effect = ["foo_locked_task_running", None]
        mock_cache_set.reset_mock()
        mock_counter_counts.side_effect = [{"total-reporters": 1000}, {"total-reporters": 1000}]

        check_contacts_count_mismatch()

        mock_cache_set.assert_called_once_with(
            "contact_counts_status",
            {
                "mismatch_counts": {
                    f"{self.uganda.pk}": {
                        "db": 0,
                        "count": 1000,
                        "count_diff": 1000,
                        "pct_diff": 0,
                        "message": "contact task running",
                    },
                    f"{self.nigeria.pk}": {"db": 1250, "count": 1000, "count_diff": 250, "pct_diff": 0.2},
                },
                "error_counts": {
                    f"{self.nigeria.pk}": {"db": 1250, "count": 1000, "count_diff": 250, "pct_diff": 0.2},
                },
            },
            None,
        )

    @patch("ureport.contacts.tasks.update_cache_org_contact_counts")
    def test_update_org_contact_count(self, mock_update_cache_org_contact_counts):
        mock_update_cache_org_contact_counts.return_value = "Called"

        update_org_contact_count(self.nigeria.pk)

        mock_update_cache_org_contact_counts.assert_called_once_with(self.nigeria)

    @patch("dash.orgs.models.Org.get_backend")
    @patch("ureport.contacts.models.ReportersCounter.squash_counts")
    @patch("ureport.tests.TestBackend.pull_fields")
    @patch("ureport.tests.TestBackend.pull_boundaries")
    @patch("ureport.tests.TestBackend.pull_contacts")
    def test_pull_contacts(
        self, mock_pull_contacts, mock_pull_boundaries, mock_pull_fields, mock_squash_counts, mock_get_backend
    ):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_pull_fields.return_value = {
            SyncOutcome.created: 1,
            SyncOutcome.updated: 2,
            SyncOutcome.deleted: 3,
            SyncOutcome.ignored: 4,
        }
        mock_pull_boundaries.return_value = {
            SyncOutcome.created: 5,
            SyncOutcome.updated: 6,
            SyncOutcome.deleted: 7,
            SyncOutcome.ignored: 8,
        }
        mock_pull_contacts.return_value = (
            {SyncOutcome.created: 9, SyncOutcome.updated: 10, SyncOutcome.deleted: 11, SyncOutcome.ignored: 12},
            None,
        )
        mock_squash_counts.return_value = "Called"

        # keep only on backend config
        self.nigeria.backends.exclude(slug="rapidpro").delete()

        pull_contacts(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key="contact-pull")
        self.assertEqual(
            task_state.get_last_results(),
            {
                "rapidpro": {
                    "fields": {"created": 1, "updated": 2, "deleted": 3},
                    "boundaries": {"created": 5, "updated": 6, "deleted": 7},
                    "contacts": {"created": 9, "updated": 10, "deleted": 11},
                }
            },
        )

        # mock_squash_counts.assert_called_once_with()
