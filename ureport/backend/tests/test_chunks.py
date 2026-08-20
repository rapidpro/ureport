# -*- coding: utf-8 -*-

import json

from mock import patch
from temba_client.exceptions import TembaRateExceededError
from temba_client.v2.types import Archive as TembaArchive, Contact as TembaContact, ObjectRef, Run as TembaRun

from django.utils import timezone

from dash.categories.models import Category
from ureport.backend import BaseBackend, ChunkResult
from ureport.backend.rapidpro import RapidProBackend
from ureport.contacts.models import Contact
from ureport.polls.models import PollResult
from ureport.tests import UreportTest
from ureport.utils import datetime_to_json_date


class CursorMockIterator:
    def __init__(self, fetches, pos, raise_on_fetch):
        self.fetches = fetches
        self.pos = pos
        self.raise_on_fetch = raise_on_fetch
        self.fetched_any = False

    def __iter__(self):
        return self

    def __next__(self):
        if self.raise_on_fetch is not None and self.pos == self.raise_on_fetch:
            raise TembaRateExceededError(0)
        if self.pos >= len(self.fetches):
            raise StopIteration()
        fetch = self.fetches[self.pos]
        self.pos += 1
        self.fetched_any = True
        return fetch

    def get_cursor(self):
        # like the real client: no cursor until a fetch has succeeded on THIS iterator
        # (a pending resume_cursor is not consulted), and none once exhausted
        if not self.fetched_any:
            return None
        return str(self.pos) if self.pos < len(self.fetches) else None


class CursorMockQuery:
    """
    Like dash's MockClientQuery but honoring iterfetches' resume_cursor and exposing
    get_cursor with the real client's semantics, so chunked pulls can be tested for
    resume behavior.
    """

    def __init__(self, *fetches, raise_on_fetch=None):
        self.fetches = list(fetches)
        self.raise_on_fetch = raise_on_fetch

    def iterfetches(self, retry_on_rate_exceed=False, resume_cursor=None):
        return CursorMockIterator(self.fetches, int(resume_cursor) if resume_cursor else 0, self.raise_on_fetch)


class PullResultsChunkTest(UreportTest):
    def setUp(self):
        super().setUp()
        self.backend = RapidProBackend(self.rapidpro_backend)
        education = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )
        self.poll = self.create_poll(self.nigeria, "Flow 1", "flow-uuid", education, self.admin)
        self.create_poll_question(self.admin, self.poll, "question 1", "ruleset-uuid")

        PollResult.objects.all().delete()
        Contact.objects.create(org=self.nigeria, uuid="C-001", gender="M", born=1990)
        Contact.objects.create(org=self.nigeria, uuid="C-002", gender="F", born=1995)

    def _run(self, uuid, contact_uuid, value, modified_on):
        return TembaRun.create(
            uuid=uuid,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid=contact_uuid, name="Reporter"),
            responded=True,
            values={"q1": TembaRun.Value.create(value=value, category="Win", node="ruleset-uuid", time=modified_on)},
            path=[TembaRun.Step.create(node="ruleset-uuid", time=modified_on)],
            created_on=modified_on,
            modified_on=modified_on,
            exited_on=modified_on,
            exit_type="completed",
        )

    @patch("dash.orgs.models.TembaClient.get_runs")
    def test_completes_in_one_chunk(self, mock_get_runs):
        now = timezone.now()
        run1 = self._run(1234, "C-001", "yes", now - timezone.timedelta(hours=1))
        run2 = self._run(1235, "C-002", "no", now)
        mock_get_runs.return_value = CursorMockQuery([run1], [run2])

        result = self.backend.pull_results_chunk(self.poll, {})

        self.assertTrue(result.done)
        self.assertFalse(result.rate_limited)
        self.assertEqual(result.counts["num_val_created"], 2)
        self.assertEqual(result.counts["num_synced"], 2)
        self.assertEqual(result.cursor["after"], datetime_to_json_date(now))
        self.assertNotIn("resume", result.cursor)
        self.assertEqual(PollResult.objects.filter(flow="flow-uuid").count(), 2)

        # the chunk contract: counts and cursor are JSON serializable
        json.dumps(result.counts)
        json.dumps(result.cursor)

        mock_get_runs.assert_called_with(flow="flow-uuid", after=None, reverse=True, paths=True)

    @patch("dash.orgs.models.TembaClient.get_runs")
    def test_empty_first_page(self, mock_get_runs):
        mock_get_runs.return_value = CursorMockQuery()

        result = self.backend.pull_results_chunk(self.poll, {})

        self.assertTrue(result.done)
        self.assertEqual(result.cursor, {"after": None})
        json.dumps(result.cursor)

    @patch("dash.orgs.models.TembaClient.get_runs")
    def test_resumes_across_chunks(self, mock_get_runs):
        now = timezone.now()
        earlier = now - timezone.timedelta(hours=1)
        run1 = self._run(1234, "C-001", "yes", earlier)
        run2 = self._run(1235, "C-002", "no", now)
        mock_get_runs.return_value = CursorMockQuery([run1], [run2])

        first = self.backend.pull_results_chunk(self.poll, {}, page_budget=1)

        self.assertFalse(first.done)
        self.assertEqual(first.counts["num_val_created"], 1)
        self.assertEqual(first.cursor, {"after": datetime_to_json_date(earlier), "resume": "1"})
        self.assertEqual(PollResult.objects.filter(flow="flow-uuid").count(), 1)

        second = self.backend.pull_results_chunk(self.poll, first.cursor, page_budget=1)

        self.assertTrue(second.done)
        self.assertEqual(second.counts["num_val_created"], 1)
        self.assertEqual(second.cursor["after"], datetime_to_json_date(now))
        self.assertEqual(PollResult.objects.filter(flow="flow-uuid").count(), 2)

        # both chunks together produced exactly what one pass would have
        self.assertEqual(
            set(PollResult.objects.filter(flow="flow-uuid").values_list("contact", flat=True)), {"C-001", "C-002"}
        )

    @patch("dash.orgs.models.TembaClient.get_runs")
    def test_budget_ending_on_last_page_is_done(self, mock_get_runs):
        now = timezone.now()
        mock_get_runs.return_value = CursorMockQuery([self._run(1234, "C-001", "yes", now)])

        result = self.backend.pull_results_chunk(self.poll, {}, page_budget=1)

        self.assertTrue(result.done)
        self.assertNotIn("resume", result.cursor)

    @patch("dash.orgs.models.TembaClient.get_runs")
    def test_rate_limit_keeps_progress(self, mock_get_runs):
        now = timezone.now()
        earlier = now - timezone.timedelta(hours=1)
        run1 = self._run(1234, "C-001", "yes", earlier)
        run2 = self._run(1235, "C-002", "no", now)
        mock_get_runs.return_value = CursorMockQuery([run1], [run2], raise_on_fetch=1)

        result = self.backend.pull_results_chunk(self.poll, {})

        self.assertFalse(result.done)
        self.assertTrue(result.rate_limited)
        # the first page's work is kept and the cursor resumes at the failed page
        self.assertEqual(result.counts["num_val_created"], 1)
        self.assertEqual(result.cursor, {"after": datetime_to_json_date(earlier), "resume": "1"})

    @patch("dash.orgs.models.TembaClient.get_runs")
    def test_rate_limit_on_first_page_of_resumed_chunk_keeps_resume_cursor(self, mock_get_runs):
        now = timezone.now()
        run1 = self._run(1234, "C-001", "yes", now)
        run2 = self._run(1235, "C-002", "no", now)
        # resumed at page 1, which immediately rate limits - no fetch succeeds
        mock_get_runs.return_value = CursorMockQuery([run1], [run2], raise_on_fetch=1)

        cursor = {"after": datetime_to_json_date(now), "resume": "1"}
        result = self.backend.pull_results_chunk(self.poll, cursor)

        self.assertTrue(result.rate_limited)
        # the incoming resume position must survive, not be dropped
        self.assertEqual(result.cursor["resume"], "1")

    @patch("dash.orgs.models.TembaClient.get_runs")
    def test_stopped_syncing_poll_is_done_immediately(self, mock_get_runs):
        self.poll.stopped_syncing = True
        self.poll.save()

        result = self.backend.pull_results_chunk(self.poll, {"after": "t1"})

        self.assertTrue(result.done)
        self.assertEqual(result.cursor, {"after": "t1"})
        mock_get_runs.assert_not_called()


class PullContactsChunkTest(UreportTest):
    def setUp(self):
        super().setUp()
        self.backend = RapidProBackend(self.rapidpro_backend)

    def _contact(self, uuid):
        # not in the configured reporter group so it syncs with the ignored outcome
        return TembaContact.create(
            uuid=uuid,
            name="Jan",
            urns=[],
            groups=[ObjectRef.create(uuid="G-007", name="Actors")],
            fields={},
            language="eng",
            created_on=timezone.now(),
        )

    @patch("dash.orgs.models.TembaClient.get_contacts")
    def test_active_stage_time_boxed_then_deleted_stage(self, mock_get_contacts):
        mock_get_contacts.return_value = CursorMockQuery([self._contact("C-001")], [self._contact("C-002")])

        # a tiny time budget stops the active stage after the first fetch
        first = self.backend.pull_contacts_chunk(self.nigeria, None, None, {}, time_budget=0.000001)

        self.assertFalse(first.done)
        self.assertEqual(first.cursor, {"stage": "active", "resume": "1"})
        self.assertEqual(first.counts["ignored"], 1)
        json.dumps(first.counts)
        json.dumps(first.cursor)

        # resuming processes only the remaining fetch then moves to the deleted stage
        second = self.backend.pull_contacts_chunk(self.nigeria, None, None, first.cursor, time_budget=600)

        self.assertFalse(second.done)
        self.assertEqual(second.cursor, {"stage": "deleted"})
        self.assertEqual(second.counts["ignored"], 1)

        # deleted stage completes the pull (no local contacts to delete)
        mock_get_contacts.return_value = CursorMockQuery([self._contact("C-003")])
        third = self.backend.pull_contacts_chunk(self.nigeria, None, None, second.cursor)

        self.assertTrue(third.done)
        self.assertEqual(third.cursor, {})
        mock_get_contacts.assert_called_with(deleted=True, after=None, before=None)

    @patch("dash.orgs.models.TembaClient.get_contacts")
    def test_deleted_stage_is_page_bounded(self, mock_get_contacts):
        pages = [[self._contact(f"C-{i:03}")] for i in range(RapidProBackend.CONTACTS_DELETED_PAGE_BUDGET + 2)]
        mock_get_contacts.return_value = CursorMockQuery(*pages)

        result = self.backend.pull_contacts_chunk(self.nigeria, None, None, {"stage": "deleted"})

        self.assertFalse(result.done)
        self.assertEqual(
            result.cursor, {"stage": "deleted", "resume": str(RapidProBackend.CONTACTS_DELETED_PAGE_BUDGET)}
        )

        # resuming finishes the remaining pages
        second = self.backend.pull_contacts_chunk(self.nigeria, None, None, result.cursor)
        self.assertTrue(second.done)
        self.assertEqual(second.cursor, {})

    @patch("dash.orgs.models.TembaClient.get_contacts")
    def test_rate_limit_returns_resume_cursor(self, mock_get_contacts):
        mock_get_contacts.return_value = CursorMockQuery(
            [self._contact("C-001")], [self._contact("C-002")], raise_on_fetch=1
        )

        result = self.backend.pull_contacts_chunk(self.nigeria, None, None, {})

        self.assertFalse(result.done)
        self.assertTrue(result.rate_limited)
        self.assertEqual(result.cursor, {"stage": "active", "resume": "1"})

    @patch("dash.orgs.models.TembaClient.get_contacts")
    def test_rate_limit_on_first_page_of_resumed_chunk_keeps_resume_cursor(self, mock_get_contacts):
        # resumed at page 1, which immediately rate limits - no fetch succeeds, so the
        # iterator has no cursor and the incoming one must be kept
        mock_get_contacts.return_value = CursorMockQuery(
            [self._contact("C-001")], [self._contact("C-002")], raise_on_fetch=1
        )

        result = self.backend.pull_contacts_chunk(self.nigeria, None, None, {"stage": "active", "resume": "1"})

        self.assertTrue(result.rate_limited)
        self.assertEqual(result.cursor, {"stage": "active", "resume": "1"})


class PullArchivesChunkTest(UreportTest):
    def setUp(self):
        super().setUp()
        self.backend = RapidProBackend(self.rapidpro_backend)
        education = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )
        self.poll = self.create_poll(self.nigeria, "Flow 1", "flow-uuid", education, self.admin)
        self.create_poll_question(self.admin, self.poll, "question 1", "ruleset-uuid")

        PollResult.objects.all().delete()
        Contact.objects.create(org=self.nigeria, uuid="C-001", gender="M", born=1990)
        Contact.objects.create(org=self.nigeria, uuid="C-002", gender="F", born=1995)

    def _archive(self, start_date, record_count=1, period="daily"):
        return TembaArchive.create(
            type="run",
            start_date=f"{start_date}T00:00:00.000Z",
            period=period,
            record_count=record_count,
            size=1024,
            hash="feca9988b7772c003204a28bd741d0d0",
            download_url="http://example.com/archive.jsonl.gz",
        )

    def _key(self, archive):
        return f"{str(archive.start_date)[:10]}|{archive.period}"

    def _run(self, uuid, contact_uuid, modified_on):
        return TembaRun.create(
            uuid=uuid,
            flow=ObjectRef.create(uuid="flow-uuid", name="Flow 1"),
            contact=ObjectRef.create(uuid=contact_uuid, name="Reporter"),
            responded=True,
            values={"q1": TembaRun.Value.create(value="yes", category="Win", node="ruleset-uuid", time=modified_on)},
            path=[TembaRun.Step.create(node="ruleset-uuid", time=modified_on)],
            created_on=modified_on,
            modified_on=modified_on,
            exited_on=modified_on,
            exit_type="completed",
        )

    @patch("ureport.backend.rapidpro.RapidProBackend._iter_poll_record_runs")
    @patch("dash.orgs.models.TembaClient.get_archives")
    def test_one_archive_per_chunk(self, mock_get_archives, mock_iter_records):
        now = timezone.now()
        newer, older = self._archive("2026-03-03"), self._archive("2026-03-02")
        mock_get_archives.return_value = CursorMockQuery([newer, older])
        mock_iter_records.side_effect = [
            iter([[self._run(1234, "C-001", now)]]),
            iter([[self._run(1235, "C-002", now)]]),
        ]

        first = self.backend.pull_results_from_archives_chunk(self.poll, {}, archive_budget=1)

        self.assertFalse(first.done)
        self.assertEqual(first.cursor, {"before": self._key(newer).split("|")[0], "seen": [self._key(newer)]})
        self.assertEqual(first.counts["num_val_created"], 1)
        self.assertEqual(PollResult.objects.filter(flow="flow-uuid").count(), 1)
        json.dumps(first.cursor)

        mock_get_archives.return_value = CursorMockQuery([newer, older])
        second = self.backend.pull_results_from_archives_chunk(self.poll, first.cursor, archive_budget=1)

        self.assertTrue(second.done)
        self.assertEqual(second.cursor, {"before": self._key(older).split("|")[0], "seen": [self._key(older)]})
        self.assertEqual(second.counts["num_val_created"], 1)
        self.assertEqual(PollResult.objects.filter(flow="flow-uuid").count(), 2)

        # only the unvisited archive was downloaded on the second chunk
        self.assertEqual(mock_iter_records.call_count, 2)

    @patch("ureport.backend.rapidpro.RapidProBackend._iter_poll_record_runs")
    @patch("dash.orgs.models.TembaClient.get_archives")
    def test_survives_listing_changing_between_chunks(self, mock_get_archives, mock_iter_records):
        now = timezone.now()
        processed_dates = []

        def record(archive, flow_uuid):
            processed_dates.append(str(archive.start_date)[:10])
            return iter([[self._run(1000 + len(processed_dates), "C-001", now)]])

        mock_iter_records.side_effect = record

        # chunk 1 processes the newest daily
        mock_get_archives.return_value = CursorMockQuery([self._archive("2026-02-03"), self._archive("2026-02-02")])
        first = self.backend.pull_results_from_archives_chunk(self.poll, {}, archive_budget=1)
        self.assertFalse(first.done)

        # before chunk 2: a NEW newer archive appears and the Feb dailies roll up into a
        # monthly - the listing has completely changed shape
        mock_get_archives.return_value = CursorMockQuery(
            [
                self._archive("2026-02-04"),  # new, outside this traversal
                self._archive("2026-02-01", period="monthly"),
                self._archive("2026-01-15"),
            ]
        )
        second = self.backend.pull_results_from_archives_chunk(self.poll, first.cursor, archive_budget=1)
        self.assertFalse(second.done)

        mock_get_archives.return_value = CursorMockQuery(
            [
                self._archive("2026-02-04"),
                self._archive("2026-02-01", period="monthly"),
                self._archive("2026-01-15"),
            ]
        )
        third = self.backend.pull_results_from_archives_chunk(self.poll, second.cursor, archive_budget=1)
        self.assertTrue(third.done)

        # the new head archive was skipped (its runs were live when the traversal started),
        # and the monthly rollup and older archive were both processed - nothing lost
        self.assertEqual(processed_dates, ["2026-02-03", "2026-02-01", "2026-01-15"])

    @patch("ureport.backend.rapidpro.RapidProBackend._iter_poll_record_runs")
    @patch("dash.orgs.models.TembaClient.get_archives")
    def test_empty_archives_do_not_consume_budget(self, mock_get_archives, mock_iter_records):
        now = timezone.now()
        mock_get_archives.return_value = CursorMockQuery(
            [self._archive("2026-03-03", record_count=0), self._archive("2026-03-02", record_count=0)]
        )

        first = self.backend.pull_results_from_archives_chunk(self.poll, {}, archive_budget=1)

        # both empties were passed in a single chunk without consuming the budget
        self.assertTrue(first.done)
        self.assertEqual(first.cursor["before"], "2026-03-02")
        mock_iter_records.assert_not_called()

        # a run-bearing archive after empties is still processed within the same chunk
        mock_get_archives.return_value = CursorMockQuery(
            [self._archive("2026-03-05", record_count=0), self._archive("2026-03-04", record_count=1)]
        )
        mock_iter_records.side_effect = [iter([[self._run(1234, "C-001", now)]])]
        result = self.backend.pull_results_from_archives_chunk(self.poll, {}, archive_budget=1)
        self.assertTrue(result.done)
        self.assertEqual(result.counts["num_val_created"], 1)

    @patch("dash.orgs.models.TembaClient.get_archives")
    def test_failing_archive_is_recorded_and_does_not_block_progress(self, mock_get_archives):
        broken = self._archive("2026-03-03")
        mock_get_archives.return_value = CursorMockQuery([broken])

        with patch.object(RapidProBackend, "_iter_poll_record_runs", side_effect=ValueError("corrupt")):
            result = self.backend.pull_results_from_archives_chunk(self.poll, {}, archive_budget=1)

        self.assertTrue(result.done)
        self.assertEqual(result.cursor["failed"], [self._key(broken)])
        self.assertEqual(result.counts["num_val_created"], 0)
        json.dumps(result.cursor)


class DummyBackend(BaseBackend):
    def pull_fields(self, org):
        return {}

    def pull_boundaries(self, org):
        return {}

    def pull_contacts(self, org, modified_after, modified_before, progress_callback=None):
        from dash.utils.sync import SyncOutcome

        return ({SyncOutcome.created: 3, SyncOutcome.updated: 1}, None)

    def pull_results(self, poll, modified_after, modified_before):
        return (1, 2, 3, 4, 5, 6)


class BaseBackendChunkDefaultsTest(UreportTest):
    """
    Backends without real pagination support (e.g. FLOIP) inherit single chunk defaults
    so callers can use the chunked interface uniformly, with the same counts schema as
    the chunked implementations.
    """

    def setUp(self):
        super().setUp()
        self.backend = DummyBackend(self.floip_backend)

    def test_pull_contacts_chunk_default(self):
        result = self.backend.pull_contacts_chunk(self.nigeria, None, None, {})

        self.assertIsInstance(result, ChunkResult)
        self.assertTrue(result.done)
        self.assertEqual(result.counts, {"created": 3, "updated": 1, "deleted": 0, "ignored": 0})
        json.dumps(result.counts)

    def test_pull_results_chunk_default(self):
        result = self.backend.pull_results_chunk(None, {})

        self.assertTrue(result.done)
        self.assertEqual(result.counts["num_val_created"], 1)
        self.assertEqual(result.counts["num_path_ignored"], 6)
        self.assertEqual(result.counts["num_synced"], 0)

    def test_pull_archives_chunk_default(self):
        result = self.backend.pull_results_from_archives_chunk(None, {"before": "t"})

        self.assertTrue(result.done)
        self.assertEqual(result.cursor, {"before": "t"})
        self.assertEqual(result.counts["num_synced"], 0)
