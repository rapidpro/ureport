from datetime import date
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction

from ureport.flows.models import FlowResult, FlowResultCategory
from ureport.stats.models import ContactActivityCounter, PollEngagementDailyCount, PollStatsCounter
from ureport.tests import UreportTest
from ureport.utils.counts import get_merge_squashed_sql


class SquashableCountTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.flow_result = FlowResult.objects.create(
            org=self.uganda, flow_uuid="flow-uuid-1", result_uuid="result-uuid-1", result_name="Q1"
        )
        self.yes = FlowResultCategory.objects.create(flow_result=self.flow_result, category="Yes")

    def add_stats(self, count, category=None, scope="all", is_squashed=False):
        return PollStatsCounter.objects.create(
            org=self.uganda,
            flow_result=self.flow_result,
            flow_result_category=category,
            scope=scope,
            count=count,
            is_squashed=is_squashed,
        )

    def add_engagement(self, count, is_responded=None, day=date(2026, 1, 1), is_squashed=False):
        return PollEngagementDailyCount.objects.create(
            org=self.uganda,
            flow_result=self.flow_result,
            is_responded=is_responded,
            scope="all",
            day=day,
            count=count,
            is_squashed=is_squashed,
        )

    def add_activity(self, count, value="M", is_squashed=False):
        return ContactActivityCounter.objects.create(
            org=self.uganda, date=date(2026, 1, 1), type="G", value=value, count=count, is_squashed=is_squashed
        )

    def assert_rows(self, qs, expected):
        self.assertEqual(sorted(expected), sorted(qs.values_list("count", "is_squashed")))

    def test_squash(self):
        stats = PollStatsCounter.objects.filter(flow_result=self.flow_result)

        # a set with no squashed row gets one, including a set over a NULL category
        self.add_stats(2, category=self.yes)
        self.add_stats(3, category=self.yes)
        self.add_stats(1)
        self.add_stats(4)

        self.assertEqual(2, PollStatsCounter.squash())
        self.assert_rows(stats, [(5, True), (5, True)])
        yes_total = stats.get(flow_result_category=self.yes)
        null_total = stats.get(flow_result_category=None)

        # deltas are added onto the existing squashed rows, which keep their ids
        self.add_stats(-1, category=self.yes)
        self.add_stats(2)

        self.assertEqual(2, PollStatsCounter.squash())
        self.assertEqual({(yes_total.id, 4), (null_total.id, 7)}, set(stats.values_list("id", "count")))

        # deltas summing to zero leave the total untouched
        self.add_stats(3, category=self.yes)
        self.add_stats(-3, category=self.yes)

        PollStatsCounter.squash()
        self.assertEqual({(yes_total.id, 4), (null_total.id, 7)}, set(stats.values_list("id", "count")))

        # a total reaching zero is deleted, and comes back with later deltas
        self.add_stats(-7)

        PollStatsCounter.squash()
        self.assertEqual([(yes_total.id, 4)], list(stats.values_list("id", "count")))

        self.add_stats(2)

        PollStatsCounter.squash()
        self.assertEqual({(self.yes.id, 4), (None, 2)}, set(stats.values_list("flow_result_category_id", "count")))

        # totals can go negative
        self.add_stats(-5, category=self.yes)

        PollStatsCounter.squash()
        self.assertEqual(-1, stats.get(flow_result_category=self.yes).count)

        # nothing to squash
        self.assertEqual(0, PollStatsCounter.squash())

    def test_squash_engagement(self):
        engagement = PollEngagementDailyCount.objects.filter(flow_result=self.flow_result)

        self.add_engagement(1)
        self.add_engagement(2)
        self.add_engagement(4, is_responded=True)

        self.assertEqual(2, PollEngagementDailyCount.squash())
        self.assert_rows(engagement, [(3, True), (4, True)])
        null_total = engagement.get(is_responded=None)

        self.add_engagement(5)

        PollEngagementDailyCount.squash()
        self.assertEqual(8, engagement.get(id=null_total.id).count)
        self.assertEqual(2, engagement.count())

        # a total reaching zero is deleted
        self.add_engagement(-8)
        self.add_engagement(1, is_responded=True)

        PollEngagementDailyCount.squash()
        self.assertEqual([(True, 5)], list(engagement.values_list("is_responded", "count")))

    def test_squash_max_distinct(self):
        self.add_stats(1, scope="a")
        self.add_stats(1, scope="b")
        self.add_stats(1, scope="c")

        with patch.object(PollStatsCounter, "squash_max_distinct", 2):
            self.assertEqual(2, PollStatsCounter.squash())
            self.assertEqual(1, PollStatsCounter.squash())

        self.assertEqual(3, PollStatsCounter.objects.filter(is_squashed=True).count())

    def test_squashed_rows_unique(self):
        self.add_stats(1, is_squashed=True)

        # NULLs aren't distinct, so a second squashed row for the NULL category is rejected
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_stats(1, is_squashed=True)

        self.add_engagement(1, is_squashed=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_engagement(1, is_squashed=True)

        self.add_activity(1, is_squashed=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_activity(1, is_squashed=True)

        # but any number of unsquashed rows are fine
        self.add_stats(1)
        self.add_stats(1)

    def test_squash_contact_activity(self):
        counters = ContactActivityCounter.objects.filter(org=self.uganda)

        self.add_activity(2)
        self.add_activity(3)

        ContactActivityCounter.squash()
        total = counters.get()
        self.assertEqual((5, True), (total.count, total.is_squashed))

        # deltas are added onto the squashed row, which keeps its id
        self.add_activity(2)
        ContactActivityCounter.squash()
        self.assertEqual([(total.id, 7)], list(counters.values_list("id", "count")))

        self.add_activity(-3)
        ContactActivityCounter.squash()
        self.assertEqual([(total.id, 4)], list(counters.values_list("id", "count")))

        # deltas summing to zero leave it untouched
        self.add_activity(2)
        self.add_activity(-2)
        ContactActivityCounter.squash()
        self.assertEqual([(total.id, 4)], list(counters.values_list("id", "count")))

        # it never goes below zero, and is deleted when it reaches zero
        self.add_activity(-6)
        ContactActivityCounter.squash()
        self.assertEqual(0, counters.count())

        # a set without a squashed row only gets one if its deltas sum above zero
        self.add_activity(-2)
        ContactActivityCounter.squash()
        self.assertEqual(0, counters.count())

        self.add_activity(3)
        ContactActivityCounter.squash()
        self.assertEqual([3], list(counters.values_list("count", flat=True)))

    def test_merge_squashed_sql(self):
        table = PollStatsCounter._meta.db_table
        columns = ("org_id", "flow_result_id", "flow_result_category_id", "scope")

        with connection.cursor() as cursor:
            cursor.execute('DROP INDEX "stats_psc_squashed"')

        self.add_stats(2, is_squashed=True)
        self.add_stats(3, is_squashed=True)
        self.add_stats(4, category=self.yes, is_squashed=True)
        self.add_stats(-4, category=self.yes, is_squashed=True)
        self.add_stats(1, scope="other", is_squashed=True)
        self.add_stats(6)

        with connection.cursor() as cursor:
            cursor.execute(get_merge_squashed_sql(table, columns))

        # duplicates over the NULL category are merged, ones summing to zero are dropped, others are left alone
        self.assertEqual(
            {(None, "all", 5, True), (None, "other", 1, True), (None, "all", 6, False)},
            set(PollStatsCounter.objects.values_list("flow_result_category_id", "scope", "count", "is_squashed")),
        )

    def test_merge_squashed_sql_contact_activity(self):
        table = ContactActivityCounter._meta.db_table
        columns = ("org_id", "date", "type", "value")

        with connection.cursor() as cursor:
            cursor.execute('DROP INDEX "stats_cac_squashed"')

        self.add_activity(2, is_squashed=True)
        self.add_activity(3, is_squashed=True)
        self.add_activity(4, value="F", is_squashed=True)
        self.add_activity(1)

        with connection.cursor() as cursor:
            cursor.execute(get_merge_squashed_sql(table, columns))

        self.assertEqual(
            {("M", 5, True), ("F", 4, True), ("M", 1, False)},
            set(ContactActivityCounter.objects.values_list("value", "count", "is_squashed")),
        )
