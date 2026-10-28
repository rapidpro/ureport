from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone as tzone
from unittest.mock import patch

from django.core.cache import cache

from dash.categories.models import Category
from ureport.contacts.models import ReportersCounter
from ureport.locations.models import Boundary
from ureport.stats.models import ContactActivityCounter, PollEngagementDailyCount, SchemeSegment
from ureport.tests import UreportTest
from ureport.utils import ORG_CONTACT_COUNT_KEY


@contextmanager
def frozen_now(now):
    """
    Freezes both clocks the engagement data reads - the aware one its queries start from and the naive one its date
    buckets are built from
    """

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.replace(tzinfo=None)

    with patch("django.utils.timezone.now", return_value=now), patch("ureport.utils.datetime", FrozenDatetime):
        yield


class EngagementDataTest(UreportTest):
    # just before and after the month, half month and 10 day boundaries each time filter buckets by, a leap day, and
    # the turn of a year
    NOWS = [
        datetime(2026, 3, 1, 0, 30, tzinfo=tzone.utc),
        datetime(2026, 2, 28, 23, 30, tzinfo=tzone.utc),
        datetime(2024, 2, 29, 12, 0, tzinfo=tzone.utc),
        datetime(2026, 1, 1, 0, 0, tzinfo=tzone.utc),
        datetime(2025, 12, 31, 23, 59, tzinfo=tzone.utc),
        datetime(2026, 10, 10, 12, 0, tzinfo=tzone.utc),
        datetime(2026, 10, 11, 12, 0, tzinfo=tzone.utc),
        datetime(2026, 10, 15, 12, 0, tzinfo=tzone.utc),
        datetime(2026, 10, 16, 12, 0, tzinfo=tzone.utc),
        datetime(2026, 10, 21, 12, 0, tzinfo=tzone.utc),
        datetime(2026, 10, 31, 23, 59, tzinfo=tzone.utc),
    ]

    SEED_START = date(2022, 11, 1)
    SEED_END = date(2026, 12, 31)

    def setUp(self):
        super().setUp()

        self.org = self.uganda

        SchemeSegment.objects.get_or_create(scheme="tel")
        Boundary.objects.create(org=self.org, osm_id="R1", name="Kampala", level=Boundary.STATE_LEVEL)
        Boundary.objects.create(org=self.org, osm_id="R2", name="Gulu", level=Boundary.STATE_LEVEL)

        category = Category.objects.create(org=self.org, name="Health", created_by=self.admin, modified_by=self.admin)
        poll = self.create_poll(self.org, "Poll 1", "flow-uuid-1", category, self.admin)
        flow_result = self.create_poll_question(self.admin, poll, "Q1", "result-uuid-1").flow_result

        scopes = ["all", "gender:m", "gender:f", "scheme:tel", "state:R1", "state:R2"]
        scopes += [f"age:{min_age}" for min_age in (0, 15, 20, 25, 31, 35)]

        days = [self.SEED_START + timedelta(days=i) for i in range((self.SEED_END - self.SEED_START).days + 1)]

        engagement = []
        reporters = []
        for i, day in enumerate(days):
            for j, scope in enumerate(scopes):
                # vary the counts by day and scope, and leave some days out, so that every bucket differs
                if (i + j) % 5 == 0:
                    continue
                engagement.append(self.engagement(flow_result, scope, day, None, (i * 7 + j) % 13 + 1))
                if (i + j) % 3:
                    engagement.append(self.engagement(flow_result, scope, day, True, (i * 3 + j) % 5 + 1))

            if i % 4 == 0:
                continue
            count = i % 9 + 1
            reporters += [
                f"registered_on:{day}",
                f"registered_gender:{day}:{'m' if i % 2 else 'f'}",
                f"registered_born:{day}:{1990 + i % 30}",
                f"registered_scheme:{day}:{'tel' if i % 3 else 'twitterid'}",
                f"registered_state:{day}:{'R1' if i % 5 else 'R2'}",
            ] * count

        PollEngagementDailyCount.objects.bulk_create(engagement, batch_size=5000)

        reporters_counts = {"scheme:tel": 10, "scheme:twitterid": 5}
        for counter_type in reporters:
            reporters_counts[counter_type] = reporters_counts.get(counter_type, 0) + 1
        ReportersCounter.objects.bulk_create(
            [ReportersCounter(org=self.org, type=t, count=c) for t, c in reporters_counts.items()], batch_size=5000
        )

        activity = []
        month = self.SEED_START
        k = 0
        while month <= self.SEED_END:
            for counter_type, values in (
                (ContactActivityCounter.TYPE_ALL, [""]),
                (ContactActivityCounter.TYPE_AGE, ["12", "17", "22", "28", "33", "40"]),
                (ContactActivityCounter.TYPE_GENDER, ["M", "F"]),
                (ContactActivityCounter.TYPE_LOCATION, ["R1", "R2"]),
                (ContactActivityCounter.TYPE_SCHEME, ["tel", "twitterid"]),
            ):
                for value in values:
                    k += 1
                    activity.append(
                        ContactActivityCounter(
                            org=self.org, date=month, type=counter_type, value=value, count=k % 11 + 1
                        )
                    )
            month = (month + timedelta(days=32)).replace(day=1)

        ContactActivityCounter.objects.bulk_create(activity)

        cache.delete(ORG_CONTACT_COUNT_KEY % self.org.id)

    def engagement(self, flow_result, scope, day, is_responded, count):
        return PollEngagementDailyCount(
            org=self.org, flow_result=flow_result, scope=scope, day=day, is_responded=is_responded, count=count
        )

    def combos(self):
        for metric in PollEngagementDailyCount.DATA_METRICS:
            for segment in PollEngagementDailyCount.DATA_SEGMENTS:
                yield metric, segment

    def cached(self, metric, segment, time_filter):
        key = f"org:{self.org.id}:metric:{metric}:segment:{segment}:filter:{time_filter}"
        return cache.get(key)

    def test_refresh_matches_per_filter_calculation(self):
        time_filters = list(PollEngagementDailyCount.DATA_TIME_FILTERS)

        for now in self.NOWS:
            with frozen_now(now):
                for metric, segment in self.combos():
                    with self.subTest(now=now, metric=metric, segment=segment):
                        expected = {
                            time_filter: PollEngagementDailyCount.refresh_engagement_data(
                                self.org, metric, segment, time_filters=[time_filter]
                            )[time_filter]
                            for time_filter in time_filters
                        }

                        for time_filter in time_filters:
                            # the fixture leaves no series empty, so a mismatch can't hide behind two empty outputs
                            self.assertTrue(expected[time_filter])
                            self.assertTrue(any(any(series["data"].values()) for series in expected[time_filter]))

                        self.assertEqual(
                            expected, PollEngagementDailyCount.refresh_engagement_data(self.org, metric, segment)
                        )

                        for time_filter in time_filters:
                            self.assertEqual(
                                {"results": expected[time_filter]}, self.cached(metric, segment, time_filter)
                            )
                            self.assertEqual(
                                expected[time_filter],
                                PollEngagementDailyCount.get_engagement_data(self.org, metric, segment, time_filter),
                            )

    def test_refresh_buckets(self):
        with frozen_now(datetime(2026, 3, 1, 0, 30, tzinfo=tzone.utc)):
            data = PollEngagementDailyCount.refresh_engagement_data(self.org, "opinion-responses", "all")

        # 12 months bucket by month, 6 months by half month and 3 months by 10 days, each ending with the bucket today
        # falls in
        self.assertEqual(13, len(data[12][0]["data"]))
        self.assertEqual("2026-03-01", max(data[12][0]["data"]))
        self.assertEqual(13, len(data[6][0]["data"]))
        self.assertEqual("2026-03-01", max(data[6][0]["data"]))
        self.assertEqual(10, len(data[3][0]["data"]))
        self.assertEqual("2025-12-01", min(data[3][0]["data"]))

    def test_get_engagement_data_fills_cache_on_miss(self):
        with frozen_now(datetime(2026, 10, 16, 12, 0, tzinfo=tzone.utc)):
            for time_filter in PollEngagementDailyCount.DATA_TIME_FILTERS:
                self.assertIsNone(self.cached("active-users", "gender", time_filter))

            data = PollEngagementDailyCount.get_engagement_data(self.org, "active-users", "gender", 6)

            # a miss on one filter refreshes them all
            for time_filter in PollEngagementDailyCount.DATA_TIME_FILTERS:
                self.assertIsNotNone(self.cached("active-users", "gender", time_filter))
            self.assertEqual({"results": data}, self.cached("active-users", "gender", 6))

            # a filter outside the usual ones is still calculated, and cached
            data = PollEngagementDailyCount.get_engagement_data(self.org, "active-users", "gender", 1)
            self.assertTrue(data)
            self.assertEqual({"results": data}, self.cached("active-users", "gender", 1))
