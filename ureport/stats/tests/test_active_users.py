from datetime import date, datetime, timedelta, timezone as tzone
from io import StringIO
from unittest.mock import patch

from django_valkey import get_valkey_connection

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.utils import translation

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
    PollEngagementDailyCount,
    SchemeSegment,
)
from ureport.stats.tasks import checkpoint_active_users
from ureport.stats.tests.test_engagement import frozen_now
from ureport.tests import UreportTest
from ureport.utils import ORG_CONTACT_COUNT_KEY, datetime_to_json_date

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=tzone.utc)

SEGMENTS = ("all", "age", "gender", "location", "scheme")


class ActiveUsersTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.org = self.uganda
        self.r = get_valkey_connection()
        self.clear()

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
        Saves results for a couple of years of answers from contacts of varied segments, and returns them
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

    def expected_activity(self, results, segment_slug, time_filters):
        """
        The chart data of a segment as get_activity gives it, but with each count taken exactly from the results
        """
        translation.activate(self.org.language)

        months = active_users.chart_months()
        output = {tf: [] for tf in time_filters}
        for name, extra, segments_of in active_users._segment_series(self.org, segment_slug):
            counts = {}
            for month in months:
                window = {active_users.add_months(month, -i) for i in range(active_users.WINDOW_MONTHS)}
                segments = set(segments_of(month))
                counts[month] = len(
                    {
                        r.contact
                        for r in results
                        if active_users.is_countable(r)
                        and r.org_id == self.org.id
                        and active_users.result_month(r.date) in window
                        and segments & set(active_users.result_segments(r.born, r.gender, r.state, r.scheme))
                    }
                )
            for tf in time_filters:
                output[tf].append(dict(name=name, **extra, data=active_users._time_filter_data(counts, tf)))
        return output

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

        # the policy Valkey evicts by only takes keys with an expiry
        self.assertEqual(-1, self.r.ttl(active_users.sketch_key(self.org.id, march, "all")))

        self.assertEqual(0, active_users.add_results([self.result("c3", when, category=None)]))

    def test_record_results(self):
        when = datetime(2026, 3, 10, tzinfo=tzone.utc)

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
        # and those over the oldest band count in none
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

    def test_get_activity(self):
        results = self.seed()
        active_users.add_results(results)

        with frozen_now(NOW):
            for segment in SEGMENTS:
                hll = active_users.get_activity(self.org, segment, [3, 6, 12])
                self.assertEqual(self.expected_activity(results, segment, [3, 6, 12]), hll, segment)
                self.assertTrue(any(v for s in hll[12] for v in s["data"].values()), segment)

            self.assertEqual([], active_users.get_activity(self.org, "unknown", [12])[12])

    def test_time_filter_data(self):
        counts = {active_users.add_months(date(2025, 10, 1), i): i + 1 for i in range(13)}

        with frozen_now(NOW):
            data = active_users._time_filter_data(counts, 12)
            self.assertEqual({str(m): c for m, c in counts.items()}, data)

            # each bucket shows the count of its month, but for the buckets of a month whose start is out of range
            self.assertEqual(
                {
                    "2026-07-11": 0,
                    "2026-07-21": 0,
                    "2026-08-01": 11,
                    "2026-08-11": 11,
                    "2026-08-21": 11,
                    "2026-09-01": 12,
                    "2026-09-11": 12,
                    "2026-09-21": 12,
                    "2026-10-01": 13,
                    "2026-10-11": 13,
                },
                active_users._time_filter_data(counts, 3),
            )

            expected = {f"2026-{m:02d}-{d}": m + 3 for m in range(4, 11) for d in ("01", "16")}
            del expected["2026-10-16"]
            self.assertEqual(expected, active_users._time_filter_data(counts, 6))

    def test_engagement_reads_sketches(self):
        results = self.seed()
        active_users.add_results(results)

        with frozen_now(NOW), patch.object(active_users, "get_activity", wraps=active_users.get_activity) as mock:
            data = PollEngagementDailyCount.refresh_engagement_data(self.org, "active-users", "gender", [12])
            self.assertEqual(1, mock.call_count)
            self.assertEqual(self.expected_activity(results, "gender", [12]), data)

            # other metrics don't read them
            PollEngagementDailyCount.refresh_engagement_data(self.org, "response-rate", "all")
            self.assertEqual(1, mock.call_count)

    def test_checkpoint_and_restore(self):
        results = self.seed()
        active_users.add_results(results)
        # a sketch of an org that has gone, which is dropped
        self.r.pfadd(active_users.sketch_key(999999, date(2026, 1, 1), "all"), "x")
        self.r.sadd(active_users.DIRTY_KEY, active_users.sketch_key(999999, date(2026, 1, 1), "all"))
        # and one that was deleted after being touched
        self.r.sadd(active_users.DIRTY_KEY, active_users.sketch_key(self.org.id, date(2026, 1, 1), "gone"))

        with frozen_now(NOW):
            before = {s: active_users.get_activity(self.org, s, [12]) for s in SEGMENTS}

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
        self.assertGreater(active_users._delete_sketches(self.org), 0)

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
            active_users._delete_sketches(self.org)

            self.assertEqual((1, 1), active_users.restore(self.org))
            self.assertEqual(1, self.pfcount(date(2026, 8, 1), "all"))
            self.assertEqual(1, self.pfcount(date(2026, 10, 1), "gender:F"))

            # nothing to restore from fills back everything from the results, here the one as it is now
            ActiveUsersCheckpoint.objects.all().delete()
            active_users._delete_sketches(self.org)
            self.assertEqual((0, 1), active_users.restore(self.org))
            self.assertEqual(0, self.pfcount(date(2026, 8, 1), "all"))
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

            active_users._delete_sketches(self.org)
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

        # the sketches past their retention go with them
        self.assertEqual(0, self.pfcount(date(2024, 1, 1), "all"))
        self.assertEqual(1, self.pfcount(date(2026, 1, 1), "all"))

    def test_prune_checkpoint_history(self):
        now = datetime(2026, 10, 15, tzinfo=tzone.utc)
        jan = active_users.sketch_key(self.org.id, date(2026, 1, 1), "all")
        feb = active_users.sketch_key(self.org.id, date(2026, 2, 1), "all")

        # a sketch touched on each of these, and another only on the first
        for days in (50, 40, 35, 10):
            with frozen_now(now - timedelta(days=days)):
                self.r.pfadd(jan, f"c{days}")
                self.r.sadd(active_users.DIRTY_KEY, jan)
                if days == 50:
                    self.r.pfadd(feb, "c")
                    self.r.sadd(active_users.DIRTY_KEY, feb)
                active_users.checkpoint()

        def taken(key):
            rows = ActiveUsersCheckpoint.objects.filter(key=key).order_by("taken_on").values_list("taken_on", flat=True)
            return [(now - t).days for t in rows]

        self.assertEqual(4, ActiveUsersCheckpointRun.objects.count())

        with frozen_now(now):
            active_users.prune_checkpoints()

        # what a restore as of the oldest day it can go back to needs, and everything since
        self.assertEqual([35, 10], taken(jan))
        self.assertEqual([50], taken(feb))
        self.assertEqual(
            [40, 35, 10],
            [
                (now - t).days
                for t in ActiveUsersCheckpointRun.objects.order_by("id").values_list("taken_on", flat=True)
            ],
        )

    def test_checkpoints_kept_each_night(self):
        key = active_users.sketch_key(self.org.id, date(2026, 8, 1), "all")
        with frozen_now(NOW - timedelta(days=1)):
            active_users.add_results([self.result("c1", datetime(2026, 8, 1, tzinfo=tzone.utc))])
            active_users.checkpoint()
            first = bytes(ActiveUsersCheckpoint.objects.get(key=key).value)

        with frozen_now(NOW):
            active_users.add_results([self.result("c2", datetime(2026, 8, 2, tzinfo=tzone.utc))])

            # a sketch saved by an interrupted run and touched again before the run resuming it is saved once
            self.r.sunionstore(active_users.CHECKPOINTING_KEY, active_users.DIRTY_KEY)
            self.assertEqual(2, active_users.checkpoint())

            rows = list(ActiveUsersCheckpoint.objects.filter(key=key).order_by("taken_on"))
            self.assertEqual([NOW - timedelta(days=1), NOW], [c.taken_on for c in rows])
            self.assertEqual(first, bytes(rows[0].value))

            # a restore takes the latest
            active_users._delete_sketches(self.org)
            self.assertEqual((1, 0), active_users.restore(self.org))
            self.assertEqual(2, self.pfcount(date(2026, 8, 1), "all"))

    def test_rollback(self):
        august, september = date(2026, 8, 1), date(2026, 9, 1)
        night1, night2 = NOW - timedelta(days=3), NOW - timedelta(days=1)

        with frozen_now(night1):
            PollResult.objects.bulk_create([self.result("c1", datetime(2026, 8, 1, tzinfo=tzone.utc))])
            active_users.add_results(list(PollResult.objects.filter(contact="c1")))
            active_users.checkpoint()

        # a result after the good checkpoint, and contacts that were never answers in one sketch it has and one it hasn't
        with frozen_now(night2):
            PollResult.objects.bulk_create([self.result("c2", datetime(2026, 8, 2, tzinfo=tzone.utc))])
            active_users.add_results(list(PollResult.objects.filter(contact="c2")))
            for month in (august, september):
                self.r.pfadd(active_users.sketch_key(self.org.id, month, "all"), "wrong")
                self.r.sadd(active_users.DIRTY_KEY, active_users.sketch_key(self.org.id, month, "all"))
            active_users.checkpoint()

        self.assertEqual(3, self.pfcount(august, "all"))
        self.assertEqual(1, self.pfcount(september, "all"))

        with frozen_now(NOW):
            self.assertEqual((1, 2), active_users.restore(self.org, as_of=night1))

            self.assertEqual(2, self.pfcount(august, "all"))
            self.assertEqual(0, self.pfcount(september, "all"))

            # what was saved after it is gone, so a later restore doesn't bring it back
            self.assertEqual(
                {night1}, set(ActiveUsersCheckpoint.objects.filter(org=self.org).values_list("taken_on", flat=True))
            )
            active_users.restore(self.org)
            self.assertEqual(2, self.pfcount(august, "all"))
            self.assertEqual(0, self.pfcount(september, "all"))

    def test_rollback_limits(self):
        with frozen_now(NOW):
            active_users.add_results([self.result("c1", datetime(2026, 8, 1, tzinfo=tzone.utc))])

            with self.assertRaisesRegex(ValueError, "Can only roll back 30 days"):
                active_users.restore(self.org, as_of=NOW - timedelta(days=31))
            with self.assertRaisesRegex(ValueError, "No completed checkpoint"):
                active_users.restore(self.org, as_of=NOW - timedelta(days=1))

            # neither touched the sketches
            self.assertEqual(1, self.pfcount(date(2026, 8, 1), "all"))

    def test_rollback_with_nothing_to_restore(self):
        with frozen_now(NOW - timedelta(days=1)):
            active_users.checkpoint()

        with frozen_now(NOW):
            PollResult.objects.bulk_create([self.result("c1", datetime(2026, 8, 1, tzinfo=tzone.utc))])
            self.assertEqual((0, 1), active_users.restore(self.org, as_of=NOW))
            self.assertEqual(1, self.pfcount(date(2026, 8, 1), "all"))

    def test_clear_ignores_earlier_checkpoints(self):
        kept, dropped = date(2026, 8, 1), date(2026, 9, 1)
        before, cleared, rebuilt = NOW - timedelta(days=3), NOW - timedelta(days=2), NOW - timedelta(days=1)

        with frozen_now(before):
            PollResult.objects.bulk_create([self.result("c1", datetime(2026, 8, 1, tzinfo=tzone.utc))])
            active_users.add_results(
                list(PollResult.objects.filter(contact="c1"))
                + [self.result("wrong", datetime(2026, 9, 1, tzinfo=tzone.utc))]
            )
            active_users.checkpoint()

        with frozen_now(cleared):
            self.assertGreater(active_users.clear(self.org), 0)

        with frozen_now(rebuilt):
            active_users.backfill(self.org)
            active_users.checkpoint()

        # a sketch the rebuild didn't fill back isn't brought back
        with frozen_now(NOW):
            active_users._delete_sketches(self.org)
            active_users.restore(self.org)
            self.assertEqual(1, self.pfcount(kept, "all"))
            self.assertEqual(0, self.pfcount(dropped, "all"))

            # unless rolling back to before it was cleared
            active_users.restore(self.org, as_of=before)
            self.assertEqual(1, self.pfcount(dropped, "all"))

    def test_backfill(self):
        results = self.seed()
        PollResult.objects.bulk_create(
            [self.result("other-org", datetime(2026, 1, 5, tzinfo=tzone.utc), flow="flow-1", org=self.nigeria)]
        )

        with frozen_now(NOW):
            added = active_users.backfill(self.org, since=date(2026, 1, 1), until=date(2026, 3, 1), batch_size=3)
            self.assertEqual(len([r for r in results if date(2026, 1, 1) <= r.date.date() < date(2026, 4, 1)]), added)
            self.assertEqual(0, self.pfcount(date(2025, 12, 1), "all"))
            self.assertGreater(self.pfcount(date(2026, 3, 1), "all"), 0)
            self.assertEqual(0, self.pfcount(date(2026, 4, 1), "all"))
            self.assertEqual(0, self.pfcount(date(2026, 1, 1), "all", org=self.nigeria))

            # the rest, overlapping what's there
            self.assertEqual(len(results), active_users.backfill(self.org))
            for segment in SEGMENTS:
                self.assertEqual(
                    self.expected_activity(results, segment, [12]),
                    active_users.get_activity(self.org, segment, [12]),
                    segment,
                )

            # the sketches it touched are left to be checkpointed
            self.assertIn(active_users.sketch_key(self.org.id, date(2026, 1, 1), "all"), self.dirty())

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

    def test_command(self):
        results = self.seed()

        def run(*args):
            out = StringIO()
            with frozen_now(NOW):
                call_command("active_users", *args, stdout=out)
            return out.getvalue()

        out = run(
            "backfill",
            "--org",
            str(self.org.id),
            "--since",
            "2024-10",
            "--until",
            "2026-10",
            "--clear",
        )
        self.assertIn(f"sketches of org #{self.org.id}", out)
        self.assertIn("flow flow-1", out)
        self.assertIn(f"org #{self.org.id} (uganda): {len(results)} results", out)

        self.assertIn("Checkpointed", run("checkpoint"))
        self.assertIn(f"sketches of org #{self.org.id} and replayed", run("restore", "--org", str(self.org.id)))

        out = run("restore", "--org", str(self.org.id), "--as-of", "2026-10-15")
        self.assertIn(f"sketches of org #{self.org.id} and replayed", out)
        with self.assertRaisesRegex(CommandError, "Can only roll back 30 days"):
            run("restore", "--org", str(self.org.id), "--as-of", "2020-01-01")
        with self.assertRaisesRegex(CommandError, "Invalid day nope"):
            run("restore", "--org", str(self.org.id), "--as-of", "nope")

        # all active orgs by default
        self.assertIn(f"org #{self.nigeria.id} (nigeria): 0 results", run("backfill"))

        with self.assertRaises(Exception):
            run("backfill", "--since", "nope")

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

    def test_remove_expiries(self):
        sketch = active_users.sketch_key(self.org.id, date(2026, 3, 1), "all")
        tmp_key = f"{sketch}:restoring"
        self.r.pfadd(sketch, "c1")
        self.r.expire(sketch, 1000)
        self.r.set(tmp_key, b"x", ex=60)
        self.addCleanup(self.r.delete, tmp_key)

        out = StringIO()
        call_command("active_users", "remove-expiries", stdout=out)

        self.assertRegex(out.getvalue(), r"Removed the expiry of \d+ sketches")
        self.assertEqual(-1, self.r.ttl(sketch))
        self.assertGreater(self.r.ttl(tmp_key), 0)

    def test_parse_key(self):
        self.assertEqual(
            (12, date(2026, 3, 1), "born:1990"),
            active_users.parse_key(active_users.sketch_key(12, date(2026, 3, 1), "born:1990")),
        )
        self.assertEqual(date(2027, 2, 1), active_users.add_months(date(2026, 11, 1), 3))
        self.assertEqual(date(2025, 11, 1), active_users.add_months(date(2026, 1, 1), -2))
        self.assertEqual(13, len(active_users.chart_months(NOW)))
