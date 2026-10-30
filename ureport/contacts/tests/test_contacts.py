# -*- coding: utf-8 -*-

import importlib
from datetime import timedelta

from django_valkey import get_valkey_connection
from mock import patch

from django.conf import settings
from django.db import connection
from django.utils import timezone

from dash.orgs.models import TaskState
from ureport.contacts.models import Contact, ContactField, ReportersCounter
from ureport.contacts.tasks import (
    check_contacts_count_mismatch,
    pull_contacts,
    squash_reporters_counts,
    update_org_contact_count,
)
from ureport.locations.models import Boundary
from ureport.syncjobs.models import SyncJob
from ureport.syncjobs.tests.base import held_lock
from ureport.tests import UreportTest
from ureport.utils import json_date_to_datetime


class ContactTest(UreportTest):
    def setUp(self):
        super(ContactTest, self).setUp()
        self.nigeria.set_config("rapidpro.reporter_group", "Ureporters")
        self.nigeria.set_config("rapidpro.registration_label", "Registration Date")
        self.nigeria.set_config("rapidpro.state_label", "State")
        self.nigeria.set_config("rapidpro.district_label", "LGA")
        self.nigeria.set_config("rapidpro.ward_label", "Ward")
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
            registered_on=json_date_to_datetime("2014-01-02T03:04:05.000"),
            state="R-LAGOS",
            district="R-OYO",
            scheme="tel",
        )

        expected = dict()
        expected["total-reporters"] = 1
        expected["gender:m"] = 1
        expected["born:1990"] = 1
        expected["state:R-LAGOS"] = 1
        expected["district:R-OYO"] = 1
        expected["scheme:tel"] = 1

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)
        Contact.recalculate_reporters_stats(self.nigeria)

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

        signup_date = timezone.now() - timedelta(days=300)

        Contact.objects.create(
            uuid="C-008",
            org=self.nigeria,
            gender="M",
            born=1980,
            registered_on=signup_date,
            state="R-LAGOS",
            district="R-OYO",
            scheme="facebook",
        )

        expected = dict()
        expected["total-reporters"] = 2
        expected["gender:m"] = 2
        expected["born:1990"] = 1
        expected["born:1980"] = 1
        expected[f"registered_on:{signup_date.date()}"] = 1
        expected[f"registered_gender:{signup_date.date()}:m"] = 1
        expected[f"registered_born:{signup_date.date()}:1980"] = 1
        expected[f"registered_state:{signup_date.date()}:R-LAGOS"] = 1
        expected[f"registered_scheme:{signup_date.date()}:facebook"] = 1
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
        signup_date = timezone.now() - timedelta(days=300)
        self.assertEqual(ReportersCounter.get_counts(self.nigeria), dict())
        Contact.objects.create(
            uuid="C-007",
            org=self.nigeria,
            gender="M",
            born=1990,
            registered_on=signup_date,
            state="R-LAGOS",
            district="R-OYO",
            scheme="tel",
        )

        expected = dict()
        expected["total-reporters"] = 1
        expected["gender:m"] = 1
        expected["born:1990"] = 1
        expected[f"registered_on:{signup_date.date()}"] = 1
        expected[f"registered_gender:{signup_date.date()}:m"] = 1
        expected[f"registered_born:{signup_date.date()}:1990"] = 1
        expected[f"registered_state:{signup_date.date()}:R-LAGOS"] = 1
        expected[f"registered_scheme:{signup_date.date()}:tel"] = 1
        expected["state:R-LAGOS"] = 1
        expected["district:R-OYO"] = 1
        expected["scheme:tel"] = 1

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

        Contact.objects.create(
            uuid="C-008",
            org=self.nigeria,
            gender="M",
            born=1980,
            registered_on=signup_date,
            state="R-LAGOS",
            district="R-OYO",
            scheme="facebook",
        )

        expected = dict()
        expected["total-reporters"] = 2
        expected["gender:m"] = 2
        expected["born:1990"] = 1
        expected["born:1980"] = 1
        expected[f"registered_on:{signup_date.date()}"] = 2
        expected[f"registered_gender:{signup_date.date()}:m"] = 2
        expected[f"registered_born:{signup_date.date()}:1990"] = 1
        expected[f"registered_born:{signup_date.date()}:1980"] = 1
        expected[f"registered_state:{signup_date.date()}:R-LAGOS"] = 2
        expected[f"registered_scheme:{signup_date.date()}:tel"] = 1
        expected[f"registered_scheme:{signup_date.date()}:facebook"] = 1
        expected["state:R-LAGOS"] = 2
        expected["district:R-OYO"] = 2
        expected["scheme:tel"] = 1
        expected["scheme:facebook"] = 1

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), expected)

        self.assertEqual(
            ReportersCounter.get_counts(self.nigeria, ["total-reporters", "gender:m"]),
            {"total-reporters": 2, "gender:m": 2},
        )

    def test_squash_reporters(self):
        def rows():
            return set(ReportersCounter.objects.values_list("id", "org_id", "type", "count", "is_squashed"))

        def totals():
            return ReportersCounter.get_counts(self.nigeria), ReportersCounter.get_counts(self.uganda)

        # nothing to squash
        ReportersCounter.squash_counts()
        self.assertFalse(ReportersCounter.objects.exists())

        # deltas as the contact triggers insert them, relying on the database default
        with connection.cursor() as c:
            c.execute(
                "INSERT INTO contacts_reporterscounter (org_id, type, count) VALUES (%s, 'type-a', 2), "
                "(%s, 'type-a', 3), (%s, 'type-b', 1), (%s, 'type-a', 4)",
                (self.nigeria.id, self.nigeria.id, self.nigeria.id, self.uganda.id),
            )
        self.assertFalse(ReportersCounter.objects.filter(is_squashed=True).exists())
        expected_totals = totals()

        ReportersCounter.squash_counts()

        # each group gets a single squashed row
        self.assertEqual(
            {("type-a", 5), ("type-b", 1)},
            set(ReportersCounter.objects.filter(org=self.nigeria, is_squashed=True).values_list("type", "count")),
        )
        self.assertEqual(ReportersCounter.objects.count(), 3)
        self.assertFalse(ReportersCounter.objects.filter(is_squashed=False).exists())
        self.assertEqual(totals(), expected_totals)
        squashed = rows()

        # passes with no new deltas write nothing
        ReportersCounter.squash_counts()
        ReportersCounter.squash_counts()
        self.assertEqual(rows(), squashed)

        # new deltas are added onto their group's squashed row, which keeps its id, and other groups are untouched
        nigeria_a = ReportersCounter.objects.get(org=self.nigeria, type="type-a")
        ReportersCounter.objects.create(org=self.nigeria, type="type-a", count=-1)
        ReportersCounter.objects.create(org=self.nigeria, type="type-a", count=3)
        ReportersCounter.objects.create(org=self.nigeria, type="type-c", count=2)

        ReportersCounter.squash_counts()

        self.assertEqual(ReportersCounter.objects.get(org=self.nigeria, type="type-a"), nigeria_a)
        self.assertEqual(ReportersCounter.objects.get(pk=nigeria_a.pk).count, 7)
        self.assertEqual(ReportersCounter.objects.get(org=self.nigeria, type="type-c").count, 2)
        self.assertTrue({row for row in squashed if row[2] == "type-b" or row[1] == self.uganda.id} <= rows())
        self.assertEqual(totals(), ({"type-a": 7, "type-b": 1, "type-c": 2}, expected_totals[1]))

    def test_squash_reporters_never_below_zero(self):
        squashed = ReportersCounter.objects.create(org=self.nigeria, type="type-a", count=2, is_squashed=True)

        # a squashed row that reaches zero is deleted
        ReportersCounter.objects.create(org=self.nigeria, type="type-a", count=-2)
        ReportersCounter.squash_counts()
        self.assertFalse(ReportersCounter.objects.filter(pk=squashed.pk).exists())

        # as is one that would go below zero
        ReportersCounter.objects.create(org=self.nigeria, type="type-b", count=1, is_squashed=True)
        ReportersCounter.objects.create(org=self.nigeria, type="type-b", count=-3)
        ReportersCounter.squash_counts()
        self.assertFalse(ReportersCounter.objects.filter(type="type-b").exists())

        # and a group without one only gets one if its deltas sum above zero
        ReportersCounter.objects.create(org=self.nigeria, type="type-c", count=-1)
        ReportersCounter.objects.create(org=self.nigeria, type="type-d", count=0)
        ReportersCounter.objects.create(org=self.nigeria, type="type-e", count=-1)
        ReportersCounter.objects.create(org=self.nigeria, type="type-e", count=2)
        ReportersCounter.squash_counts()
        self.assertEqual(
            [("type-e", 1, True)], list(ReportersCounter.objects.values_list("type", "count", "is_squashed"))
        )

        self.assertEqual(ReportersCounter.get_counts(self.nigeria), {"type-e": 1})

    def test_squash_reporters_skipped_while_running(self):
        ReportersCounter.objects.create(org=self.nigeria, type="type-a", count=2)

        with held_lock(ReportersCounter.COUNTS_SQUASH_LOCK):
            ReportersCounter.squash_counts()

        self.assertFalse(ReportersCounter.objects.filter(is_squashed=True).exists())

    def test_merge_squashed_reporters_counters(self):
        migration = importlib.import_module("ureport.contacts.migrations.0032_reporterscounter_squashed_unique")

        # put the table back as it is before the migration, with existing rows all counted as squashed
        with connection.cursor() as c:
            c.execute('DROP INDEX "contacts_rptrscntr_squashed"')

        def add(org, type_, count):
            ReportersCounter.objects.create(org=org, type=type_, count=count, is_squashed=True)

        add(self.nigeria, "type-a", 2)
        add(self.nigeria, "type-a", 3)
        add(self.uganda, "type-a", 4)
        add(self.nigeria, "type-b", 2)
        add(self.nigeria, "type-b", -3)
        add(self.nigeria, "type-c", 0)
        add(self.nigeria, "type-d", -1)
        single = ReportersCounter.objects.get(org=self.uganda, type="type-a")
        ReportersCounter.objects.create(org=self.nigeria, type="type-a", count=1)

        migration.merge_squashed(None, connection.schema_editor())

        # groups are merged, or dropped if they don't sum above zero, single rows above zero and unsquashed rows are
        # left alone
        self.assertEqual(
            {
                (self.nigeria.id, "type-a", 5, True),
                (self.nigeria.id, "type-a", 1, False),
                (self.uganda.id, "type-a", 4, True),
            },
            set(ReportersCounter.objects.values_list("org_id", "type", "count", "is_squashed")),
        )
        self.assertTrue(ReportersCounter.objects.filter(pk=single.pk).exists())
        self.assertIsNone(get_valkey_connection().get(ReportersCounter.COUNTS_SQUASH_LOCK))

    def test_recalculate_reporters_stats_waits_for_squashing(self):
        Contact.objects.create(uuid="C-007", org=self.nigeria, gender="M")
        ReportersCounter.objects.create(org=self.nigeria, type="gender:m", count=5)

        with patch.object(ReportersCounter, "REPLACE_COUNTS_LOCK_TIMEOUT", 1):
            with held_lock(ReportersCounter.COUNTS_SQUASH_LOCK):
                self.assertIsNone(Contact.recalculate_reporters_stats(self.nigeria))

        # the counters are left as they were
        self.assertEqual(ReportersCounter.get_counts(self.nigeria, ["gender:m"]), {"gender:m": 6})

        self.assertIsNotNone(Contact.recalculate_reporters_stats(self.nigeria))
        self.assertEqual(ReportersCounter.get_counts(self.nigeria, ["gender:m"]), {"gender:m": 1})

        # the rebuilt counters are one per type, so they're created squashed
        self.assertFalse(ReportersCounter.objects.filter(org=self.nigeria, is_squashed=False).exists())
        self.assertIsNone(get_valkey_connection().get(ReportersCounter.COUNTS_SQUASH_LOCK))


class ContactsTasksTest(UreportTest):
    def setUp(self):
        super(ContactsTasksTest, self).setUp()

    @patch("ureport.contacts.models.ReportersCounter.squash_counts")
    def test_squash_reporters_counts(self, mock_squash_counts):
        squash_reporters_counts()

        mock_squash_counts.assert_called_once_with()

        entry = settings.CELERY_BEAT_SCHEDULE["reporters_counts_squash"]
        self.assertEqual(entry["task"], squash_reporters_counts.name)

    @patch("valkey.client.StrictValkey.get")
    @patch("django.core.cache.cache.set")
    @patch("ureport.contacts.models.ReportersCounter.get_counts")
    def test_check_contacts_count_mismatch(self, mock_counter_counts, mock_cache_set, mock_valkey_get):
        mock_valkey_get.return_value = None
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

        mock_valkey_get.side_effect = ["foo_locked_task_running", None]
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

    @patch("ureport.contacts.sync.sync_contacts.apply_async")
    def test_pull_contacts_enqueues_sync_jobs(self, mock_enqueue):
        # keep only on backend config
        self.nigeria.backends.exclude(slug="rapidpro").delete()

        results = pull_contacts(self.nigeria.pk)

        job = SyncJob.objects.get(org=self.nigeria, job_type="contact-pull", scope="rapidpro")
        mock_enqueue.assert_called_once_with((job.id,), queue="celery")
        self.assertEqual(results, {"enqueued": {"rapidpro": job.id}, "skipped": {}})

        # enqueuing isn't pulling, so it must not report a pull the org's task state
        self.assertFalse(TaskState.objects.filter(org=self.nigeria, task_key="contact-pull").exists())
