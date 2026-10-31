import csv
import os
import tempfile
from datetime import date, datetime, timezone as tzone
from io import StringIO
from unittest.mock import patch

from django_valkey import get_valkey_connection

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import override_settings

from dash.categories.models import Category
from dash.orgs.models import Org
from ureport.backend.floip import FLOIPBackend
from ureport.backend.rapidpro import RapidProBackend
from ureport.contacts.models import ReportersCounter
from ureport.locations.models import Boundary
from ureport.polls.models import PollResult
from ureport.stats import active_users
from ureport.stats.models import (
    ActiveUsersCheckpoint,
    ActiveUsersCheckpointRun,
    AgeSegment,
    ContactActivity,
    PollEngagementDailyCount,
    SchemeSegment,
)
from ureport.stats.tasks import checkpoint_active_users, compare_active_users
from ureport.stats.tests.test_engagement import frozen_now
from ureport.tests import UreportTest
from ureport.utils import ORG_CONTACT_COUNT_KEY, datetime_to_json_date

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=tzone.utc)
FAR_FUTURE = int(datetime(2100, 1, 1, tzinfo=tzone.utc).timestamp())


@override_settings(ACTIVE_USERS_HLL_WRITE=True)
class ActiveUsersTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.org = self.uganda
        self.r = get_valkey_connection()
        self.clear()

        # sketches expire by the real clock, which the months these tests use must not depend on
        expire_patch = patch("ureport.stats.active_users._expire_at", return_value=FAR_FUTURE)
        expire_patch.start()
        self.addCleanup(expire_patch.stop)

        SchemeSegment.objects.get_or_create(scheme="tel")
        Boundary.objects.create(org=self.org, osm_id="R1", name="Kampala", level=Boundary.STATE_LEVEL)
        Boundary.objects.create(org=self.org, osm_id="R2", name="Gulu", level=Boundary.STATE_LEVEL)
        ReportersCounter.objects.create(org=self.org, type="scheme:tel", count=10)
        ReportersCounter.objects.create(org=self.org, type="scheme:twitterid", count=5)
        cache.delete(ORG_CONTACT_COUNT_KEY % self.org.id)

        category = Category.objects.create(org=self.org, name="Health", created_by=self.admin, modified_by=self.admin)
        self.poll = self.create_poll(self.org, "Poll 1", "flow-1", category, self.admin)
        self.poll2 = self.create_poll(self.org, "Poll 2", "flow-2", category, self.admin)

    def tearDown(self):
        self.clear()
        super().tearDown()

    def clear(self):
        for org in (self.uganda, self.nigeria):
            active_users.clear(org)
        self.r.delete(active_users.DIRTY_KEY, active_users.CHECKPOINTING_KEY)
        for key in self.r.scan_iter(match=f"{active_users.KEY_PREFIX}:999999:*"):
            self.r.delete(key)

    def result(self, contact, when, flow="flow-1", ruleset="ruleset-1", category="Yes", org=None, **kwargs):
        fields = dict(born=None, gender=None, state=None, scheme=None)
        fields.update(kwargs)
        return PollResult(
            org=org or self.org,
            flow=flow,
            ruleset=ruleset,
            contact=contact,
            category=category,
            date=when,
            completed=True,
            **fields,
        )

    def pfcount(self, month, segment, org=None):
        return self.r.pfcount(active_users.sketch_key((org or self.org).id, month, segment))

    def dirty(self):
        return {k.decode() for k in self.r.smembers(active_users.DIRTY_KEY)}

    def seed(self):
        """
        Saves results for a couple of years of answers from contacts of varied segments, which the contact activity
        trigger turns into activities, and returns them
        """
        genders = ["M", "F", "O", None]
        states = ["R1", "r2", None]
        schemes = ["tel", "twitterid", "TEL", None]
        borns = [2011, 2008, 2004, 1999, 1994, 1980, None]

        results = []
        for i in range(60):
            contact = f"contact-{i}"
            attrs = dict(
                born=borns[i % len(borns)],
                gender=genders[i % len(genders)],
                state=states[i % len(states)],
                scheme=schemes[i % len(schemes)],
            )
            # each contact answers in a few months spread over the last two years
            for j in range(i % 4 + 1):
                month = active_users.add_months(date(2024, 10, 1), (i * 5 + j * 7) % 25)
                when = datetime(month.year, month.month, 1 + (i + j) % 27, 12, tzinfo=tzone.utc)
                results.append(self.result(contact, when, ruleset=f"ruleset-{j}", **attrs))

        PollResult.objects.bulk_create(results)
        return results

    def test_add_results_segments(self):
        when = datetime(2026, 3, 31, 23, 30, tzinfo=tzone.utc)  # still March in UTC though April in Kampala
        results = [
            self.result("c1", when, born=2000, gender="f", state="r1", scheme="TEL"),
            self.result("c1", when, ruleset="ruleset-2", born=2000, gender="f", state="r1", scheme="TEL"),
            self.result("c2", when, gender="M", state="", scheme=None),
            self.result("c3", when, category=None),  # no answer
            self.result("c4", None),  # no date
            self.result("c5", when, flow=""),
        ]

        with patch("ureport.stats.active_users.PIPELINE_SIZE", 4):
            self.assertEqual(6, active_users.add_results(results))

        march = date(2026, 3, 1)
        self.assertEqual(2, self.pfcount(march, "all"))
        self.assertEqual(1, self.pfcount(march, "born:2000"))
        self.assertEqual(1, self.pfcount(march, "gender:F"))
        self.assertEqual(1, self.pfcount(march, "gender:M"))
        self.assertEqual(1, self.pfcount(march, "state:R1"))
        self.assertEqual(1, self.pfcount(march, "scheme:tel"))
        self.assertEqual(0, self.pfcount(date(2026, 4, 1), "all"))

        self.assertEqual(
            {active_users.sketch_key(self.org.id, march, s) for s in ("all", "born:2000", "gender:F", "gender:M")}
            | {active_users.sketch_key(self.org.id, march, s) for s in ("state:R1", "scheme:tel")},
            self.dirty(),
        )

        self.assertEqual(FAR_FUTURE, self.r.expiretime(active_users.sketch_key(self.org.id, march, "all")))

        self.assertEqual(0, active_users.add_results([self.result("c3", when, category=None)]))

    def test_record_results(self):
        when = datetime(2026, 3, 10, tzinfo=tzone.utc)

        with override_settings(ACTIVE_USERS_HLL_WRITE=False):
            active_users.record_results([self.result("c1", when)])
        self.assertEqual(0, self.pfcount(date(2026, 3, 1), "all"))

        # a failing write is logged rather than failing the sync
        with patch("ureport.stats.active_users.add_results", side_effect=ConnectionError("down")):
            with self.assertLogs("ureport.stats.active_users", level="ERROR"):
                active_users.record_results([self.result("c1", when)])

        active_users.record_results([self.result("c1", when)])
        self.assertEqual(1, self.pfcount(date(2026, 3, 1), "all"))

    def test_sync_records_new_and_updated_results(self):
        backend = RapidProBackend(self.rapidpro_backend)
        march, april = date(2026, 3, 1), date(2026, 4, 1)

        backend._save_new_poll_results_to_database(
            {"c1": {"ruleset-1": self.result("c1", datetime(2026, 3, 2, tzinfo=tzone.utc), gender="F")}}
        )
        self.assertEqual(1, self.pfcount(march, "gender:F"))

        existing = PollResult.objects.get(org=self.org, contact="c1")

        run = type("Run", (), {})()
        run.flow = type("Flow", (), {"uuid": "flow-1"})()
        run.contact = type("Contact", (), {"uuid": "c1"})()
        run.exit_type = "completed"
        run.created_on = datetime(2026, 4, 2, tzinfo=tzone.utc)
        run.path = []
        value = type("Value", (), {})()
        value.node = "ruleset-1"
        value.category = "No"
        value.value = "no"
        value.time = datetime(2026, 4, 3, tzinfo=tzone.utc)
        run.values = {"q1": value}
        contact = type("Contact", (), dict(state="R1", district="", ward="", born=1990, gender="M", scheme="tel"))()

        backend._process_run_poll_results(
            self.org, ["ruleset-1"], run, contact, {"c1": {"ruleset-1": existing}}, {}, {"num_val_updated": 0}
        )

        self.assertEqual(1, self.pfcount(april, "all"))
        self.assertEqual(1, self.pfcount(april, "gender:M"))
        self.assertEqual(1, self.pfcount(april, "state:R1"))
        self.assertEqual(1, self.pfcount(april, "born:1990"))

    def test_floip_sync_records_new_and_updated_results(self):
        backend = FLOIPBackend(self.floip_backend)
        march, april = date(2026, 3, 1), date(2026, 4, 1)

        backend._save_new_poll_results_to_database(
            {"c1": {"ruleset-1": self.result("c1", datetime(2026, 3, 2, tzinfo=tzone.utc), org=self.nigeria)}}
        )
        self.assertEqual(1, self.pfcount(march, "all", org=self.nigeria))

        existing = PollResult.objects.get(org=self.nigeria, contact="c1")
        result = [datetime_to_json_date(datetime(2026, 4, 3, tzinfo=tzone.utc)), "row-1", "c1", "s1", "ruleset-1", "No"]
        contact = type("Contact", (), dict(state="R1", district="", ward="", born=1990, gender="M"))()

        stats = {"num_val_updated": 0}
        backend._process_run_poll_results(
            self.nigeria, "flow-1", ["ruleset-1"], result, contact, {"c1": {"ruleset-1": existing}}, {}, stats
        )

        self.assertEqual(1, stats["num_val_updated"])
        self.assertEqual(1, self.pfcount(april, "all", org=self.nigeria))
        self.assertEqual(1, self.pfcount(april, "gender:M", org=self.nigeria))
        self.assertEqual(1, self.pfcount(april, "born:1990", org=self.nigeria))

    def test_window_union(self):
        jan = date(2026, 1, 1)
        active_users.add_results(
            [
                self.result("c1", datetime(2026, 1, 5, tzinfo=tzone.utc)),
                self.result("c1", datetime(2026, 6, 5, tzinfo=tzone.utc)),  # counted once across the window
                self.result("c2", datetime(2026, 6, 5, tzinfo=tzone.utc)),
                self.result("c3", datetime(2026, 6, 5, tzinfo=tzone.utc), org=self.nigeria),
            ]
        )

        self.assertEqual(0, active_users.count(self.org, date(2025, 12, 1), ["all"]))
        self.assertEqual(1, active_users.count(self.org, jan, ["all"]))
        self.assertEqual(1, active_users.count(self.org, date(2026, 5, 1), ["all"]))
        self.assertEqual(2, active_users.count(self.org, date(2026, 6, 1), ["all"]))
        self.assertEqual(2, active_users.count(self.org, date(2026, 12, 1), ["all"]))  # last month c1's Jan counts
        self.assertEqual(2, active_users.count(self.org, date(2027, 1, 1), ["all"]))
        self.assertEqual(2, active_users.count(self.org, date(2027, 5, 1), ["all"]))
        self.assertEqual(0, active_users.count(self.org, date(2027, 6, 1), ["all"]))
        self.assertEqual(1, active_users.count(self.nigeria, date(2026, 6, 1), ["all"]))

    def test_age_bands_taken_in_month(self):
        # born 2011 answering in December 2025 is 14 then, but 15 in the months of 2026 its activity covers
        active_users.add_results([self.result("c1", datetime(2025, 12, 5, tzinfo=tzone.utc), born=2011)])

        self.assertEqual(
            1, active_users.count(self.org, date(2025, 12, 1), active_users._born_segments(date(2025, 12, 1), 0, 14))
        )
        self.assertEqual(
            0, active_users.count(self.org, date(2026, 1, 1), active_users._born_segments(date(2026, 1, 1), 0, 14))
        )
        self.assertEqual(
            1, active_users.count(self.org, date(2026, 1, 1), active_users._born_segments(date(2026, 1, 1), 15, 19))
        )

        self.assertEqual([], active_users._born_segments(date(2026, 1, 1), 2000, 2000))

        # a band with no born years to read counts nothing
        AgeSegment.objects.create(min_age=200, max_age=300)
        series = active_users.get_series_counts(self.org, "age", [date(2025, 12, 1)])
        self.assertEqual((None, {}, {date(2025, 12, 1): 0}), series[-1])
        self.assertEqual({date(2025, 12, 1): 1}, series[0][2])
        self.assertEqual("born:1900", active_users._born_segments(date(2026, 1, 1), 35, 2000)[0])

        # born years before the ones kept count together, in the band that reaches back past them, while no born year
        # and those the counters leave out as over the oldest band count in none
        active_users.add_results(
            [
                self.result("c2", datetime(2025, 12, 6, tzinfo=tzone.utc), born=1066),
                self.result("c3", datetime(2025, 12, 6, tzinfo=tzone.utc), born=1850),
                self.result("c4", datetime(2025, 12, 6, tzinfo=tzone.utc), born=0),
                self.result("c5", datetime(2025, 12, 6, tzinfo=tzone.utc), born=20),
                self.result("c6", datetime(2025, 12, 6, tzinfo=tzone.utc), born=-1),
            ]
        )
        self.assertEqual(2, self.pfcount(date(2025, 12, 1), active_users.OLD_BORN_SEGMENT))
        self.assertEqual(6, self.pfcount(date(2025, 12, 1), "all"))
        series = {s[0]: s[2] for s in active_users.get_series_counts(self.org, "age", [date(2025, 12, 1)])}
        self.assertEqual({date(2025, 12, 1): 2}, series["35+"])
        self.assertEqual({date(2025, 12, 1): 0}, series[None])
        self.assertNotIn(active_users.OLD_BORN_SEGMENT, active_users._born_segments(date(2026, 1, 1), 31, 34))

    def test_reader_matches_contact_activity(self):
        results = self.seed()
        active_users.add_results(results)

        with frozen_now(NOW):
            for segment in active_users.COMPARE_SEGMENTS:
                existing = active_users._existing_activity(self.org, segment, [3, 6, 12])
                hll = active_users.get_activity(self.org, segment, [3, 6, 12])
                self.assertEqual(existing, hll, segment)
                self.assertTrue(any(v for s in hll[12] for v in s["data"].values()), segment)

            with self.settings(ACTIVE_USERS_HLL_READ=False):
                self.assertEqual([], active_users.get_activity(self.org, "unknown", [12])[12])

    def test_reader_switch(self):
        active_users.add_results(self.seed())

        with frozen_now(NOW), patch.object(active_users, "get_activity", wraps=active_users.get_activity) as mock:
            PollEngagementDailyCount.refresh_engagement_data(self.org, "active-users", "gender")
            self.assertEqual(0, mock.call_count)

            self.org.set_config("common.active_users_hll", True)
            PollEngagementDailyCount.refresh_engagement_data(self.org, "active-users", "gender")
            self.assertEqual(1, mock.call_count)

            self.org.set_config("common.active_users_hll", False)
            with self.settings(ACTIVE_USERS_HLL_READ=True):
                result = PollEngagementDailyCount.refresh_engagement_data(self.org, "active-users", "all", [12])
            self.assertEqual(2, mock.call_count)
            self.assertEqual(ContactActivity.get_activity(self.org, [12]), result)

            # other metrics are unaffected
            with self.settings(ACTIVE_USERS_HLL_READ=True):
                PollEngagementDailyCount.refresh_engagement_data(self.org, "response-rate", "all")
            self.assertEqual(2, mock.call_count)

    def test_checkpoint_and_restore(self):
        results = self.seed()
        active_users.add_results(results)
        # a sketch of an org that has gone, which is dropped
        self.r.pfadd(active_users.sketch_key(999999, date(2026, 1, 1), "all"), "x")
        self.r.sadd(active_users.DIRTY_KEY, active_users.sketch_key(999999, date(2026, 1, 1), "all"))
        # and one that expired after being touched
        self.r.sadd(active_users.DIRTY_KEY, active_users.sketch_key(self.org.id, date(2026, 1, 1), "gone"))

        with frozen_now(NOW):
            before = {s: active_users.get_activity(self.org, s, [12]) for s in active_users.COMPARE_SEGMENTS}

        keys = self.dirty() - {
            active_users.sketch_key(999999, date(2026, 1, 1), "all"),
            active_users.sketch_key(self.org.id, date(2026, 1, 1), "gone"),
        }

        with frozen_now(NOW):
            saved = active_users.checkpoint(batch_size=7)

        self.assertEqual(len(keys), saved)
        self.assertEqual(set(), self.dirty())
        self.assertFalse(self.r.exists(active_users.CHECKPOINTING_KEY))
        self.assertEqual(keys, set(ActiveUsersCheckpoint.objects.filter(org=self.org).values_list("key", flat=True)))

        cp = ActiveUsersCheckpoint.objects.get(key=active_users.sketch_key(self.org.id, date(2026, 1, 1), "all"))
        self.assertEqual(self.r.get(cp.key), bytes(cp.value))
        self.assertEqual(NOW, cp.taken_on)

        run = ActiveUsersCheckpointRun.objects.get()
        self.assertEqual(
            (NOW, PollResult.objects.order_by("-id").first().id, saved), (run.taken_on, run.watermark, run.saved)
        )

        # nothing touched since, so nothing to save
        with frozen_now(NOW):
            self.assertEqual(0, active_users.checkpoint())

        # results saved since the checkpoint, one of them a contact already counted
        later = [
            self.result("late-1", datetime(2026, 9, 1, tzinfo=tzone.utc), gender="F"),
            self.result("late-1", datetime(2026, 9, 2, tzinfo=tzone.utc), ruleset="ruleset-9", gender="F"),
        ]
        PollResult.objects.bulk_create(later)

        # the sketches are lost
        self.assertGreater(active_users.clear(self.org), 0)

        with frozen_now(NOW):
            restored, replayed = active_users.restore(self.org)
            self.assertEqual(len(keys), restored)
            # the results saved since, and those of polls still syncing answered since the day before
            self.assertEqual(
                2 + len([r for r in results if r.date >= datetime(2026, 10, 14, 12, tzinfo=tzone.utc)]), replayed
            )

            sept = date(2026, 9, 1)
            self.assertEqual(1, self.pfcount(sept, "gender:F"))

            # every count is what it was plus the new contact
            after = active_users.get_activity(self.org, "all", [12])[12][0]["data"]
            for month, count in before["all"][12][0]["data"].items():
                self.assertEqual(count + (1 if month >= "2026-09-01" else 0), after[month], month)

            # restoring again and replaying the same results over the top changes nothing
            active_users.restore(self.org)
            active_users.add_results(results + later)
            self.assertEqual(after, active_users.get_activity(self.org, "all", [12])[12][0]["data"])
            for segment in ("age", "location", "scheme"):
                self.assertEqual(before[segment], active_users.get_activity(self.org, segment, [12]), segment)

    def test_restore_replays_changed_answers(self):
        with frozen_now(NOW):
            PollResult.objects.bulk_create([self.result("c1", datetime(2026, 8, 1, tzinfo=tzone.utc))])
            active_users.backfill(self.org)
            active_users.checkpoint()
            active_users.checkpoint()

            # an answer changed in place since, on a poll still syncing
            PollResult.objects.filter(org=self.org, contact="c1").update(
                date=datetime(2026, 10, 14, 18, tzinfo=tzone.utc), gender="F"
            )
            active_users.clear(self.org)

            self.assertEqual((1, 1), active_users.restore(self.org))
            self.assertEqual(1, self.pfcount(date(2026, 8, 1), "all"))
            self.assertEqual(1, self.pfcount(date(2026, 10, 1), "gender:F"))

            # nothing to restore from replays everything
            ActiveUsersCheckpoint.objects.all().delete()
            active_users.clear(self.org)
            self.assertEqual((0, 1), active_users.restore(self.org))
            self.assertEqual(1, self.pfcount(date(2026, 10, 1), "all"))

    def test_interrupted_checkpoint_resumed(self):
        jan, feb = (active_users.sketch_key(self.org.id, date(2026, m, 1), "all") for m in (1, 2))
        active_users.add_results([self.result("c1", datetime(2026, 1, 5, tzinfo=tzone.utc))])
        self.r.rename(active_users.DIRTY_KEY, active_users.CHECKPOINTING_KEY)
        active_users.add_results([self.result("c2", datetime(2026, 2, 5, tzinfo=tzone.utc))])

        # a run that fails part way isn't recorded, and leaves its sketches to be saved
        with patch("ureport.stats.models.ActiveUsersCheckpoint.objects.bulk_create", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                active_users.checkpoint()
        self.assertFalse(ActiveUsersCheckpointRun.objects.exists())
        self.assertEqual({jan}, {k.decode() for k in self.r.smembers(active_users.CHECKPOINTING_KEY)})

        # the next saves the interrupted run's sketches, then the ones touched since
        self.assertEqual(2, active_users.checkpoint())
        self.assertEqual({jan, feb}, set(ActiveUsersCheckpoint.objects.values_list("key", flat=True)))
        self.assertEqual(set(), self.dirty())
        self.assertFalse(self.r.exists(active_users.CHECKPOINTING_KEY))
        self.assertEqual(1, ActiveUsersCheckpointRun.objects.count())

    def test_restore_replays_since_previous_run(self):
        with frozen_now(datetime(2026, 8, 1, tzinfo=tzone.utc)):
            # an old month's sketch, checkpointed long before and not touched since
            PollResult.objects.bulk_create([self.result("old", datetime(2025, 3, 5, tzinfo=tzone.utc))])
            active_users.backfill(self.org)
            active_users.checkpoint()

        with frozen_now(datetime(2026, 9, 1, tzinfo=tzone.utc)):
            PollResult.objects.bulk_create([self.result("sept", datetime(2026, 8, 31, tzinfo=tzone.utc))])
            active_users.backfill(self.org)
            active_users.checkpoint()

        with frozen_now(NOW):
            # saved after the previous run started, so replayed, however its sketches were checkpointed
            PollResult.objects.bulk_create([self.result("late", datetime(2026, 10, 1, tzinfo=tzone.utc))])
            active_users.add_results(list(PollResult.objects.filter(contact="late")))
            active_users.checkpoint()

            # only the last two runs are kept
            self.assertEqual(2, ActiveUsersCheckpointRun.objects.count())

            active_users.clear(self.org)
            self.assertEqual((3, 1), active_users.restore(self.org))
            for contact, month in (("old", date(2025, 3, 1)), ("sept", date(2026, 8, 1)), ("late", date(2026, 10, 1))):
                self.assertEqual([month], self.months_of(contact, self.org), contact)

    def test_prune_checkpoints(self):
        active_users.add_results(
            [
                self.result("c1", datetime(2024, 1, 5, tzinfo=tzone.utc)),
                self.result("c1", datetime(2026, 1, 5, tzinfo=tzone.utc)),
            ]
        )
        with frozen_now(datetime(2025, 1, 1, tzinfo=tzone.utc)):
            self.assertEqual(2, active_users.checkpoint())

        with frozen_now(NOW):
            active_users.prune_checkpoints()

        self.assertEqual(
            [date(2026, 1, 1)], list(ActiveUsersCheckpoint.objects.filter(org=self.org).values_list("month", flat=True))
        )

    def test_backfill(self):
        results = self.seed()
        PollResult.objects.bulk_create(
            [self.result("other-org", datetime(2026, 1, 5, tzinfo=tzone.utc), flow="flow-1", org=self.nigeria)]
        )

        with frozen_now(NOW):
            answers, added = active_users.backfill(
                self.org, since=date(2026, 1, 1), until=date(2026, 3, 1), batch_size=3
            )
            self.assertGreater(answers, 0)
            self.assertEqual(len([r for r in results if date(2026, 1, 1) <= r.date.date() < date(2026, 4, 1)]), added)
            self.assertEqual(0, self.pfcount(date(2025, 12, 1), "all"))
            self.assertGreater(self.pfcount(date(2026, 3, 1), "all"), 0)
            self.assertEqual(0, self.pfcount(date(2026, 4, 1), "all"))
            self.assertEqual(0, self.pfcount(date(2026, 1, 1), "all", org=self.nigeria))

            # the rest, overlapping what's there
            self.assertEqual(len(results), active_users.backfill(self.org)[1])
            for segment in active_users.COMPARE_SEGMENTS:
                self.assertEqual(
                    active_users._existing_activity(self.org, segment, [12]),
                    active_users.get_activity(self.org, segment, [12]),
                )

    def activities(self, contact, first, last, org=None, **kwargs):
        """
        Contact activity rows for every month from first to last, as the trigger would have written them
        """
        fields = dict(born=None, gender=None, state=None, district=None, ward=None, scheme=None)
        fields.update(kwargs)
        rows, month = [], first
        while month <= last:
            rows.append(ContactActivity(org=org or self.org, contact=contact, date=month, used=True, **fields))
            month = active_users.add_months(month, 1)
        return rows

    def months_of(self, contact, org):
        """
        The months a contact is in org's sketches for, i.e. those whose count doesn't change with it added
        """
        probe = active_users.sketch_key(999999, date(2000, 1, 1), "probe")
        self.r.pfadd(probe, contact)

        found, month = [], date(2023, 1, 1)
        while month <= date(2027, 12, 1):
            key = active_users.sketch_key(org.id, month, "all")
            if self.r.exists(key) and self.r.pfcount(key) == self.r.pfcount(key, probe):
                found.append(month)
            month = active_users.add_months(month, 1)

        self.r.delete(probe)
        return found

    def test_backfill_reconstructs_activity_answers(self):
        org = self.nigeria
        ContactActivity.objects.bulk_create(
            # a long run, which answered at its start, a year later, and 12 months before its end
            self.activities("0aaa", date(2024, 10, 1), date(2026, 12, 1), org=org)
            # two runs with a gap between
            + self.activities("Fbbb", date(2025, 1, 1), date(2025, 12, 1), org=org)
            + self.activities("Fbbb", date(2026, 3, 1), date(2027, 2, 1), org=org)
            # a run the prune has cut into at the start, which answered before its first row
            + self.activities("zccc", date(2025, 10, 1), date(2026, 3, 1), org=org, gender="F")
            # answered before the sketches are kept
            + self.activities("9ddd", date(2024, 1, 1), date(2024, 12, 1), org=org)
        )

        with frozen_now(NOW):
            progress = []
            answers, _ = active_users.backfill(org, prefix_length=1, progress=lambda *a: progress.append(a))
            self.assertEqual(6, answers)

        progress = [p for p in progress if p[0] == "activities"]
        self.assertEqual(16, len(progress))
        self.assertEqual(("activities", "contacts [, 1)", 3), progress[0])  # the long run
        self.assertEqual("contacts [f, )", progress[-1][1])
        # wherever the collation puts uppercase and non hex uuids, the ranges between them cover every one
        self.assertEqual(6, sum(n for *_, n in progress))

        self.assertEqual([date(2024, 10, 1), date(2025, 10, 1), date(2026, 1, 1)], self.months_of("0aaa", org))
        self.assertEqual([date(2025, 1, 1), date(2026, 3, 1)], self.months_of("Fbbb", org))
        self.assertEqual([date(2025, 4, 1)], self.months_of("zccc", org))
        self.assertEqual([], self.months_of("9ddd", org))
        self.assertEqual(1, self.pfcount(date(2025, 4, 1), "gender:F", org=org))

        # the sketches it touched are left to be checkpointed
        self.assertIn(active_users.sketch_key(org.id, date(2025, 4, 1), "gender:F"), self.dirty())

    def test_backfill_matches_contact_activity(self):
        genders = ["M", "F", "O", None]
        states = ["R1", "r2", None]
        schemes = ["tel", "twitterid", "TEL", None]
        borns = [2011, 2008, 2004, 1999, 1994, 1980, None]

        rows = []
        for i in range(60):
            attrs = dict(
                born=borns[i % len(borns)],
                gender=genders[i % len(genders)],
                state=states[i % len(states)],
                scheme=schemes[i % len(schemes)],
            )
            contact = f"{i:02x}-contact"
            first = active_users.add_months(date(2024, 10, 1), i % 9)
            if i % 3 == 0:  # one long run
                rows += self.activities(contact, first, active_users.add_months(first, 14 + i % 13), **attrs)
            elif i % 3 == 1:  # runs with gaps between
                rows += self.activities(contact, first, active_users.add_months(first, 11), **attrs)
                second = active_users.add_months(first, 13 + i % 5)
                rows += self.activities(contact, second, active_users.add_months(second, 11 + i % 7), **attrs)
            else:  # cut short at the start by the prune
                start = date(2025, 10, 1)
                rows += self.activities(contact, start, active_users.add_months(start, i % 11), **attrs)
        ContactActivity.objects.bulk_create(rows)

        with frozen_now(NOW):
            answers, _ = active_users.backfill(self.org)
            for segment in active_users.COMPARE_SEGMENTS:
                existing = active_users._existing_activity(self.org, segment, [12])
                self.assertEqual(existing, active_users.get_activity(self.org, segment, [12]), segment)
                self.assertTrue(any(v for s in existing[12] for v in s["data"].values()), segment)

            # backfilling again changes nothing
            self.assertEqual((answers, 0), active_users.backfill(self.org, prefix_length=0))
            for segment in active_users.COMPARE_SEGMENTS:
                self.assertEqual(
                    active_users._existing_activity(self.org, segment, [12]),
                    active_users.get_activity(self.org, segment, [12]),
                    segment,
                )

    def test_compare(self):
        results = self.seed()
        active_users.add_results(results)

        with frozen_now(NOW):
            rows = active_users.compare_org(self.org)

        self.assertEqual(
            {"org", "month", "segment", "series", "existing", "hll", "error", "rel_error"}, set(rows[0].keys())
        )
        self.assertEqual(set(active_users.COMPARE_SEGMENTS), {r["segment"] for r in rows})
        self.assertTrue(all(r["error"] == 0 for r in rows))

        # series are matched by name, whatever order each side lists them in
        with frozen_now(NOW), patch("ureport.stats.active_users.get_activity", side_effect=lambda *a: {12: []}):
            missing = active_users.compare_org(self.org, segments=["gender"])
        self.assertEqual({0}, {r["hll"] for r in missing})
        self.assertTrue(any(r["existing"] for r in missing))

        reversed_get_activity = active_users.get_activity

        def reverse(org, segment, tfs):
            output = reversed_get_activity(org, segment, tfs)
            return {tf: list(reversed(series)) for tf, series in output.items()}

        with frozen_now(NOW), patch("ureport.stats.active_users.get_activity", side_effect=reverse):
            self.assertTrue(all(r["error"] == 0 for r in active_users.compare_org(self.org)))

        # make one series undercount, and another count where there's nothing
        rows[0].update(existing=1000, hll=950, error=-50, rel_error=-0.05)
        rows[1].update(existing=0, hll=3, error=3, rel_error=None)
        rows[2].update(existing=200, hll=201, error=1, rel_error=0.005)

        summary = active_users.summarize(rows, min_count=100)
        self.assertEqual(len(rows), summary["rows"])
        self.assertEqual(2, summary["measured"])
        self.assertAlmostEqual(0.05, summary["max_abs_rel_error"])
        self.assertAlmostEqual(0.0275, summary["mean_abs_rel_error"])
        self.assertAlmostEqual(0.5, summary["within_2se"])

        self.assertEqual([rows[0], rows[2], rows[1]], active_users.worst(rows, limit=3))

        empty = active_users.summarize([])
        self.assertIsNone(empty["mean_abs_rel_error"])
        self.assertIsNone(empty["p95_abs_rel_error"])

    def test_command(self):
        results = self.seed()

        def run(*args):
            out = StringIO()
            with frozen_now(NOW):
                call_command("active_users", *args, stdout=out)
            return out.getvalue()

        out = run("backfill", "--org", str(self.org.id), "--since", "2024-10", "--until", "2026-10", "--clear")
        self.assertIn(f"sketches of org #{self.org.id}", out)
        self.assertIn("flow flow-1", out)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rows.csv")
            out = run("compare", "--org", str(self.org.id), "--worst", "3", "--min-count", "1", "--csv", path)
            with open(path) as f:
                rows = list(csv.DictReader(f))

        self.assertIn(f"org #{self.org.id} (uganda):", out)
        self.assertIn("all orgs:", out)
        self.assertIn("Worst 3:", out)
        self.assertIn("within 2SE 100.00%", out)
        self.assertGreater(len(rows), 10)

        out = run("compare", "--org", str(self.org.id), "--segment", "gender")
        self.assertIn("mean", out)

        ContactActivity.objects.create(org=self.nigeria, contact="abc", date=date(2026, 1, 1), used=True)
        out = run("backfill", "--org", str(self.nigeria.id), "--prefix-length", "1")
        self.assertIn(f"org #{self.nigeria.id} contacts [a, b): 1 activities", out)
        self.assertIn(f"org #{self.nigeria.id} (nigeria): 1 answer months from activity tables, 0 results", out)

        self.assertIn("Checkpointed", run("checkpoint"))
        self.assertIn(f"sketches of org #{self.org.id} and replayed", run("restore", "--org", str(self.org.id)))

        # all active orgs by default
        self.assertIn(f"org #{self.nigeria.id}", run("compare", "--segment", "all"))

        with self.assertRaises(Exception):
            run("backfill", "--since", "nope")

        self.assertTrue(len(results))

    def test_backfill_skip_results(self):
        self.seed()

        out = StringIO()
        with frozen_now(NOW), patch("ureport.stats.active_users._backfill_results") as backfill_results:
            call_command("active_users", "backfill", "--org", str(self.org.id), "--skip-results", stdout=out)
            backfill_results.assert_not_called()

            for segment in active_users.COMPARE_SEGMENTS:
                self.assertEqual(
                    active_users._existing_activity(self.org, segment, [12]),
                    active_users.get_activity(self.org, segment, [12]),
                    segment,
                )

        self.assertRegex(
            out.getvalue(), rf"org #{self.org.id} \(uganda\): \d+ answer months from activity tables, 0 results"
        )

    def test_backfill_without_activity_tables(self):
        results = self.seed()
        with frozen_now(NOW):
            expected = {s: active_users._existing_activity(self.org, s, [12]) for s in active_users.COMPARE_SEGMENTS}

        # a later release drops the tables
        self.assertTrue(active_users.activity_table_exists())
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("DROP TABLE stats_contactactivity CASCADE")
        self.assertFalse(active_users.activity_table_exists())

        # just the results
        with frozen_now(NOW):
            self.assertEqual((None, len(results)), active_users.backfill(self.org))
            self.assertTrue(self.dirty())
            for segment in active_users.COMPARE_SEGMENTS:
                self.assertEqual(expected[segment], active_users.get_activity(self.org, segment, [12]), segment)

            out = StringIO()
            call_command("active_users", "backfill", stdout=out)

        out = out.getvalue()
        self.assertEqual(1, out.count("No contact activity tables, backfilling from results only"))
        self.assertIn(f"org #{self.org.id} (uganda): {len(results)} results", out)
        self.assertIn(f"org #{self.nigeria.id} (nigeria): 0 results", out)

        with self.assertRaisesMessage(CommandError, "the results can't be skipped"):
            call_command("active_users", "backfill", "--skip-results", stdout=StringIO())

        # clearing what the results alone can't fill back needs forcing
        with self.assertRaisesMessage(CommandError, "use --force to clear"):
            call_command("active_users", "backfill", "--clear", stdout=StringIO())

        out = StringIO()
        with frozen_now(NOW):
            call_command("active_users", "backfill", "--org", str(self.org.id), "--clear", "--force", stdout=out)
        self.assertIn(f"sketches of org #{self.org.id}", out.getvalue())

    def test_backfill_command_needs_writes(self):
        with override_settings(ACTIVE_USERS_HLL_WRITE=False):
            with self.assertRaisesMessage(CommandError, "ACTIVE_USERS_HLL_WRITE is off"):
                call_command("active_users", "backfill", stdout=StringIO())

    def test_backfill_command_orgs(self):
        def run(*args):
            out, err = StringIO(), StringIO()
            with frozen_now(NOW):
                call_command("active_users", "backfill", *args, stdout=out, stderr=err)
            return out.getvalue(), err.getvalue()

        uganda, nigeria = self.org, self.nigeria
        self.assertLess(uganda.id, nigeria.id)
        active = Org.objects.filter(is_active=True).order_by("id")

        # capped, saying where to pick up
        out, _ = run("--limit", "1")
        self.assertIn(f"org #{active[0].id} ", out)
        self.assertNotIn(f"org #{active[1].id} ", out)
        self.assertIn(f"Stopped after 1 orgs, {active.count() - 1} left - resume with --from-org {active[1].id}", out)

        # resumed
        out, _ = run("--from-org", str(nigeria.id), "--org", str(uganda.id), "--org", str(nigeria.id))
        self.assertNotIn(f"org #{uganda.id} ", out)
        self.assertIn(f"org #{nigeria.id} (nigeria): ", out)
        self.assertNotIn("Stopped", out)

        # an org that fails doesn't stop the others, and is listed to be run again
        backfill = active_users.backfill

        def failing(org, **kwargs):
            if org == uganda:
                raise ValueError("boom")
            return backfill(org, **kwargs)

        logs = self.assertLogs("ureport.stats.management.commands.active_users", level="ERROR")
        with patch("ureport.stats.active_users.backfill", side_effect=failing), logs:
            with self.assertRaisesMessage(CommandError, f"1 orgs failed, run them again with: --org {uganda.id}"):
                out, err = StringIO(), StringIO()
                with frozen_now(NOW):
                    call_command(
                        "active_users",
                        "backfill",
                        "--org",
                        str(uganda.id),
                        "--org",
                        str(nigeria.id),
                        stdout=out,
                        stderr=err,
                    )

        self.assertIn(f"org #{uganda.id} (uganda) failed: boom", err.getvalue())
        self.assertIn(f"org #{nigeria.id} (nigeria): ", out.getvalue())

    def test_tasks(self):
        active_users.add_results([self.result("c1", datetime(2026, 1, 5, tzinfo=tzone.utc))])

        checkpoint_active_users()
        self.assertEqual(1, ActiveUsersCheckpoint.objects.count())

        self.r.set("checkpoint_active_users_lock", "1", ex=60)
        try:
            active_users.add_results([self.result("c2", datetime(2026, 2, 5, tzinfo=tzone.utc))])
            checkpoint_active_users()
            self.assertEqual(1, ActiveUsersCheckpoint.objects.count())
        finally:
            self.r.delete("checkpoint_active_users_lock")

        with patch("ureport.stats.active_users.compare_org") as mock_compare:
            compare_active_users()
            mock_compare.assert_not_called()

            mock_compare.return_value = []
            with self.settings(ACTIVE_USERS_HLL_COMPARE=True):
                with self.assertLogs("ureport.stats.tasks", level="INFO"):
                    compare_active_users()
            self.assertTrue(mock_compare.called)

            mock_compare.side_effect = ValueError("boom")
            with self.settings(ACTIVE_USERS_HLL_COMPARE=True):
                with self.assertLogs("ureport.stats.tasks", level="ERROR"):
                    compare_active_users()

    def test_expire_at(self):
        patch.stopall()

        # kept until the charts no longer reach it
        self.assertEqual(datetime(2028, 4, 1, tzinfo=tzone.utc).timestamp(), active_users._expire_at(date(2026, 3, 1)))

    def test_parse_key(self):
        self.assertEqual(
            (12, date(2026, 3, 1), "born:1990"),
            active_users.parse_key(active_users.sketch_key(12, date(2026, 3, 1), "born:1990")),
        )
        self.assertEqual(date(2027, 2, 1), active_users.add_months(date(2026, 11, 1), 3))
        self.assertEqual(date(2025, 11, 1), active_users.add_months(date(2026, 1, 1), -2))
        self.assertEqual(13, len(active_users.chart_months(NOW)))
