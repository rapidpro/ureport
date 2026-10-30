# -*- coding: utf-8 -*-

from datetime import timedelta, timezone as tzone
from io import StringIO

from mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from dash.categories.models import Category
from dash.orgs.models import Org, TaskState
from ureport.backend import ChunkResult
from ureport.backend.rapidpro import RapidProBackend
from ureport.contacts.models import Contact
from ureport.polls.models import Poll, PollResult
from ureport.polls.sync import (
    AGE_GENDER_JOB_TYPE,
    ARCHIVE_ATTEMPTS,
    ARCHIVES_BATCH_BUSY_BACKOFF,
    ARCHIVES_BATCH_JOB_TYPE,
    ARCHIVES_JOB_TYPE,
    ARCHIVES_LEASE_SECONDS,
    ARCHIVES_RESET_BACKOFF,
    ARCHIVES_RESET_PENDING,
    COUNTS_FULL_REBUILD_DAYS,
    COUNTS_JOB_TYPE,
    FULL_REPULL_KEY,
    PRUNE_JOB_TYPE,
    PRUNE_RETIRED,
    PRUNE_SKIPPED_PULLING,
    PRUNE_SKIPPED_RETIRED,
    RATE_LIMITED_BACKOFF,
    REBUILD_COUNTS_EVERY,
    RESULTS_JOB_TYPE,
    RESULTS_LEASE_SECONDS,
    RETIRE_FALLBACK_WAIT,
    RETIRE_KEY,
    _archives_walked,
    _counts_rebuild_due,
    _delete_flow_results,
    _finalize_archives,
    _finalize_results,
    _prune_poll,
    _retire_flow,
    backfill_age_gender,
    batch_owned_flows,
    dispatch_archives,
    dispatch_org_polls,
    is_flow_syncing,
    prune_poll_results,
    prune_results_dispatch,
    queue_archives_batch,
    queue_full_repulls,
    rebuild_counts_dispatch,
    rebuild_poll_counts,
    sync_poll_archives,
    sync_poll_archives_batch,
    sync_poll_results,
    sync_polls_dispatch,
)
from ureport.polls.tasks import (
    backfill_poll_results,
    clear_old_poll_results,
    pull_refresh,
    pull_refresh_from_archives,
    pull_results_main_poll,
    pull_results_other_polls,
    pull_results_recent_polls,
    rebuild_counts,
    update_results_age_gender,
)
from ureport.polls.views import PollCRUDL
from ureport.stats.models import PollStatsCounter
from ureport.syncjobs.models import SyncJob
from ureport.syncjobs.tests.base import (
    SyncJobTestMixin,
    drop_lease,
    end_run,
    held_lock,
    hold_lease,
    make_stale,
    reload,
    run_task,
    run_to_completion,
)
from ureport.tests import UreportTest
from ureport.utils import LAST_POPULATED_CONTACT_KEY, datetime_to_json_date


def results_counts(**overrides):
    counts = dict(
        num_val_created=0,
        num_val_updated=0,
        num_val_ignored=0,
        num_path_created=0,
        num_path_updated=0,
        num_path_ignored=0,
        num_synced=0,
    )
    counts.update(overrides)
    return counts


class PollSyncTestBase(SyncJobTestMixin, UreportTest):
    def setUp(self):
        super(PollSyncTestBase, self).setUp()

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )
        self.poll = self.create_poll(self.nigeria, "Poll 1", "uuid-1", self.education_nigeria, self.admin)

        self.addCleanup(self.clear_poll_cache_keys)
        self.clear_poll_cache_keys()

    def clear_poll_cache_keys(self):
        for poll in Poll.objects.all():
            cache.delete(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (poll.org_id, poll.flow_uuid))
            cache.delete(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (poll.org_id, poll.pk))
            cache.delete(Poll.ORG_MAIN_POLL_ID % poll.org_id)
            cache.delete(Poll.POLL_RESULTS_CHANGED_CACHE_KEY % (poll.org_id, poll.flow_uuid))
            cache.delete(Poll.POLL_COUNTS_REBUILT_CACHE_KEY % (poll.org_id, poll.flow_uuid))
            cache.delete(RETIRE_KEY % (poll.org_id, poll.flow_uuid))
            cache.delete(FULL_REPULL_KEY % (poll.org_id, poll.flow_uuid))

    def get_job(self, job_type=RESULTS_JOB_TYPE, org=None, flow_uuid="uuid-1"):
        return SyncJob.objects.get(org=org or self.nigeria, job_type=job_type, scope=flow_uuid)


class SyncPollResultsTest(PollSyncTestBase):
    def setUp(self):
        super(SyncPollResultsTest, self).setUp()

        self.job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")

        # a flow created now has no archived runs, so archives stay out of the way unless
        # a test asks for them
        self.mock_flow_date = self.start_patch(patch.object(Poll, "get_flow_date"))
        self.mock_flow_date.return_value = datetime_to_json_date(timezone.now().replace(tzinfo=tzone.utc))

        self.mock_queue_archives = self.start_patch(patch.object(sync_poll_archives, "apply_async"))
        self.mock_rebuild = self.start_patch(patch.object(Poll, "rebuild_poll_results_counts"))

    def test_seeds_cursor_from_legacy_cache_key(self):
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, "uuid-1"), "2026-08-01T10:00:00.000Z", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(
                counts=results_counts(num_val_created=3), cursor={"after": "2026-08-02T10:00:00.000Z"}, done=True
            )
            run_task(sync_poll_results, self.job.id)

        self.assertEqual(mock_chunk.call_args[0][1], {"after": "2026-08-01T10:00:00.000Z"})

    def test_starts_from_scratch_without_legacy_position(self):
        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": None}, done=True)
            run_task(sync_poll_results, self.job.id)

        self.assertEqual(mock_chunk.call_args[0][1], {})

    def test_resumes_across_chunks(self):
        chunks = [
            ChunkResult(
                counts=results_counts(num_val_created=2, num_synced=10), cursor={"after": "t1", "resume": "c1"}
            ),
            ChunkResult(counts=results_counts(num_val_created=1, num_synced=5), cursor={"after": "t2"}, done=True),
        ]

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.side_effect = chunks

            mock_continue = run_task(sync_poll_results, self.job.id)
            mock_continue.assert_called_once_with((self.job.id,), queue="sync", countdown=None)

            self.assertJobState(self.job, status=SyncJob.STATUS_RUNNING, cursor={"after": "t1", "resume": "c1"})

            # the continuation picks up from the checkpointed position
            run_task(sync_poll_results, self.job.id)

        self.assertEqual(mock_chunk.call_args_list[1][0][1], {"after": "t1", "resume": "c1"})

        job = self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={"after": "t2"})
        self.assertEqual(job.progress["chunks"], 2)
        self.assertEqual(job.progress["num_val_created"], 3)
        self.assertEqual(job.progress["num_synced"], 15)

    def test_backs_off_when_rate_limited(self):
        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(
                counts=results_counts(), cursor={"after": "t1", "resume": "c1"}, rate_limited=True
            )
            mock_continue = run_task(sync_poll_results, self.job.id)

        mock_continue.assert_called_once_with((self.job.id,), queue="sync", countdown=RATE_LIMITED_BACKOFF)
        self.assertJobState(self.job, cursor={"after": "t1", "resume": "c1"})

    def test_rebuilds_counts_periodically(self):
        # a run four chunks in, i.e. between chunks of an interrupted traversal
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_RUNNING, progress={"chunks": 4})

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(num_val_created=1), cursor={"after": "t5"})

            # the fifth chunk rebuilds so partial results reach the public site
            run_task(sync_poll_results, self.job.id)
            self.mock_rebuild.assert_called_once()

            self.mock_rebuild.reset_mock()
            run_task(sync_poll_results, self.job.id)
            self.mock_rebuild.assert_not_called()

    def test_records_when_results_changed(self):
        same_flow = self.create_poll(self.nigeria, "Same flow", "uuid-1", self.education_nigeria, self.admin)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            # a chunk that changed nothing leaves the counts as up to date as they were
            mock_chunk.return_value = ChunkResult(counts=results_counts(num_val_ignored=3), cursor={"after": "t1"})
            run_task(sync_poll_results, self.job.id)

            self.assertEqual((None, None), self.poll.get_counts_stamps())

            before = timezone.now()
            mock_chunk.return_value = ChunkResult(counts=results_counts(num_path_updated=1), cursor={"after": "t2"})
            run_task(sync_poll_results, self.job.id)

        # it's recorded for the flow, as all its polls' counts are rebuilt from the same results
        changed_on, rebuilt_on = same_flow.get_counts_stamps()
        self.assertGreaterEqual(changed_on, before)
        self.assertIsNone(rebuilt_on)

    def test_queues_archives_on_first_sync(self):
        self.mock_flow_date.return_value = None

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t1"}, done=True)

            run_task(sync_poll_results, self.job.id)

        archives_job = self.get_job(ARCHIVES_JOB_TYPE)
        self.mock_queue_archives.assert_called_once_with((archives_job.id,), queue="sync")

    def test_no_archives_for_recent_flow_or_synced_poll(self):
        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t1"}, done=True)

            run_task(sync_poll_results, self.job.id)
            self.mock_queue_archives.assert_not_called()

            # nor once the polls on the flow have completed their first sync
            self.mock_flow_date.return_value = None
            run_task(sync_poll_results, self.job.id)
            self.mock_queue_archives.assert_not_called()

        self.assertTrue(Poll.objects.get(id=self.poll.id).has_synced)
        self.assertFalse(SyncJob.objects.filter(job_type=ARCHIVES_JOB_TYPE).exists())

    def test_restarts_after_results_deleted(self):
        PollResult.objects.create(
            org=self.nigeria,
            flow="uuid-1",
            ruleset="ruleset-uuid",
            contact="contact-uuid",
            date=timezone.now(),
            completed=False,
        )
        SyncJob.objects.filter(id=self.job.id).update(cursor={"after": "t1"})
        archives_job = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=archives_job.id).update(cursor={"before": "2026-01-01"})

        cache.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk), "2026-08-01", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t2"}, done=True)

            run_task(sync_poll_results, self.job.id)

        # the traversal starts over, the deleted results are gone and the archives are walked again
        self.assertEqual(mock_chunk.call_args[0][1], {})
        self.assertFalse(PollResult.objects.filter(org=self.nigeria, flow="uuid-1").exists())
        self.assertIsNone(cache.get(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk)))
        self.assertEqual(self.get_job(ARCHIVES_JOB_TYPE).cursor, {})
        self.mock_queue_archives.assert_called_once_with((archives_job.id,), queue="sync")

        # deleting the results changed them, even with nothing pulled back yet
        self.assertIsNotNone(self.poll.get_counts_stamps()[0])

    def test_a_rebuild_during_the_delete_leaves_the_flow_due(self):
        cache.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk), "2026-08-01", None)

        # a rebuild that starts while the results are being deleted counts some of them
        def rebuilt_during_delete():
            self.poll._mark_counts_rebuilt(timezone.now())

        with (
            patch.object(Poll, "delete_poll_results", autospec=True, side_effect=lambda poll: rebuilt_during_delete()),
            patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk,
        ):
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t2"}, done=True)

            run_task(sync_poll_results, self.job.id)

        changed_on, rebuilt_on = self.poll.get_counts_stamps()
        self.assertGreater(changed_on, rebuilt_on)

    def test_restart_survives_an_interrupted_delete(self):
        # deleting consumes the flag and the legacy position, so the restart has to already
        # be durable when a chunk dies part way through
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, "uuid-1"), "t0", None)
        SyncJob.objects.filter(id=self.job.id).update(cursor={"after": "t1"})
        cache.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk), "2026-08-01", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.side_effect = [
                ValueError("worker died"),
                ChunkResult(counts=results_counts(), cursor={"after": "t2"}, done=True),
            ]

            with patch.object(sync_poll_results, "apply_async"):
                with self.assertRaises(ValueError):
                    sync_poll_results(self.job.id)

            self.assertJobState(self.job, status=SyncJob.STATUS_FAILED, cursor={})

            # the retry pulls from scratch rather than resuming past the deleted results
            run_task(sync_poll_results, self.job.id)

        self.assertEqual(mock_chunk.call_args[0][1], {})

    def test_restarts_when_a_duplicate_poll_asks_for_it(self):
        # the newest poll of the flow is the one the job syncs, but the flag can be set on
        # any poll sharing it
        newest = self.create_poll(self.nigeria, "Poll newest", "uuid-1", self.education_nigeria, self.admin)
        SyncJob.objects.filter(id=self.job.id).update(cursor={"after": "t1"})

        cache.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk), "2026-08-01", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t2"}, done=True)

            run_task(sync_poll_results, self.job.id)

        self.assertEqual(mock_chunk.call_args[0][1], {})
        self.assertEqual(mock_chunk.call_args[0][0].pk, newest.pk)

        # the flags of every poll on the flow are cleared, they never expire on their own
        for poll_id in (self.poll.pk, newest.pk):
            self.assertIsNone(cache.get(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, poll_id)))

        self.mock_queue_archives.assert_called_once()

    def test_retries_a_refused_archives_reset(self):
        archives_job = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=archives_job.id).update(
            cursor={"before": "2026-01-01"},
            status=SyncJob.STATUS_RUNNING,
            lease_owner="worker-1",
            lease_expires_on=timezone.now() + timedelta(minutes=5),
        )
        cache.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk), "2026-08-01", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t2"})

            run_task(sync_poll_results, self.job.id)

            # its worker still owns the cursor, so the reset is deferred, not dropped
            self.assertEqual(self.get_job(ARCHIVES_JOB_TYPE).cursor, {"before": "2026-01-01"})
            self.assertEqual(self.get_job().progress["archives_reset_pending"], 1)

            drop_lease(archives_job)
            run_task(sync_poll_results, self.job.id)

        self.assertEqual(self.get_job(ARCHIVES_JOB_TYPE).cursor, {})
        self.assertNotIn("archives_reset_pending", self.get_job().progress)

    def test_a_run_waits_for_a_refused_archives_reset_to_land(self):
        archives_job = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=archives_job.id).update(cursor={"before": "2026-01-01"})
        hold_lease(archives_job)
        cache.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk), "2026-08-01", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t2"}, done=True)

            # the pull is done, but ending the run would drop the reset its next run knows nothing of
            mock_continue = run_task(sync_poll_results, self.job.id)

            mock_continue.assert_called_once_with((self.job.id,), queue="sync", countdown=ARCHIVES_RESET_BACKOFF)
            self.assertJobState(self.job, status=SyncJob.STATUS_RUNNING)
            self.assertEqual(self.get_job().progress[ARCHIVES_RESET_PENDING], 1)

            # the walk holding the lease carries itself on, so no message is queued for it
            self.mock_queue_archives.assert_not_called()

            drop_lease(archives_job)
            mock_continue = run_task(sync_poll_results, self.job.id)

        mock_continue.assert_not_called()
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)
        self.assertEqual(self.get_job(ARCHIVES_JOB_TYPE).cursor, {})
        self.assertEqual(self.mock_queue_archives.call_count, 1)

    def test_queues_archives_again_after_a_failed_chunk(self):
        self.mock_flow_date.return_value = None

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.side_effect = [
                ValueError("boom"),
                ChunkResult(counts=results_counts(), cursor={"after": "t1"}, done=True),
            ]

            with patch.object(sync_poll_results, "apply_async"):
                with self.assertRaises(ValueError):
                    sync_poll_results(self.job.id)

            run_task(sync_poll_results, self.job.id)

        # one job, nudged by both attempts - the failed one never got to run the archives
        self.assertEqual(SyncJob.objects.filter(job_type=ARCHIVES_JOB_TYPE, scope="uuid-1").count(), 1)
        self.assertEqual(self.mock_queue_archives.call_count, 2)

    def test_finalize_skips_rebuild_when_nothing_changed(self):
        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(num_val_ignored=7), cursor={}, done=True)

            run_task(sync_poll_results, self.job.id)

        self.mock_rebuild.assert_not_called()
        self.assertTrue(Poll.objects.get(id=self.poll.id).has_synced)

    def test_leftover_finalize_runs_against_the_completed_run(self):
        # a worker that completed a run but died before finalizing it
        SyncJob.objects.filter(id=self.job.id).update(
            status=SyncJob.STATUS_COMPLETE,
            needs_finalize=True,
            cursor={"after": "t1"},
            progress={"chunks": 3, "num_val_created": 2},
        )

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t2"}, done=True)

            run_task(sync_poll_results, self.job.id)

        # the leftover finalize saw the completed run's counters, this run's changed nothing
        self.mock_rebuild.assert_called_once()
        self.assertTrue(Poll.objects.get(id=self.poll.id).has_synced)
        self.assertJobState(self.job, needs_finalize=False)
        self.assertEqual(cache.get(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, "uuid-1")), "t2")

    def test_completed_cursor_is_not_reseeded_from_the_legacy_key(self):
        # a stale legacy position must never pull a caught up job backwards
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_COMPLETE, cursor={"after": "t2"})
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, "uuid-1"), "t0", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t3"}, done=True)

            run_task(sync_poll_results, self.job.id)

        self.assertEqual(mock_chunk.call_args[0][1], {"after": "t2"})

    def test_finalize_marks_synced_and_mirrors_position(self):
        same_flow = self.create_poll(self.nigeria, "Poll same flow", "uuid-1", self.education_nigeria, self.admin)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(
                counts=results_counts(num_val_created=1), cursor={"after": "2026-08-11T09:00:00.000Z"}, done=True
            )
            run_task(sync_poll_results, self.job.id)

        self.mock_rebuild.assert_called_once()

        self.poll.refresh_from_db()
        same_flow.refresh_from_db()
        self.assertTrue(self.poll.has_synced)
        self.assertTrue(same_flow.has_synced)

        # the unchunked task would resume from the same position after a rollback
        self.assertEqual(
            cache.get(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, "uuid-1")),
            "2026-08-11T09:00:00.000Z",
        )

    def test_completes_without_syncable_poll(self):
        Poll.objects.filter(id=self.poll.id).update(stopped_syncing=True)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_continue = run_task(sync_poll_results, self.job.id)

        mock_chunk.assert_not_called()
        mock_continue.assert_not_called()
        self.mock_rebuild.assert_not_called()
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)


class SyncPollArchivesTest(PollSyncTestBase):
    def setUp(self):
        super(SyncPollArchivesTest, self).setUp()

        self.job = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")

    def test_resumes_across_chunks_and_finalizes(self):
        chunks = [
            ChunkResult(counts=results_counts(num_val_created=4), cursor={"before": "2026-07-01", "seen": ["a"]}),
            ChunkResult(counts=results_counts(num_val_updated=1), cursor={"before": "2026-06-01"}, done=True),
        ]

        with patch.object(RapidProBackend, "pull_results_from_archives_chunk") as mock_chunk:
            mock_chunk.side_effect = chunks

            with patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild:
                mock_continue = run_task(sync_poll_archives, self.job.id)
                mock_continue.assert_called_once_with((self.job.id,), queue="sync", countdown=None)

                run_task(sync_poll_archives, self.job.id)

        self.assertEqual(mock_chunk.call_args_list[1][0][1], {"before": "2026-07-01", "seen": ["a"]})
        mock_rebuild.assert_called_once()

        job = self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress["chunks"], 2)

        self.poll.refresh_from_db()
        self.assertTrue(self.poll.has_synced)
        self.assertIsNotNone(self.poll.get_counts_stamps()[0])

    def test_finalize_skips_rebuild_without_results(self):
        with patch.object(RapidProBackend, "pull_results_from_archives_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"before": "2026-06-01"}, done=True)

            with patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild:
                run_task(sync_poll_archives, self.job.id)

        mock_rebuild.assert_not_called()
        self.poll.refresh_from_db()
        self.assertTrue(self.poll.has_synced)
        self.assertIsNone(self.poll.get_counts_stamps()[0])

    def test_backs_off_when_rate_limited(self):
        with patch.object(RapidProBackend, "pull_results_from_archives_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(
                counts=results_counts(), cursor={"before": "2026-07-01"}, rate_limited=True
            )
            mock_continue = run_task(sync_poll_archives, self.job.id)

        mock_continue.assert_called_once_with((self.job.id,), queue="sync", countdown=RATE_LIMITED_BACKOFF)

    def test_a_new_run_retries_the_archives_it_failed_to_pull(self):
        failed = {"2026-03-03|daily": 1, "2026-02-01|monthly": ARCHIVE_ATTEMPTS}
        end_run(self.job, cursor={"before": "2026-01-01", "seen": [], "failed": failed})

        # until they've failed too often, when they are given up on
        with patch.object(RapidProBackend, "pull_results_from_archives_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"before": "2026-01-01"}, done=True)
            run_task(sync_poll_archives, self.job.id)

        self.assertEqual(mock_chunk.call_args.args[1]["retry"], ["2026-03-03|daily"])

        # a chunk resuming the run carries on from its own position
        end_run(self.job, status=SyncJob.STATUS_FAILED, cursor={"before": "2026-01-01", "failed": failed})

        with patch.object(RapidProBackend, "pull_results_from_archives_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"before": "2026-01-01"}, done=True)
            run_task(sync_poll_archives, self.job.id)

        self.assertNotIn("retry", mock_chunk.call_args.args[1])

    def test_waits_for_failed_archives_to_be_retried(self):
        end_run(self.job, cursor={"before": "2026-01-01", "failed": {"2026-03-03|daily": 1}})
        self.assertFalse(_archives_walked(reload(self.job)))

        end_run(self.job, cursor={"before": "2026-01-01", "failed": {"2026-03-03|daily": ARCHIVE_ATTEMPTS}})
        self.assertTrue(_archives_walked(reload(self.job)))


class SyncPollArchivesBatchTest(PollSyncTestBase):
    def setUp(self):
        super(SyncPollArchivesBatchTest, self).setUp()

        self.poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin)
        self.mock_rebuild = self.start_patch(patch.object(Poll, "rebuild_poll_results_counts", autospec=True))

    def queue_batch(self, flow_uuids=("uuid-1", "uuid-2")):
        with patch.object(sync_poll_archives_batch, "apply_async") as mock_queue:
            job = queue_archives_batch(self.nigeria, flow_uuids, "rapidpro")

        if job:
            mock_queue.assert_called_once_with((job.id,), queue="sync")
        return job

    def flow_counts(self, **by_flow):
        return {flow_uuid: results_counts(**counts) for flow_uuid, counts in by_flow.items()}

    def rebuilt_flows(self):
        return [call[0][0].flow_uuid for call in self.mock_rebuild.call_args_list]

    def walk(self, job, *results):
        with patch.object(RapidProBackend, "pull_results_from_archives_batch_chunk") as mock_chunk:
            mock_chunk.side_effect = results
            mock_continue = run_task(sync_poll_archives_batch, job.id, times=len(results))

        return mock_chunk, mock_continue

    def test_queue_and_start_take_over_the_flows_archive_jobs(self):
        idle = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=idle.id).update(status=SyncJob.STATUS_RUNNING, cursor={"before": "2026-01-01"})
        walked = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-2")
        end_run(walked, cursor={"before": "2025-01-01"})

        job = self.queue_batch(["uuid-2", "uuid-1", "uuid-1", ""])

        self.assertEqual(job.job_type, ARCHIVES_BATCH_JOB_TYPE)
        self.assertLessEqual(len(job.scope), 64)
        self.assertEqual(job.cursor, {"flows": ["uuid-1", "uuid-2"], "backend": "rapidpro"})
        self.assertEqual(batch_owned_flows(self.nigeria.pk), {"uuid-1", "uuid-2"})
        self.assertEqual(batch_owned_flows(self.nigeria.pk, walking=True), set())

        # flows another unfinished batch owns are left to it
        self.assertIsNone(self.queue_batch(["uuid-1"]))

        # starting the walk ends the per flow traversals, which read as not walked until the batch is done
        self.walk(job, ChunkResult(counts={}, cursor={"before": "2026-07-01", "seen": ["a"]}))

        self.assertJobState(idle, status=SyncJob.STATUS_COMPLETE, cursor={})
        self.assertJobState(walked, status=SyncJob.STATUS_COMPLETE, cursor={})
        self.assertEqual(batch_owned_flows(self.nigeria.pk, walking=True), {"uuid-1", "uuid-2"})

        self.walk(job, ChunkResult(counts={}, cursor={"before": "2026-06-01", "seen": ["a", "b"]}, done=True))

        self.assertJobState(idle, cursor={"before": "2026-06-01", "seen": ["a", "b"]})
        self.assertJobState(walked, cursor={"before": "2026-06-01", "seen": ["a", "b"]})

    def test_walks_the_flows_and_rebuilds_the_ones_that_changed(self):
        job = self.queue_batch()

        chunks = [
            ChunkResult(
                counts=self.flow_counts(**{"uuid-1": dict(num_val_created=3), "uuid-2": dict(num_val_ignored=2)}),
                cursor={"before": "2026-07-01", "seen": ["2026-07-01|daily"]},
            ),
            ChunkResult(
                counts=self.flow_counts(**{"uuid-1": dict(num_path_created=1), "uuid-2": {}}),
                cursor={"before": "2026-06-01", "seen": ["2026-06-01|monthly"]},
                done=True,
            ),
        ]

        with patch.object(RapidProBackend, "pull_results_from_archives_batch_chunk") as mock_chunk:
            mock_chunk.side_effect = chunks
            chunk_count = run_to_completion(sync_poll_archives_batch, job.id)

        # two archive chunks then the rebuild stage
        self.assertEqual(chunk_count, 3)

        org, polls, cursor = mock_chunk.call_args_list[1][0]
        self.assertEqual(set(polls), {"uuid-1", "uuid-2"})
        self.assertEqual(cursor["before"], "2026-07-01")
        self.assertEqual(cursor["flows"], ["uuid-1", "uuid-2"])
        self.assertEqual(mock_chunk.call_args_list[1][1]["on_save"].__self__.id, job.id)

        # only the flow whose results changed is marked and rebuilt
        self.assertEqual(self.rebuilt_flows(), ["uuid-1"])
        self.assertIsNotNone(self.poll.get_counts_stamps()[0])
        self.assertIsNone(self.poll2.get_counts_stamps()[0])

        job = self.assertJobState(job, status=SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress["chunks"], 2)
        self.assertEqual(job.progress["num_val_created"], 3)
        self.assertEqual(
            job.progress["flows"],
            {"uuid-1": dict(num_val_created=3, num_path_created=1), "uuid-2": dict(num_val_ignored=2)},
        )

        # both flows are synced, and the batch no longer owns them
        self.assertEqual(
            set(Poll.objects.filter(has_synced=True).values_list("flow_uuid", flat=True)), {"uuid-1", "uuid-2"}
        )
        self.assertEqual(batch_owned_flows(self.nigeria.pk), set())

    def test_rebuild_stage_resumes_where_it_stopped(self):
        job = self.queue_batch()
        SyncJob.objects.filter(id=job.id).update(
            status=SyncJob.STATUS_RUNNING,
            started_on=timezone.now(),
            cursor={**job.cursor, "before": "2026-06-01", "stage": "rebuild", "rebuilt": ["uuid-1"]},
            progress={"flows": {"uuid-1": dict(num_val_created=1), "uuid-2": dict(num_val_updated=1)}},
        )

        with patch.object(RapidProBackend, "pull_results_from_archives_batch_chunk") as mock_chunk:
            run_task(sync_poll_archives_batch, job.id)

        mock_chunk.assert_not_called()
        self.assertEqual(self.rebuilt_flows(), ["uuid-2"])
        self.assertJobState(job, status=SyncJob.STATUS_COMPLETE)

    def test_resumes_from_the_last_archive_after_a_failure(self):
        job = self.queue_batch()

        with patch.object(RapidProBackend, "pull_results_from_archives_batch_chunk") as mock_chunk:
            mock_chunk.side_effect = [
                ChunkResult(counts=self.flow_counts(**{"uuid-1": {}}), cursor={"before": "2026-07-01", "seen": ["a"]}),
                ValueError("boom"),
            ]
            run_task(sync_poll_archives_batch, job.id)

            with patch.object(sync_poll_archives_batch, "apply_async"):
                with self.assertRaises(ValueError):
                    sync_poll_archives_batch(job.id)

            self.assertJobState(job, status=SyncJob.STATUS_FAILED)

            mock_chunk.side_effect = None
            mock_chunk.return_value = ChunkResult(counts={}, cursor={"before": "2026-06-01"}, done=True)
            run_task(sync_poll_archives_batch, job.id)

        self.assertEqual(mock_chunk.call_args[0][2]["before"], "2026-07-01")
        self.assertEqual(mock_chunk.call_args[0][2]["seen"], ["a"])

        # a failed batch still owns its flows, until it's done
        self.assertEqual(batch_owned_flows(self.nigeria.pk), {"uuid-1", "uuid-2"})

    def test_waits_for_a_per_flow_chunk_it_took_over(self):
        busy = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-2")
        SyncJob.objects.filter(id=busy.id).update(status=SyncJob.STATUS_RUNNING)
        hold_lease(busy)
        job = self.queue_batch()

        with patch.object(RapidProBackend, "pull_results_from_archives_batch_chunk") as mock_chunk:
            mock_continue = run_task(sync_poll_archives_batch, job.id)

            mock_chunk.assert_not_called()
            mock_continue.assert_called_once_with((job.id,), queue="sync", countdown=ARCHIVES_BATCH_BUSY_BACKOFF)

            # once that chunk is over, the per flow job ends itself rather than write on
            drop_lease(busy)
            with patch.object(RapidProBackend, "pull_results_from_archives_chunk") as mock_flow_chunk:
                run_task(sync_poll_archives, busy.id)

            mock_flow_chunk.assert_not_called()
            self.assertJobState(busy, status=SyncJob.STATUS_COMPLETE, cursor={})
            self.assertFalse(Poll.objects.get(id=self.poll2.id).has_synced)

            mock_chunk.return_value = ChunkResult(counts={}, cursor={"before": "2026-06-01"}, done=True)
            run_task(sync_poll_archives_batch, job.id)

        mock_chunk.assert_called_once()

    def test_a_lost_lease_between_saves_drops_the_chunk(self):
        job = self.queue_batch()

        def steal_lease(org, polls, cursor, on_save=None):
            SyncJob.objects.filter(id=job.id).update(lease_owner="worker-2")
            on_save()

        with patch.object(RapidProBackend, "pull_results_from_archives_batch_chunk", side_effect=steal_lease):
            mock_continue = run_task(sync_poll_archives_batch, job.id)

        mock_continue.assert_not_called()
        self.assertJobState(
            job, cursor={"flows": ["uuid-1", "uuid-2"], "backend": "rapidpro", "walking": True}, progress={}
        )

    def test_skips_flows_that_stopped_syncing(self):
        job = self.queue_batch()
        Poll.objects.filter(flow_uuid="uuid-2").update(stopped_syncing=True)

        with patch.object(RapidProBackend, "pull_results_from_archives_batch_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts={}, cursor={"before": "2026-06-01"}, done=True)
            run_task(sync_poll_archives_batch, job.id)

        self.assertEqual(set(mock_chunk.call_args[0][1]), {"uuid-1"})

        Poll.objects.filter(flow_uuid="uuid-1").update(stopped_syncing=True)
        other = self.queue_batch(["uuid-3"])
        poll3 = self.create_poll(self.nigeria, "Poll 3", "uuid-3", self.education_nigeria, self.admin)
        Poll.objects.filter(id=poll3.id).update(stopped_syncing=True)
        run_task(sync_poll_archives_batch, other.id)
        self.assertJobState(other, status=SyncJob.STATUS_COMPLETE)

    def test_dispatch_leaves_owned_flows_to_the_batch(self):
        now = timezone.now()
        owned = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")
        job = self.queue_batch(["uuid-1"])
        end_run(owned, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(hours=2), failures=1)
        unowned = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-2")
        end_run(unowned, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(hours=2), failures=1)

        with (
            patch.object(sync_poll_archives, "apply_async") as mock_flow_queue,
            patch.object(sync_poll_archives_batch, "apply_async") as mock_batch_queue,
        ):
            self.assertEqual(set(dispatch_archives(self.nigeria)), {job.scope, "uuid-2"})

        mock_flow_queue.assert_called_once_with((unowned.id,), queue="sync")
        mock_batch_queue.assert_called_once_with((job.id,), queue="sync")

    def test_flows_of_a_leased_batch_are_syncing(self):
        job = self.queue_batch(["uuid-1"])
        self.assertFalse(is_flow_syncing(self.nigeria.pk, "uuid-1"))

        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_RUNNING)
        hold_lease(job)

        self.assertTrue(is_flow_syncing(self.nigeria.pk, "uuid-1"))
        self.assertFalse(is_flow_syncing(self.nigeria.pk, "uuid-2"))
        self.assertFalse(is_flow_syncing(self.uganda.pk, "uuid-1"))

    def test_results_delete_waits_for_the_batch(self):
        PollResult.objects.create(
            org=self.nigeria,
            flow="uuid-1",
            ruleset="ruleset-uuid",
            contact="contact-uuid",
            date=timezone.now(),
            completed=False,
        )
        job = self.queue_batch(["uuid-1"])
        self.walk(job, ChunkResult(counts={}, cursor={"before": "2026-07-01"}))
        results_job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=results_job.id).update(cursor={"after": "t1"})
        flag = Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk)
        cache.set(flag, "2026-08-01", None)

        with (
            patch.object(Poll, "get_flow_date", return_value=None),
            patch.object(sync_poll_archives, "apply_async") as mock_archives_queue,
            patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk,
        ):
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t2"}, done=True)
            run_task(sync_poll_results, results_job.id)

            # nothing is deleted under the batch, and the request is kept for later
            self.assertEqual(mock_chunk.call_args[0][1], {"after": "t1"})
            self.assertTrue(PollResult.objects.filter(flow="uuid-1").exists())
            self.assertIsNotNone(cache.get(flag))

            # the first sync's archives job ends itself, the batch has them
            archives_job = self.get_job(ARCHIVES_JOB_TYPE)
            run_task(sync_poll_archives, archives_job.id)
            self.assertJobState(archives_job, status=SyncJob.STATUS_COMPLETE)

            end_run(job)
            mock_archives_queue.reset_mock()
            run_task(sync_poll_results, results_job.id)

        # once the batch is done the delete goes ahead and the archives are walked again
        self.assertEqual(mock_chunk.call_args[0][1], {})
        self.assertFalse(PollResult.objects.filter(flow="uuid-1").exists())
        self.assertIsNone(cache.get(flag))
        mock_archives_queue.assert_called_once_with((archives_job.id,), queue="sync")

    def test_pending_archives_reset_waits_for_the_batch(self):
        job = self.queue_batch(["uuid-1"])
        self.walk(job, ChunkResult(counts={}, cursor={"before": "2026-07-01"}))
        results_job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=results_job.id).update(
            status=SyncJob.STATUS_RUNNING, progress={"archives_reset_pending": 1}, cursor={"after": "t1"}
        )

        with (
            patch.object(sync_poll_archives, "apply_async") as mock_archives_queue,
            patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk,
        ):
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t2"})
            run_task(sync_poll_results, results_job.id)

        mock_archives_queue.assert_not_called()
        self.assertEqual(self.get_job().progress["archives_reset_pending"], 1)

    def test_walks_the_archives_of_a_full_repull_after_its_delete(self):
        PollResult.objects.create(
            org=self.nigeria,
            flow="uuid-1",
            ruleset="ruleset-uuid",
            contact="contact-uuid",
            date=timezone.now(),
            completed=False,
        )
        self.poll.request_full_repull()
        job = self.queue_batch(["uuid-1"])
        results_job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")

        # the batch waits for the flow's results sync to delete its results
        mock_chunk, mock_continue = self.walk(job, ChunkResult(counts={}, cursor={}))
        mock_chunk.assert_not_called()
        mock_continue.assert_called_once_with((job.id,), queue="sync", countdown=ARCHIVES_BATCH_BUSY_BACKOFF)

        with (
            patch.object(sync_poll_archives, "apply_async") as mock_archives_queue,
            patch.object(RapidProBackend, "pull_results_chunk") as mock_results_chunk,
        ):
            mock_results_chunk.return_value = ChunkResult(
                counts=results_counts(num_val_created=1), cursor={"after": "t1"}, done=True
            )
            run_to_completion(sync_poll_results, results_job.id)

        # the delete goes ahead, and the archives are left to the batch rather than walked by the flow's own job
        self.assertFalse(PollResult.objects.filter(flow="uuid-1").exists())
        mock_archives_queue.assert_not_called()
        self.assertJobState(self.get_job(ARCHIVES_JOB_TYPE), cursor={})

        # so the re-pull isn't over, and its counts wait for it
        self.assertTrue(cache.get(FULL_REPULL_KEY % (self.nigeria.pk, "uuid-1")))
        self.mock_rebuild.assert_not_called()

        with patch.object(RapidProBackend, "pull_results_from_archives_batch_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(
                counts=self.flow_counts(**{"uuid-1": {}}), cursor={"before": "2026-06-01"}, done=True
            )
            run_to_completion(sync_poll_archives_batch, job.id)

        # the end of the batch ends it, and rebuilds the counts on everything pulled again
        self.assertIsNone(cache.get(FULL_REPULL_KEY % (self.nigeria.pk, "uuid-1")))
        self.assertEqual(self.rebuilt_flows(), ["uuid-1"])
        self.assertJobState(self.get_job(ARCHIVES_JOB_TYPE), cursor={"before": "2026-06-01"})

    def test_a_flow_is_only_retired_once_its_batch_is_done(self):
        long_ago = timezone.now() - timedelta(days=500)
        Poll.objects.filter(id=self.poll.id).update(poll_date=long_ago, created_on=long_ago)
        cache.set(RETIRE_KEY % (self.nigeria.pk, "uuid-1"), timezone.now(), None)
        job = self.queue_batch(["uuid-1"])
        results_job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")

        self.assertEqual(_retire_flow(self.nigeria, "uuid-1", results_job), PRUNE_SKIPPED_PULLING)

        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_RUNNING)
        hold_lease(job)
        self.assertNotEqual(_retire_flow(self.nigeria, "uuid-1"), PRUNE_RETIRED)
        self.assertFalse(Poll.objects.get(id=self.poll.id).stopped_syncing)

        end_run(job)
        self.assertEqual(_retire_flow(self.nigeria, "uuid-1", results_job), PRUNE_RETIRED)

    def test_hands_the_archives_it_failed_to_pull_to_each_flow(self):
        job = self.queue_batch()
        failed = {"2026-06-01|monthly": 1}

        self.walk(job, ChunkResult(counts={}, cursor={"before": "2026-06-01", "failed": failed}, done=True))

        # each flow's own walk is done but for that archive, which it tries again once the wait is over
        for flow_uuid in ("uuid-1", "uuid-2"):
            archives_job = self.get_job(ARCHIVES_JOB_TYPE, flow_uuid=flow_uuid)
            self.assertJobState(archives_job, status=SyncJob.STATUS_COMPLETE)
            self.assertEqual(archives_job.cursor["failed"], failed)
            self.assertFalse(_archives_walked(archives_job))

        end_run(job)
        SyncJob.objects.filter(job_type=ARCHIVES_JOB_TYPE).update(ended_on=timezone.now() - timedelta(hours=2))

        with patch.object(sync_poll_archives, "apply_async"):
            self.assertEqual(set(dispatch_archives(self.nigeria)), {"uuid-1", "uuid-2"})

    def test_full_repulls_queue_a_batch_per_org(self):
        uganda_poll = self.create_poll(self.uganda, "Uganda poll", "uuid-ug", self.education_nigeria, self.admin)
        retired = self.create_poll(self.nigeria, "Retired", "uuid-retired", self.education_nigeria, self.admin)
        Poll.objects.filter(id=retired.id).update(stopped_syncing=True)

        with (
            patch.object(sync_poll_archives_batch, "apply_async") as mock_queue,
            patch.object(Poll, "pull_poll_results_task") as mock_pull,
        ):
            jobs = queue_full_repulls([self.poll, self.poll2, retired, uganda_poll])

        self.assertEqual(mock_queue.call_count, 2)
        self.assertEqual(mock_pull.call_count, 4)
        self.assertEqual(
            {(job.org_id, tuple(job.cursor["flows"])) for job in jobs},
            {(self.nigeria.pk, ("uuid-1", "uuid-2", "uuid-retired")), (self.uganda.pk, ("uuid-ug",))},
        )

        # each flow is asked to delete and pull its results again, a retired one syncing again
        for poll in (self.poll, self.poll2, retired, uganda_poll):
            flag = Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (poll.org_id, poll.pk)
            self.assertIsNotNone(cache.get(flag))
        self.assertFalse(Poll.objects.get(id=retired.id).stopped_syncing)


class DispatchTest(PollSyncTestBase):
    def setUp(self):
        super(DispatchTest, self).setUp()

        self.main_poll = self.create_poll(
            self.nigeria, "Main poll", "uuid-main", self.education_nigeria, self.admin, has_synced=True
        )
        self.other_poll = self.create_poll(
            self.nigeria, "Other poll", "uuid-other", self.education_nigeria, self.admin, has_synced=True
        )
        Poll.objects.filter(id=self.other_poll.id).update(created_on=timezone.now() - timedelta(days=60))

    def queued_flows(self, mock_queue):
        job_ids = [call[0][0][0] for call in mock_queue.call_args_list]
        return set(SyncJob.objects.filter(id__in=job_ids).values_list("scope", flat=True))

    def dispatch(self):
        with (
            patch.object(sync_poll_results, "apply_async") as mock_queue,
            patch.object(Poll, "get_main_poll") as mock_main_poll,
            patch.object(Poll, "get_recent_polls") as mock_recent_polls,
            patch.object(Poll, "get_other_polls") as mock_other_polls,
        ):
            mock_main_poll.return_value = self.main_poll
            mock_recent_polls.return_value = Poll.objects.none()
            mock_other_polls.return_value = Poll.objects.filter(id=self.other_poll.id)

            dispatch_org_polls(self.nigeria)

        return self.queued_flows(mock_queue)

    def test_queues_unsynced_polls_every_pass(self):
        # the unsynced poll is queued even though its job just completed
        end_run(SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1"))

        self.assertIn("uuid-1", self.dispatch())

    def complete_runs(self, started_on, ended_on):
        """
        Leaves every results job of the org as a run that started and ended when given.
        """
        SyncJob.objects.filter(org=self.nigeria, job_type=RESULTS_JOB_TYPE).update(
            status=SyncJob.STATUS_COMPLETE, started_on=started_on, ended_on=ended_on
        )

    def test_respects_cadence_of_completed_jobs(self):
        now = timezone.now()
        self.assertEqual(self.dispatch(), {"uuid-1", "uuid-main", "uuid-other"})

        self.complete_runs(now - timedelta(minutes=11), now - timedelta(minutes=10))
        self.assertEqual(self.dispatch(), {"uuid-1"})

        # the main poll is due again after twenty minutes, the other poll only after a day
        self.complete_runs(now - timedelta(minutes=31), now - timedelta(minutes=30))
        self.assertEqual(self.dispatch(), {"uuid-1", "uuid-main"})

        self.complete_runs(now - timedelta(days=2), now - timedelta(days=2))
        self.assertEqual(self.dispatch(), {"uuid-1", "uuid-main", "uuid-other"})

    def test_cadence_is_spent_by_a_long_run(self):
        # the cadence is how often a run should start, so a run that takes longer than it
        # leaves the next one due as soon as it ends rather than a whole cadence later
        now = timezone.now()
        self.dispatch()  # the jobs the cadence applies to exist once their flows are dispatched

        self.complete_runs(now - timedelta(hours=3), now - timedelta(minutes=1))

        self.assertEqual(self.dispatch(), {"uuid-1", "uuid-main"})

        # the daily cadence hasn't been spent by three hours, so the other poll waits
        self.complete_runs(now - timedelta(days=2), now - timedelta(minutes=1))
        self.assertEqual(self.dispatch(), {"uuid-1", "uuid-main", "uuid-other"})

    def test_failure_backoff_never_outpaces_the_cadence(self):
        # a job that fails after a run long enough to spend its cadence is held back by the
        # backoff alone, which must not retry it faster than it would run when healthy
        now = timezone.now()
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-other")
        end_run(
            job,
            status=SyncJob.STATUS_FAILED,
            started_on=now - timedelta(days=3),
            ended_on=now - timedelta(hours=2),
            failures=1,
        )

        self.assertNotIn("uuid-other", self.dispatch())

        # and once its own cadence is up, it is retried
        end_run(
            job,
            status=SyncJob.STATUS_FAILED,
            started_on=now - timedelta(days=3),
            ended_on=now - timedelta(days=2),
            failures=1,
        )

        self.assertIn("uuid-other", self.dispatch())

    def test_nudges_a_run_that_never_ended(self):
        # a chain that died without recording a failure left no end to schedule the next run
        # from, so it is nudged as soon as it stops checkpointing, whatever its cadence
        now = timezone.now()
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-other")
        SyncJob.objects.filter(id=job.id).update(
            status=SyncJob.STATUS_RUNNING, started_on=now - timedelta(minutes=5), ended_on=None
        )
        make_stale(job, seconds_ago=3 * 60 * 60)

        self.assertIn("uuid-other", self.dispatch())

    def test_skips_jobs_under_a_live_lease(self):
        hold_lease(SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1"))

        self.assertNotIn("uuid-1", self.dispatch())

    def test_skips_a_run_between_chunks(self):
        # chunks release the lease between continuations, so a moving run looks idle here
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_RUNNING, modified_on=timezone.now())

        self.assertNotIn("uuid-1", self.dispatch())

        # but a run that stopped checkpointing is picked back up - the recovery nudge for a
        # chain that died without recording a failure
        make_stale(job, seconds_ago=3 * 60 * 60)

        self.assertIn("uuid-1", self.dispatch())

    def test_backs_off_failing_jobs(self):
        now = timezone.now()
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")

        # a failed job is not retried at the dispatcher's rate, even at the always-due cadence
        end_run(job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(minutes=5), failures=1)
        self.assertNotIn("uuid-1", self.dispatch())

        end_run(job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(minutes=25), failures=1)
        self.assertIn("uuid-1", self.dispatch())

        # and the streak stretches the wait
        end_run(job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(minutes=25), failures=3)
        self.assertNotIn("uuid-1", self.dispatch())

        end_run(job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(hours=3), failures=3)
        self.assertIn("uuid-1", self.dispatch())

    def test_never_queues_paused_jobs(self):
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_PAUSED)

        self.assertNotIn("uuid-1", self.dispatch())

    def test_nudges_unfinished_archive_traversals(self):
        now = timezone.now()
        failed = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")
        end_run(failed, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(hours=2), failures=1)
        done = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-main")
        end_run(done, ended_on=now)
        paused = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-other")
        SyncJob.objects.filter(id=paused.id).update(status=SyncJob.STATUS_PAUSED)

        with (
            patch.object(sync_poll_results, "apply_async"),
            patch.object(sync_poll_archives, "apply_async") as mock_queue,
            patch.object(Poll, "get_main_poll") as mock_main_poll,
            patch.object(Poll, "get_recent_polls") as mock_recent_polls,
            patch.object(Poll, "get_other_polls") as mock_other_polls,
        ):
            mock_main_poll.return_value = self.main_poll
            mock_recent_polls.return_value = Poll.objects.none()
            mock_other_polls.return_value = Poll.objects.none()

            dispatch_org_polls(self.nigeria)

        mock_queue.assert_called_once_with((failed.id,), queue="sync")

    def test_nudges_walks_with_archives_to_retry_after_a_wait(self):
        now = timezone.now()
        job = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")

        def nudged(failures, hours_ago):
            end_run(job, ended_on=now - timedelta(hours=hours_ago), cursor={"before": "2026-01-01", "failed": failures})

            with patch.object(sync_poll_archives, "apply_async") as mock_queue:
                dispatch_archives(self.nigeria)

            return mock_queue.called

        # the wait doubles with each failure
        self.assertFalse(nudged({"2026-03-03|daily": 1}, 0.5))
        self.assertTrue(nudged({"2026-03-03|daily": 1}, 1.5))
        self.assertFalse(nudged({"2026-03-03|daily": 3}, 3.5))
        self.assertTrue(nudged({"2026-03-03|daily": 3}, 4.5))

        # until it is given up on
        self.assertFalse(nudged({"2026-03-03|daily": ARCHIVE_ATTEMPTS}, 100))

    def test_skips_polls_created_within_the_last_week(self):
        Poll.objects.filter(id=self.other_poll.id).update(created_on=timezone.now() - timedelta(days=2))

        self.assertNotIn("uuid-other", self.dispatch())

    def test_beat_task_covers_active_orgs(self):
        with (
            patch.object(sync_poll_results, "apply_async") as mock_queue,
            patch.object(Poll, "get_main_poll") as mock_main_poll,
        ):
            mock_main_poll.return_value = None

            sync_polls_dispatch()

        # the real poll querysets place each flow in a cadence
        self.assertEqual(self.queued_flows(mock_queue), {"uuid-1", "uuid-main", "uuid-other"})

    def test_beat_task_survives_a_failing_org(self):
        with (
            patch.object(sync_poll_results, "apply_async") as mock_queue,
            patch.object(Poll, "get_main_poll") as mock_main_poll,
        ):
            mock_main_poll.side_effect = ValueError("boom")

            sync_polls_dispatch()

        mock_queue.assert_called()


class TaskShimTest(PollSyncTestBase):
    def test_pull_refresh_queues_results_job(self):
        with patch.object(sync_poll_results, "apply_async") as mock_queue:
            pull_refresh(self.poll.pk)

        job = self.get_job()
        mock_queue.assert_called_once_with((job.id,), queue="sync")

    def test_pull_refresh_from_archives_restarts_the_traversal(self):
        job = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")
        end_run(job, cursor={"before": "2026-01-01"})

        with patch.object(sync_poll_archives, "apply_async") as mock_queue:
            pull_refresh_from_archives(self.poll.pk)

        # its only caller is a re-pull after a delete, which has to start over
        mock_queue.assert_called_once_with((job.id,), queue="sync")
        self.assertEqual(self.get_job(ARCHIVES_JOB_TYPE).cursor, {})

    def test_pull_refresh_ignores_missing_poll(self):
        with patch.object(sync_poll_results, "apply_async") as mock_queue:
            pull_refresh(-1)
            pull_refresh_from_archives(-1)

        mock_queue.assert_not_called()

    def test_org_tasks_queue_jobs(self):
        main_poll = self.create_poll(
            self.nigeria, "Main poll", "uuid-main", self.education_nigeria, self.admin, has_synced=True
        )

        with (
            patch.object(sync_poll_results, "apply_async") as mock_queue,
            patch.object(Poll, "get_main_poll") as mock_main_poll,
            patch.object(Poll, "get_recent_polls") as mock_recent_polls,
            patch.object(Poll, "get_other_polls") as mock_other_polls,
        ):
            mock_main_poll.return_value = main_poll
            mock_recent_polls.return_value = Poll.objects.filter(id=main_poll.id)
            mock_other_polls.return_value = Poll.objects.none()

            backfill_poll_results(self.nigeria.pk)
            self.assertEqual(mock_queue.call_count, 1)
            self.assertEqual(self.get_job().status, SyncJob.STATUS_PENDING)

            mock_queue.reset_mock()
            pull_results_main_poll(self.nigeria.pk)
            pull_results_recent_polls(self.nigeria.pk)
            pull_results_other_polls(self.nigeria.pk)

        main_job = self.get_job(flow_uuid="uuid-main")
        self.assertEqual([call[0][0] for call in mock_queue.call_args_list], [(main_job.id,), (main_job.id,)])

        # they only enqueue now, so they must not pass themselves off as having synced
        self.assertFalse(TaskState.objects.filter(org=self.nigeria).exists())


class RebuildPollCountsTest(PollSyncTestBase):
    def setUp(self):
        super(RebuildPollCountsTest, self).setUp()

        self.health_uganda = Category.objects.create(
            org=self.uganda, name="Health", created_by=self.admin, modified_by=self.admin
        )

        self.polls = [self.poll]
        for index in range(2, 7):
            self.polls.append(
                self.create_poll(self.nigeria, "Poll %d" % index, "uuid-%d" % index, self.education_nigeria, self.admin)
            )

        # the counts rebuild is one install wide job, so another org's polls are in its walk
        self.polls.append(self.create_poll(self.uganda, "Poll UG", "uuid-ug", self.health_uganda, self.admin))

        self.job = SyncJob.get_or_create_job(None, COUNTS_JOB_TYPE)

    def rebuild(self):
        with patch.object(Poll, "rebuild_poll_results_counts", autospec=True) as mock_rebuild:
            mock_continue = run_task(rebuild_poll_counts, self.job.id)

        return [call[0][0].pk for call in mock_rebuild.call_args_list], mock_continue

    def test_walks_every_poll_a_chunk_at_a_time(self):
        self.assertIsNone(self.job.org_id)

        rebuilt, mock_continue = self.rebuild()

        self.assertEqual(rebuilt, [poll.pk for poll in self.polls[:5]])
        mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=None)

        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_RUNNING,
            cursor={"after_pk": self.polls[4].pk},
            progress={"rebuilt": 5},
        )

        # the continuation picks up from the checkpointed position
        rebuilt, mock_continue = self.rebuild()

        self.assertEqual(rebuilt, [poll.pk for poll in self.polls[5:]])
        mock_continue.assert_called_once()

        # and the run ends once the polls are exhausted
        rebuilt, mock_continue = self.rebuild()

        self.assertEqual(rebuilt, [])
        mock_continue.assert_not_called()
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, progress={"rebuilt": 7})

    def test_skips_polls_with_nothing_to_count(self):
        Poll.objects.filter(id=self.polls[1].id).update(stopped_syncing=True)
        Poll.objects.filter(id=self.polls[2].id).update(is_active=False)

        rebuilt, _ = self.rebuild()

        self.assertEqual(rebuilt, [self.polls[index].pk for index in (0, 3, 4, 5, 6)])

    def test_resumes_where_a_killed_chunk_stopped(self):
        with (
            patch.object(rebuild_poll_counts, "apply_async"),
            patch.object(Poll, "rebuild_poll_results_counts", autospec=True) as mock_rebuild,
        ):
            mock_rebuild.side_effect = [None, None, ValueError("worker died")]

            with self.assertRaises(ValueError):
                rebuild_poll_counts(self.job.id)

        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_FAILED,
            cursor={"after_pk": self.polls[1].pk},
            progress={"rebuilt": 2},
        )

        # the retry resumes the interrupted run rather than rebuilding those two again
        rebuilt, _ = self.rebuild()

        self.assertEqual(rebuilt, [poll.pk for poll in self.polls[2:]])
        self.assertJobState(self.job, progress={"rebuilt": 7})

    def completed_run(self):
        """
        Leaves the job as a run that covered every poll a day ago, i.e. the state a new run
        of it has to recognise as one it must not resume below.
        """
        return end_run(
            self.job,
            cursor={"after_pk": self.polls[-1].pk},
            progress={"rebuilt": 7},
            ended_on=timezone.now() - timedelta(days=1),
        )

    def test_a_new_run_starts_from_the_first_poll(self):
        # a completed run leaves its position behind, and resuming below it would walk nothing
        self.completed_run()

        rebuilt, _ = self.rebuild()

        self.assertEqual(rebuilt, [poll.pk for poll in self.polls[:5]])
        self.assertJobState(self.job, progress={"rebuilt": 5})

    def test_a_new_run_that_fails_before_its_first_checkpoint_still_starts_over(self):
        self.completed_run()

        with (
            patch.object(rebuild_poll_counts, "apply_async"),
            patch.object(Poll, "rebuild_poll_results_counts", autospec=True) as mock_rebuild,
        ):
            mock_rebuild.side_effect = ValueError("worker died")

            with self.assertRaises(ValueError):
                rebuild_poll_counts(self.job.id)

        # the run dropped the completed one's position before touching a poll, so the stale
        # position can't survive a chunk that fails before checkpointing anything itself
        self.assertJobState(self.job, status=SyncJob.STATUS_FAILED, cursor={})

        # and the retry, which resumes that run rather than starting one, still walks it all
        rebuilt, _ = self.rebuild()

        self.assertEqual(rebuilt, [poll.pk for poll in self.polls[:5]])

    def test_a_lost_lease_leaves_the_polls_already_done_checkpointed(self):
        def steal(poll):
            if poll.pk == self.polls[1].pk:
                SyncJob.objects.filter(id=self.job.id).update(lease_owner="worker-2")

        with patch.object(Poll, "rebuild_poll_results_counts", autospec=True) as mock_rebuild:
            mock_rebuild.side_effect = steal

            mock_continue = run_task(rebuild_poll_counts, self.job.id)

        # the chunk is dropped where it lost the lease, but the poll it had already
        # checkpointed is not walked again by whoever took over
        self.assertJobState(self.job, status=SyncJob.STATUS_RUNNING, cursor={"after_pk": self.polls[0].pk})
        mock_continue.assert_not_called()

    def set_rebuilt(self, polls, ago, changed_ago=None):
        now = timezone.now()
        for poll in polls:
            poll._mark_counts_rebuilt(now - ago)
            if changed_ago:
                cache.set(Poll.POLL_RESULTS_CHANGED_CACHE_KEY % (poll.org_id, poll.flow_uuid), now - changed_ago, None)

    def full_rebuild_poll(self):
        # the polls have consecutive pks, so exactly one of every seven has tonight as its full rebuild night
        night = timezone.now().date().toordinal() % COUNTS_FULL_REBUILD_DAYS
        return next(poll for poll in self.polls if poll.pk % COUNTS_FULL_REBUILD_DAYS == night)

    def test_skips_polls_whose_counts_are_up_to_date(self):
        self.set_rebuilt(self.polls, timedelta(hours=1), changed_ago=timedelta(hours=2))

        rebuilt, mock_continue = self.rebuild()

        # the chunk still moves the position past the polls it looked at
        self.assertEqual(rebuilt, [])
        mock_continue.assert_called_once()
        self.assertJobState(
            self.job, status=SyncJob.STATUS_RUNNING, cursor={"after_pk": self.polls[-1].pk}, progress={"skipped": 7}
        )

        rebuilt, mock_continue = self.rebuild()

        self.assertEqual(rebuilt, [])
        mock_continue.assert_not_called()
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, progress={"skipped": 7})

    def test_rebuilds_polls_whose_results_changed_or_were_never_counted(self):
        self.set_rebuilt(self.polls, timedelta(hours=3), changed_ago=timedelta(hours=4))

        # results changed after the last rebuild started, including while it ran
        self.set_rebuilt([self.polls[1]], timedelta(hours=3), changed_ago=timedelta(hours=2))
        self.set_rebuilt([self.polls[6]], timedelta(hours=3), changed_ago=timedelta(minutes=1))
        cache.delete(Poll.POLL_COUNTS_REBUILT_CACHE_KEY % (self.polls[4].org_id, self.polls[4].flow_uuid))

        # and tonight's full rebuild poll was rebuilt too recently to be rebuilt again
        rebuilt, _ = self.rebuild()

        self.assertEqual(rebuilt, [self.polls[index].pk for index in (1, 4, 6)])
        self.assertJobState(self.job, progress={"rebuilt": 3, "skipped": 4})

    def test_rebuilds_unchanged_polls_on_their_full_rebuild_night(self):
        self.set_rebuilt(self.polls, timedelta(days=2))

        rebuilt, _ = self.rebuild()

        self.assertEqual(rebuilt, [self.full_rebuild_poll().pk])

        # unless something else already rebuilt it since the last pass
        self.set_rebuilt([self.full_rebuild_poll()], timedelta(hours=1))
        self.job = end_run(self.job, ended_on=timezone.now() - timedelta(days=1))

        rebuilt, _ = self.rebuild()

        self.assertEqual(rebuilt, [])

    def test_skips_a_poll_whose_flow_was_rebuilt_earlier_in_the_chunk(self):
        # a duplicate poll of the first poll's flow, whose counts the first poll's rebuild rebuilds too
        Poll.objects.filter(id=self.polls[2].id).update(flow_uuid=self.polls[0].flow_uuid)

        with patch.object(Poll, "rebuild_poll_results_counts", autospec=True) as mock_rebuild:
            mock_rebuild.side_effect = lambda poll: poll._mark_counts_rebuilt(timezone.now())

            run_task(rebuild_poll_counts, self.job.id)

        rebuilt = [call[0][0].pk for call in mock_rebuild.call_args_list]
        self.assertEqual(rebuilt, [self.polls[index].pk for index in (0, 1, 3, 4, 5)])
        self.assertJobState(self.job, cursor={"after_pk": self.polls[5].pk}, progress={"rebuilt": 5, "skipped": 1})

    def test_only_one_global_job_can_exist(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SyncJob.objects.create(org=None, job_type=COUNTS_JOB_TYPE, scope="")


class PrunePollResultsTest(PollSyncTestBase):
    def setUp(self):
        super(PrunePollResultsTest, self).setUp()

        # a duplicate poll on the same flow, and two polls of their own
        self.dupe = self.create_poll(self.nigeria, "Poll 1 again", "uuid-1", self.education_nigeria, self.admin)
        self.second = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin)
        self.third = self.create_poll(self.nigeria, "Poll 3", "uuid-3", self.education_nigeria, self.admin)

        self.old_polls = [self.poll, self.dupe, self.second, self.third]

        self.long_ago = timezone.now() - timedelta(days=500)
        Poll.objects.filter(id__in=[poll.id for poll in self.old_polls]).update(
            poll_date=self.long_ago, created_on=self.long_ago
        )

        self.job = SyncJob.get_or_create_job(self.nigeria, PRUNE_JOB_TYPE)

        self.mock_queue_results = self.start_patch(patch.object(sync_poll_results, "apply_async"))
        self.start_patch(patch.object(sync_poll_archives, "apply_async"))

    def results_job(self, flow_uuid="uuid-1"):
        return SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, flow_uuid)

    def archives_job(self, flow_uuid="uuid-1"):
        return SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, flow_uuid)

    def add_result(self, flow_uuid="uuid-1", contact="contact-1"):
        PollResult.objects.create(
            org=self.nigeria,
            flow=flow_uuid,
            ruleset="ruleset-uuid",
            contact=contact,
            date=timezone.now(),
            completed=False,
        )

    def results(self, flow_uuid="uuid-1"):
        return PollResult.objects.filter(org=self.nigeria, flow=flow_uuid).count()

    def prune(self, rebuilt=True):
        with patch.object(Poll, "rebuild_poll_results_counts", return_value=rebuilt):
            return run_task(prune_poll_results, self.job.id)

    def finish_sync(self, flow_uuid="uuid-1", job=None, rebuilt=True):
        """
        Ends a run of the flow's results sync, or of the given job of it
        """
        job = reload(job or self.results_job(flow_uuid))
        finalize = _finalize_archives if job.job_type == ARCHIVES_JOB_TYPE else _finalize_results

        with patch.object(Poll, "rebuild_poll_results_counts", autospec=True, return_value=rebuilt) as mock_rebuild:
            finalize(job)

        return mock_rebuild

    def requested(self, flow_uuid="uuid-1"):
        return cache.get(RETIRE_KEY % (self.nigeria.pk, flow_uuid))

    def stopped(self):
        return set(Poll.objects.filter(stopped_syncing=True).values_list("pk", flat=True))

    def test_asks_each_flow_to_retire_by_the_end_of_its_next_sync(self):
        mock_continue = self.prune()

        # the first two polls share a flow, which is only asked once
        mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=None)
        self.assertJobState(
            self.job, cursor={"after_pk": self.second.pk}, progress={"requested": 2, "skipped_pulling": 1}
        )
        self.assertTrue(self.requested("uuid-1"))
        self.assertTrue(self.requested("uuid-2"))
        self.assertEqual(self.mock_queue_results.call_count, 3)

        # nothing is retired or deleted yet
        self.assertEqual(self.stopped(), set())

        self.prune()
        self.assertTrue(self.requested("uuid-3"))

        mock_continue = self.prune()
        mock_continue.assert_not_called()
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)

    def test_retires_a_flow_by_the_end_of_its_sync_and_deletes_its_results_later(self):
        Poll.objects.filter(id=self.dupe.id).update(created_on=self.long_ago + timedelta(days=1))
        self.add_result()
        self.prune()

        mock_rebuild = self.finish_sync("uuid-1")

        # retired before the counts are rebuilt for the last time, on the results it has, as of
        # the poll the flow last synced for
        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})
        self.assertEqual(len(mock_rebuild.call_args_list), 1)
        self.assertEqual(mock_rebuild.call_args.args[0].pk, self.dupe.pk)
        self.assertEqual(mock_rebuild.call_args.kwargs, {"retiring": True})
        self.assertIsNone(self.requested("uuid-1"))
        self.assertEqual(self.results(), 1)

        # and its polls are marked synced, as a retired poll is never synced again to mark them
        self.assertFalse(Poll.objects.filter(flow_uuid="uuid-1", has_synced=False).exists())

        # a sync of another flow, or one nothing asked to retire, carries on as it was
        self.finish_sync("uuid-3")
        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})

        # the next run deletes the results, without rebuilding the counts from them again
        self.prune()
        self.prune()

        with patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild:
            run_task(prune_poll_results, self.job.id)

        mock_rebuild.assert_not_called()
        self.assertEqual(self.results(), 0)
        self.assertEqual(reload(self.job).progress, {"cleared": 1, "skipped_retired": 1, "skipped_pulling": 1})

    def test_leaves_recent_polls_alone(self):
        # results are kept for a year from the poll's date
        Poll.objects.filter(id=self.poll.id).update(poll_date=timezone.now() - timedelta(days=366))
        Poll.objects.filter(id=self.second.id).update(poll_date=timezone.now() - timedelta(days=364))
        # and a new poll's date defaults to its flow's, so it is synced for 30 days from its creation
        Poll.objects.filter(id=self.third.id).update(created_on=timezone.now() - timedelta(days=29))
        Poll.objects.filter(id=self.dupe.id).update(created_on=timezone.now() - timedelta(days=31))

        self.prune()
        self.prune()

        self.assertTrue(self.requested("uuid-1"))
        self.assertIsNone(self.requested("uuid-2"))
        self.assertIsNone(self.requested("uuid-3"))

    def test_leaves_the_main_poll_alone(self):
        with patch.object(Poll, "get_main_poll", return_value=self.second):
            self.prune()
            self.prune()

            self.assertIsNone(self.requested("uuid-2"))

            # nor is it retired by a sync asked to retire it before it became the main poll
            cache.set(RETIRE_KEY % (self.nigeria.pk, "uuid-2"), timezone.now(), None)
            self.finish_sync("uuid-2")

        self.assertNotIn(self.second.pk, self.stopped())
        self.assertIsNone(self.requested("uuid-2"))

    def test_leaves_a_flow_shared_with_a_recent_poll_alone(self):
        recent = self.create_poll(self.nigeria, "Poll 1 recent", "uuid-1", self.education_nigeria, self.admin)

        # retiring the old polls of the flow would retire the recent one with them
        self.prune()
        self.prune()
        self.assertIsNone(self.requested("uuid-1"))

        # nor is it retired by a sync that was asked to retire it before the recent poll came along
        cache.set(RETIRE_KEY % (self.nigeria.pk, "uuid-1"), timezone.now(), None)
        self.finish_sync("uuid-1")

        self.assertEqual(self.stopped(), set())
        self.assertIsNone(self.requested("uuid-1"))

        # once the recent poll is old too, its flow is retired with the rest
        Poll.objects.filter(id=recent.id).update(poll_date=self.long_ago, created_on=self.long_ago)
        self.prune()
        self.finish_sync("uuid-1")

        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk, recent.pk})

    def test_steps_over_a_flow_that_is_still_syncing(self):
        job = self.results_job()
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_RUNNING)
        hold_lease(job)

        # the syncing flow is skipped, but the polls behind it in the walk are not held up
        self.prune()

        self.assertIsNone(self.requested("uuid-1"))
        self.assertTrue(self.requested("uuid-2"))
        self.assertJobState(self.job, progress={"requested": 1, "skipped_syncing": 2})

        # between chunks the sync holds no lease, but its next chunk is on the queue
        drop_lease(job)
        self.prune()
        self.prune()
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)

        self.prune()
        self.assertIsNone(self.requested("uuid-1"))

        # a sync that stopped checkpointing died, and the next run picks the flow back up
        self.prune()
        self.prune()
        make_stale(job, seconds_ago=2 * RESULTS_LEASE_SECONDS + 60)

        self.prune()
        self.assertTrue(self.requested("uuid-1"))

    def test_steps_over_a_flow_held_by_an_unchunked_pull(self):
        with held_lock(Poll.POLL_PULL_RESULTS_TASK_LOCK % (self.nigeria.pk, "uuid-1")) as lock:
            # the lock is never waited on, a chunk holding a job lease can't sit on it for hours
            self.prune()

            self.assertIsNone(self.requested("uuid-1"))
            self.assertJobState(self.job, progress={"requested": 1, "skipped_syncing": 2})

            # and it is left for whoever holds it, not released from under them
            self.assertTrue(lock.owned())

    def test_waits_for_the_flows_other_sync_to_finish(self):
        self.prune()

        # the archives of the flow are still being walked when its results sync ends
        archives = self.archives_job()
        SyncJob.objects.filter(id=archives.id).update(status=SyncJob.STATUS_RUNNING)
        hold_lease(archives)

        self.finish_sync("uuid-1")

        self.assertEqual(self.stopped(), set())
        self.assertTrue(self.requested("uuid-1"))

        # nor does the end of that walk, it is the end of the next results sync that does
        drop_lease(archives)
        SyncJob.objects.filter(id=archives.id).update(status=SyncJob.STATUS_COMPLETE, cursor={"before": "2026-01-01"})
        self.finish_sync(job=archives)

        self.assertEqual(self.stopped(), set())

        self.finish_sync("uuid-1")
        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})

    def test_retires_a_flow_by_the_end_of_a_sync_holding_its_own_lease(self):
        # an old flow has synced before, so its sync doesn't start an archives walk of its own
        Poll.objects.filter(flow_uuid="uuid-1").update(has_synced=True)
        self.prune()

        # a whole run of the sync, whose lease is held through its finalization
        with (
            patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk,
            patch.object(Poll, "rebuild_poll_results_counts", return_value=True),
        ):
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t1"}, done=True)

            run_task(sync_poll_results, self.results_job().id)

        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})
        self.assertJobState(self.results_job(), status=SyncJob.STATUS_COMPLETE, lease_owner=None)

    def test_waits_for_an_archives_walk_still_finalizing(self):
        self.prune()

        # the walk is done, but its finalization still holds the lease
        archives = self.archives_job()
        SyncJob.objects.filter(id=archives.id).update(status=SyncJob.STATUS_COMPLETE, cursor={"before": "2026-01-01"})
        hold_lease(archives)

        self.finish_sync("uuid-1")
        self.assertEqual(self.stopped(), set())

    def test_waits_for_the_flows_archives_to_be_walked(self):
        self.prune()

        # a walk sent back to the start hasn't been done yet, though its job last completed
        archives = self.archives_job()
        SyncJob.objects.filter(id=archives.id).update(status=SyncJob.STATUS_COMPLETE, cursor={})

        self.finish_sync("uuid-1")
        self.assertEqual(self.stopped(), set())

        SyncJob.objects.filter(id=archives.id).update(cursor={"before": "2026-01-01"})

        self.finish_sync("uuid-1")
        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})

    def test_rebuilds_the_counts_before_deleting_if_retiring_did_not(self):
        self.add_result()
        self.prune()

        # another rebuild of the flow held it, so the counts it was retired on may be missing results
        self.finish_sync("uuid-1", rebuilt=False)

        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})
        self.assertTrue(self.requested("uuid-1"))

        # and that is kept for however long it takes, as the results are deleted without a rebuild once it's gone
        self.assertIsNone(cache.ttl(RETIRE_KEY % (self.nigeria.pk, "uuid-1")))

        # the results are kept until a rebuild replaced all of the counts
        self.prune()
        self.prune()

        self.prune(rebuilt=False)
        self.assertEqual(self.results(), 1)
        self.assertEqual(reload(self.job).progress.get("skipped_rebuilding"), 2)

        self.prune()
        self.prune()

        with patch.object(Poll, "rebuild_poll_results_counts", autospec=True, return_value=True) as mock_rebuild:
            run_task(prune_poll_results, self.job.id)

        self.assertEqual(mock_rebuild.call_args.kwargs, {"retiring": True})
        self.assertEqual(self.results(), 0)
        self.assertIsNone(self.requested("uuid-1"))

    def test_finishes_a_delete_that_was_interrupted(self):
        # the first flow was retired on all of its counts, but its delete didn't get through all of its results
        Poll.objects.filter(flow_uuid="uuid-1").update(stopped_syncing=True)
        self.add_result(contact="contact-1")
        self.add_result(contact="contact-2")

        with patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild:
            run_task(prune_poll_results, self.job.id)

        # the leftovers are deleted without rebuilding the counts from them, and the
        # duplicate poll of the flow finds nothing left to delete
        mock_rebuild.assert_not_called()
        self.assertEqual(self.results(), 0)
        self.assertJobState(self.job, progress={"cleared": 1, "skipped_retired": 1, "requested": 1})

    def test_leaves_the_results_of_a_reused_flow_alone(self):
        # the first flow was retired long ago, and a new poll on it is syncing its results again
        Poll.objects.filter(flow_uuid="uuid-1").update(stopped_syncing=True)
        reused = self.create_poll(self.nigeria, "Poll 1 reused", "uuid-1", self.education_nigeria, self.admin)
        self.add_result()

        # the retired polls of the flow aren't walked, so the results stay with the new poll
        self.prune()
        self.prune()

        self.assertEqual(self.results(), 1)
        self.assertFalse(Poll.objects.get(id=reused.id).stopped_syncing)

        # nor is a retired poll the walk had already picked when the new poll came along
        self.assertEqual(_prune_poll(self.nigeria, self.poll, True), PRUNE_SKIPPED_RETIRED)
        self.assertEqual(self.results(), 1)

    def test_keeps_the_results_of_a_reused_flow_while_its_new_poll_is_inactive(self):
        Poll.objects.filter(flow_uuid="uuid-1").update(stopped_syncing=True)
        reused = self.create_poll(self.nigeria, "Poll 1 reused", "uuid-1", self.education_nigeria, self.admin)
        Poll.objects.filter(id=reused.id).update(is_active=False)
        self.add_result()

        # an inactive poll syncs again once reactivated, so the results stay until it is retired
        self.prune()
        self.prune()
        self.assertEqual(self.results(), 1)

        # which it is once it is old too, on the results it has, as no sync is run for it
        Poll.objects.filter(id=reused.id).update(poll_date=self.long_ago, created_on=self.long_ago)

        with patch.object(Poll, "rebuild_poll_results_counts", autospec=True, return_value=True) as mock_rebuild:
            run_to_completion(prune_poll_results, self.job.id)

        self.assertEqual(mock_rebuild.call_args.args[0].pk, reused.pk)
        self.assertEqual(mock_rebuild.call_args.kwargs, {"retiring": True})
        self.assertIn(reused.pk, self.stopped())

        run_to_completion(prune_poll_results, self.job.id)
        self.assertEqual(self.results(), 0)

    def test_retires_a_flow_without_results_on_the_counts_it_had(self):
        # its results were deleted to be pulled again by a poll that never synced
        Poll.objects.filter(flow_uuid="uuid-1").update(is_active=False)

        with patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild:
            self.prune()

        # counting nothing would only zero the counts it has
        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})
        mock_rebuild.assert_not_called()
        self.assertIsNone(self.requested("uuid-1"))

    def test_leaves_polls_without_a_flow_alone(self):
        Poll.objects.filter(id=self.third.id).update(flow_uuid="")

        run_to_completion(prune_poll_results, self.job.id)

        self.assertNotIn(self.third.pk, self.stopped())
        self.assertIsNone(self.requested(""))

    def test_retires_a_flow_whose_sync_keeps_failing(self):
        self.prune()

        job = self.results_job()
        end_run(job, status=SyncJob.STATUS_FAILED, failures=3)

        # it is waited for a while, the sync being nudged again each night
        self.mock_queue_results.reset_mock()
        self.prune()
        self.prune()
        self.prune()

        self.assertEqual(self.stopped(), set())
        self.assertTrue(self.mock_queue_results.called)

        # but not forever - the prune retires it, unless a chunk of either sync is under way
        asked_on = timezone.now() - RETIRE_FALLBACK_WAIT - timedelta(minutes=1)
        cache.set(RETIRE_KEY % (self.nigeria.pk, "uuid-1"), asked_on, None)
        archives = self.archives_job()
        SyncJob.objects.filter(id=archives.id).update(status=SyncJob.STATUS_RUNNING)
        hold_lease(archives)

        self.prune()
        self.prune()
        self.prune()
        self.assertEqual(self.stopped(), set())

        # once there is none, it is retired on what it has, its archives walked or not
        drop_lease(archives)
        make_stale(archives, seconds_ago=2 * ARCHIVES_LEASE_SECONDS + 60)

        self.prune()
        self.prune()
        self.prune()

        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})
        self.assertJobState(job, status=SyncJob.STATUS_FAILED, lease_owner=None)

    def test_retires_a_flow_failing_mid_full_repull_on_the_counts_it_had(self):
        # its results were deleted to be pulled again, and its archives walk then kept failing
        end_run(self.results_job(), status=SyncJob.STATUS_FAILED, failures=3)
        cache.set(FULL_REPULL_KEY % (self.nigeria.pk, "uuid-1"), True, None)
        asked_on = timezone.now() - RETIRE_FALLBACK_WAIT - timedelta(minutes=1)
        cache.set(RETIRE_KEY % (self.nigeria.pk, "uuid-1"), asked_on, None)

        with patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild:
            run_to_completion(prune_poll_results, self.job.id)

        # the counts left as they were before the delete have more results than a rebuild would count
        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})
        mock_rebuild.assert_not_called()
        self.assertIsNone(self.requested("uuid-1"))
        self.assertFalse(cache.get(FULL_REPULL_KEY % (self.nigeria.pk, "uuid-1")))

    def test_waits_for_a_paused_sync_however_long(self):
        self.prune()

        asked_on = timezone.now() - RETIRE_FALLBACK_WAIT - timedelta(days=10)
        cache.set(RETIRE_KEY % (self.nigeria.pk, "uuid-1"), asked_on, None)

        # whichever of the flow's syncs it is
        for job in (self.results_job(), self.archives_job()):
            job.pause()

            self.prune()
            self.prune()
            self.prune()

            self.assertEqual(self.stopped(), set())
            self.assertJobState(job, status=SyncJob.STATUS_PAUSED)

            job.resume()

    def test_retires_a_flow_whose_polls_are_all_inactive_straight_away(self):
        # no sync is run for inactive polls, so there is none to wait for
        Poll.objects.filter(flow_uuid="uuid-1").update(is_active=False)

        self.prune()

        self.assertEqual(self.stopped(), {self.poll.pk, self.dupe.pk})
        self.assertJobState(self.job, progress={"retired": 1, "skipped_retired": 1, "requested": 1})

    @patch("ureport.polls.sync.PRUNE_MAX_REQUESTS", 1)
    def test_spreads_a_backlog_of_flows_over_runs(self):
        self.prune()
        self.prune()

        self.assertTrue(self.requested("uuid-1"))
        self.assertIsNone(self.requested("uuid-2"))
        self.assertIsNone(self.requested("uuid-3"))
        self.assertJobState(self.job, progress={"requested": 1, "skipped_pulling": 1, "deferred": 2})

    def test_moves_past_a_poll_that_errors(self):
        def enqueue(job):
            if job.scope == "uuid-1":
                raise ValueError("boom")

        with patch("ureport.polls.sync.enqueue", side_effect=enqueue):
            self.prune()

        # one broken poll can't stall the polls behind it
        self.assertTrue(self.requested("uuid-2"))
        self.assertJobState(self.job, cursor={"after_pk": self.second.pk}, progress={"errors": 2, "requested": 1})


class FullRepullTest(PollSyncTestBase):
    def setUp(self):
        super(FullRepullTest, self).setUp()

        self.results_job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        self.archives_job = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")

        # the results were deleted by a run of the results sync, which is still going
        SyncJob.objects.filter(id=self.results_job.id).update(status=SyncJob.STATUS_RUNNING)
        cache.set(RETIRE_KEY % (self.nigeria.pk, "uuid-1"), timezone.now(), None)

        with patch.object(Poll, "delete_poll_results"):
            _delete_flow_results(self.results_job, self.poll)

    def set_state(self, job, **fields):
        SyncJob.objects.filter(id=job.id).update(**fields)
        return reload(job)

    def finalize(self, job):
        with patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild:
            (_finalize_archives if job.job_type == ARCHIVES_JOB_TYPE else _finalize_results)(reload(job))

        return mock_rebuild.call_count

    def test_counts_wait_for_both_halves(self):
        # a retirement asked for before is moot, as the flow is pulled again in full
        self.assertIsNone(cache.get(RETIRE_KEY % (self.nigeria.pk, "uuid-1")))

        # and the re-pull is waited for however long it takes, the counts being replaced once it's over
        self.assertIsNone(cache.ttl(FULL_REPULL_KEY % (self.nigeria.pk, "uuid-1")))

        # neither the nightly pass nor the results sync rebuilds a flow pulled again in part
        self.assertFalse(_counts_rebuild_due(self.poll, timezone.now()))

        # a flow with few archives walks them before its results are pulled again
        self.set_state(self.archives_job, status=SyncJob.STATUS_COMPLETE, cursor={"before": "2026-01-01"})
        self.assertEqual(self.finalize(self.archives_job), 0)

        # and the end of the results run ends the re-pull, rebuilding the flow on all of its results
        self.set_state(self.results_job, status=SyncJob.STATUS_COMPLETE, progress={"num_val_created": 3})
        self.assertEqual(self.finalize(self.results_job), 1)

        self.assertFalse(cache.get(FULL_REPULL_KEY % (self.nigeria.pk, "uuid-1")))
        self.assertTrue(_counts_rebuild_due(self.poll, timezone.now()))

    def test_a_walk_from_before_the_reset_does_not_end_it(self):
        # the reset was refused, so the old walk carries on while the results run waits for it
        self.set_state(self.archives_job, status=SyncJob.STATUS_COMPLETE, cursor={"before": "2026-01-01"})
        self.assertEqual(self.finalize(self.archives_job), 0)

        # the reset lands and the results run ends, but the new walk hasn't been done
        self.set_state(self.archives_job, cursor={})
        self.set_state(self.results_job, status=SyncJob.STATUS_COMPLETE, progress={"num_val_created": 3})
        self.assertEqual(self.finalize(self.results_job), 0)

        self.set_state(self.archives_job, cursor={"before": "2026-02-01"})
        self.assertEqual(self.finalize(self.archives_job), 1)
        self.assertFalse(cache.get(FULL_REPULL_KEY % (self.nigeria.pk, "uuid-1")))

    def test_a_leftover_finalization_ends_it(self):
        self.set_state(self.archives_job, status=SyncJob.STATUS_COMPLETE, cursor={"before": "2026-01-01"})
        completed = self.set_state(self.results_job, status=SyncJob.STATUS_COMPLETE, progress={"num_val_created": 3})

        # the run it finalizes ended, though the job has been claimed for a new one since
        self.set_state(self.results_job, status=SyncJob.STATUS_RUNNING)

        with patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild:
            _finalize_results(completed)

        self.assertEqual(mock_rebuild.call_count, 1)
        self.assertFalse(cache.get(FULL_REPULL_KEY % (self.nigeria.pk, "uuid-1")))

    def test_backfills_leave_the_counts_alone(self):
        with (
            patch("ureport.utils.populate_age_and_gender_for_contacts"),
            patch.object(Poll, "rebuild_poll_results_counts", autospec=True) as mock_rebuild,
        ):
            run_to_completion(backfill_age_gender, SyncJob.get_or_create_job(self.nigeria, AGE_GENDER_JOB_TYPE).id)

        self.assertNotIn(self.poll.pk, [call.args[0].pk for call in mock_rebuild.call_args_list])

    def test_results_chunks_leave_the_counts_alone(self):
        self.set_state(self.results_job, progress={"chunks": REBUILD_COUNTS_EVERY - 1})

        with (
            patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild,
            patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk,
        ):
            mock_chunk.return_value = ChunkResult(counts=results_counts(num_val_created=1), cursor={"after": "t1"})

            run_task(sync_poll_results, self.results_job.id)

        self.assertEqual(reload(self.results_job).progress["chunks"], REBUILD_COUNTS_EVERY)
        mock_rebuild.assert_not_called()


class RebuildRetiringTest(PollSyncTestBase):
    def test_reports_a_rebuild_that_did_not_run(self):
        with held_lock(Poll.POLL_REBUILD_COUNTS_LOCK % (self.nigeria.pk, "uuid-1")):
            self.assertFalse(self.poll.rebuild_poll_results_counts())

        self.assertTrue(self.poll.rebuild_poll_results_counts())

    def test_rebuilds_a_flow_being_retired(self):
        self.create_poll_question(self.admin, self.poll, "Color", "ruleset-uuid")
        Poll.objects.filter(id=self.poll.id).update(stopped_syncing=True)
        poll = Poll.objects.get(id=self.poll.id)

        with (
            patch.object(Poll, "update_question_word_clouds", autospec=True) as mock_clouds,
            patch.object(Poll, "update_questions_results_cache", autospec=True) as mock_cache,
        ):
            # a retired flow's counts are left as they are
            self.assertTrue(poll.rebuild_poll_results_counts())
            mock_clouds.assert_not_called()

            # unless it is the rebuild retiring it, which regenerates its word clouds while its results are there
            self.assertTrue(poll.rebuild_poll_results_counts(retiring=True))

        self.assertEqual([call[0][0].pk for call in mock_clouds.call_args_list], [poll.pk])
        self.assertIn(poll.pk, [call[0][0].pk for call in mock_cache.call_args_list])

    def test_refreshes_the_results_of_retired_polls_sharing_the_flow(self):
        self.create_poll_question(self.admin, self.poll, "Color", "ruleset-uuid")
        retired = self.create_poll(self.nigeria, "Poll 1 retired", "uuid-1", self.education_nigeria, self.admin)
        Poll.objects.filter(id=retired.id).update(stopped_syncing=True)

        with (
            patch.object(Poll, "update_question_word_clouds", autospec=True) as mock_clouds,
            patch.object(Poll, "update_questions_results_cache", autospec=True) as mock_cache,
        ):
            self.poll.rebuild_poll_results_counts()

        # the counts are the flow's, so the retired poll's cached results are refreshed from them too
        self.assertEqual({call[0][0].pk for call in mock_cache.call_args_list}, {self.poll.pk, retired.pk})
        self.assertEqual([call[0][0].pk for call in mock_clouds.call_args_list], [self.poll.pk])


class RefreshReusedFlowsTest(PollSyncTestBase):
    def test_lists_and_refreshes_the_flows_with_retired_and_syncing_polls(self):
        retired = self.create_poll(self.nigeria, "Poll 1 retired", "uuid-1", self.education_nigeria, self.admin)
        Poll.objects.filter(id=retired.id).update(stopped_syncing=True)
        self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin)

        out = StringIO()
        with patch("ureport.polls.management.commands.refresh_reused_flows.queue_full_repulls") as mock_repulls:
            call_command("refresh_reused_flows", stdout=out)

        mock_repulls.assert_not_called()
        self.assertIn("flow uuid-1 (poll #%d" % self.poll.pk, out.getvalue())
        self.assertNotIn("uuid-2", out.getvalue())
        self.assertIn("Found 1 flows", out.getvalue())

        with patch("ureport.polls.management.commands.refresh_reused_flows.queue_full_repulls") as mock_repulls:
            call_command("refresh_reused_flows", "--refresh", stdout=StringIO())

        self.assertEqual([poll.pk for poll in mock_repulls.call_args[0][0]], [self.poll.pk])

    def test_lists_and_refreshes_the_retired_flows_with_zeroed_counts(self):
        def retired_poll(title, flow_uuid, is_active=True, question=True):
            poll = self.create_poll(self.nigeria, title, flow_uuid, self.education_nigeria, self.admin)
            Poll.objects.filter(id=poll.id).update(stopped_syncing=True, is_active=is_active)
            if question:
                return self.create_poll_question(self.admin, poll, "Question", "ruleset-%s" % flow_uuid)

        # zeroed: retired, no results left and no positive counts, including a zero counter left behind
        zeroed = self.create_poll_question(self.admin, self.poll, "Question", "ruleset-uuid-1")
        Poll.objects.filter(id=self.poll.id).update(stopped_syncing=True)
        PollStatsCounter.objects.create(org=self.nigeria, flow_result=zeroed.flow_result, scope="all", count=0)

        # an older inactive duplicate of the zeroed flow isn't the one pulled again
        retired_poll("Poll 1 dupe", "uuid-1", is_active=False, question=False)

        counted = retired_poll("Poll 2 counted", "uuid-2")
        PollStatsCounter.objects.create(org=self.nigeria, flow_result=counted.flow_result, scope="all", count=3)

        retired_poll("Poll 3 with results", "uuid-3")
        PollResult.objects.create(
            org=self.nigeria,
            flow="uuid-3",
            ruleset="ruleset-uuid-3",
            contact="contact-1",
            date=timezone.now(),
            completed=False,
        )

        retired_poll("Poll 4 reused", "uuid-4")
        self.create_poll(self.nigeria, "Poll 4 syncing", "uuid-4", self.education_nigeria, self.admin)

        retired_poll("Poll 5 inactive", "uuid-5", is_active=False)
        retired_poll("Poll 6 without questions", "uuid-6", question=False)

        other = retired_poll("Poll 7 zeroed", "uuid-7")

        out = StringIO()
        with patch("ureport.polls.management.commands.refresh_reused_flows.queue_full_repulls") as mock_repulls:
            call_command("refresh_reused_flows", "--zeroed", stdout=out)

        mock_repulls.assert_not_called()
        self.assertIn("flow uuid-1 (poll #%d" % self.poll.pk, out.getvalue())
        self.assertIn("flow uuid-7 (poll #%d" % other.poll.pk, out.getvalue())
        for flow_uuid in ("uuid-2", "uuid-3", "uuid-4", "uuid-5", "uuid-6"):
            self.assertNotIn(flow_uuid, out.getvalue())
        self.assertIn("Found 2 flows", out.getvalue())

        out = StringIO()
        with patch("ureport.polls.management.commands.refresh_reused_flows.queue_full_repulls") as mock_repulls:
            call_command("refresh_reused_flows", "--zeroed", "--refresh", "--limit", "1", stdout=out)

        self.assertEqual([poll.pk for poll in mock_repulls.call_args[0][0]], [self.poll.pk])
        self.assertIn("Scheduled a full pull of 1 flows", out.getvalue())

        # an actual refresh syncs the flow again, which takes it off the list until it's retired again, and walks
        # the archives of all of them in one batch
        with (
            patch.object(Poll, "pull_poll_results_task") as mock_pull,
            patch.object(sync_poll_archives_batch, "apply_async"),
        ):
            call_command("refresh_reused_flows", "--zeroed", "--refresh", "--org", self.nigeria.pk, stdout=StringIO())

        self.assertEqual(mock_pull.call_count, 2)
        self.assertEqual(batch_owned_flows(self.nigeria.pk), {"uuid-1", "uuid-7"})
        self.assertEqual(
            set(Poll.objects.filter(stopped_syncing=False).values_list("flow_uuid", flat=True)),
            {"uuid-1", "uuid-4", "uuid-7"},
        )

        out = StringIO()
        call_command("refresh_reused_flows", "--zeroed", stdout=out)
        self.assertIn("Found 0 flows", out.getvalue())

    def test_lists_and_refreshes_the_flows_of_given_polls(self):
        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin)
        dupe = self.create_poll(self.nigeria, "Poll 1 again", "uuid-1", self.education_nigeria, self.admin)
        inactive = self.create_poll(self.nigeria, "Poll 3", "uuid-3", self.education_nigeria, self.admin)
        Poll.objects.filter(id=inactive.id).update(is_active=False)

        out = StringIO()
        with patch("ureport.polls.management.commands.refresh_reused_flows.queue_full_repulls") as mock_repulls:
            call_command(
                "refresh_reused_flows",
                *["--poll", str(self.poll.pk), "--poll", str(dupe.pk), "--poll", str(poll2.pk)],
                *["--poll", str(inactive.pk), "--refresh"],
                stdout=out,
            )

        # one poll per flow, the newest
        self.assertEqual([poll.pk for poll in mock_repulls.call_args[0][0]], [dupe.pk, poll2.pk])
        self.assertIn("Scheduled a full pull of 2 flows", out.getvalue())


@patch("ureport.polls.sync.POPULATE_BATCH_SIZE", 2)
@patch("ureport.polls.sync.POPULATE_BATCHES_PER_CHUNK", 2)
class BackfillAgeGenderTest(PollSyncTestBase):
    def setUp(self):
        super(BackfillAgeGenderTest, self).setUp()

        self.polls = [self.poll]
        for index in range(2, 8):
            self.polls.append(
                self.create_poll(self.nigeria, "Poll %d" % index, "uuid-%d" % index, self.education_nigeria, self.admin)
            )

        self.contacts = [
            Contact.objects.create(uuid="contact-%d" % index, org=self.nigeria, gender="M", born=1990)
            for index in range(1, 6)
        ]

        # another org's contacts belong to that org's job, ids are global but the walk isn't
        Contact.objects.create(uuid="contact-ug", org=self.uganda, gender="F", born=1985)

        self.job = SyncJob.get_or_create_job(self.nigeria, AGE_GENDER_JOB_TYPE)

        cache.delete(LAST_POPULATED_CONTACT_KEY)
        self.addCleanup(cache.delete, LAST_POPULATED_CONTACT_KEY)

    def backfill(self, populate=None):
        with (
            patch("ureport.utils.populate_age_and_gender_for_contacts") as mock_populate,
            patch.object(Poll, "rebuild_poll_results_counts", autospec=True) as mock_rebuild,
        ):
            if populate:
                mock_populate.side_effect = populate

            mock_continue = run_task(backfill_age_gender, self.job.id)

        populated = [list(call[0][0]) for call in mock_populate.call_args_list]

        return populated, [call[0][0].pk for call in mock_rebuild.call_args_list], mock_continue

    def contact_ids(self, *indexes):
        return [self.contacts[index].pk for index in indexes]

    def test_populates_in_batches_then_rebuilds(self):
        populated, rebuilt, mock_continue = self.backfill()

        # two batches of two contacts, the org's own, and nothing rebuilt yet
        self.assertEqual(populated, [self.contact_ids(0, 1), self.contact_ids(2, 3)])
        self.assertEqual(rebuilt, [])
        mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=None)

        self.assertJobState(
            self.job,
            cursor={"stage": "populate", "after_contact_id": self.contacts[3].pk},
            progress={"populated": 4},
        )

        # the fifth contact is the org's last, so the pass moves on to the rebuild
        populated, rebuilt, _ = self.backfill()

        self.assertEqual(populated, [self.contact_ids(4)])
        self.assertEqual(rebuilt, [])
        self.assertJobState(self.job, cursor={"stage": "rebuild", "populate_watermark": self.contacts[4].pk})

        populated, rebuilt, _ = self.backfill()

        self.assertEqual(populated, [])
        self.assertEqual(rebuilt, [poll.pk for poll in self.polls[:5]])

        populated, rebuilt, _ = self.backfill()
        self.assertEqual(rebuilt, [poll.pk for poll in self.polls[5:]])

        populated, rebuilt, mock_continue = self.backfill()

        self.assertEqual(rebuilt, [])
        mock_continue.assert_not_called()

        job = self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, progress={"populated": 5, "rebuilt": 7})
        self.assertEqual(job.cursor["populate_watermark"], self.contacts[4].pk)

    def test_resumes_the_populate_pass_after_a_takeover(self):
        positions = []

        def populate(contact_ids):
            job = reload(self.job)
            positions.append((job.cursor.get("after_contact_id"), job.lease_expires_on))

        self.backfill(populate=populate)

        # each batch checkpoints its position and renews the lease before the next one
        self.assertEqual([position[0] for position in positions], [0, self.contacts[1].pk])
        self.assertGreater(positions[1][1], positions[0][1])

        # a worker that dies part way through leaves the position of the batches it finished
        self.job.force_resync()

        def die(contact_ids):
            if contact_ids[0] == self.contacts[2].pk:
                raise ValueError("worker died")

        with self.assertRaises(ValueError):
            self.backfill(populate=die)

        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_FAILED,
            cursor={"stage": "populate", "after_contact_id": self.contacts[1].pk},
        )

        # and the walk carries on from there rather than from the org's first contact
        populated, _, _ = self.backfill()
        self.assertEqual(populated, [self.contact_ids(2, 3), self.contact_ids(4)])

    def test_resumes_the_rebuild_stage_after_a_kill(self):
        end_run(
            self.job,
            status=SyncJob.STATUS_FAILED,
            cursor={"stage": "rebuild", "after_pk": self.polls[2].pk},
            progress={"populated": 5, "rebuilt": 3},
        )

        populated, rebuilt, _ = self.backfill()

        self.assertEqual(populated, [])
        self.assertEqual(rebuilt, [poll.pk for poll in self.polls[3:]])

    def test_a_new_run_carries_on_from_the_last_watermark(self):
        end_run(
            self.job,
            cursor={"stage": "rebuild", "after_pk": self.polls[-1].pk, "populate_watermark": self.contacts[2].pk},
            progress={"populated": 5, "rebuilt": 7},
            ended_on=timezone.now() - timedelta(days=1),
        )

        populated, rebuilt, _ = self.backfill()

        # only the contacts added since the last run, and the polls are walked from the start
        self.assertEqual(populated, [self.contact_ids(3, 4)])
        self.assertEqual(rebuilt, [])

        populated, _, _ = self.backfill()
        self.assertEqual(populated, [])
        self.assertEqual(reload(self.job).cursor["populate_watermark"], self.contacts[4].pk)

    def test_seeds_a_first_run_from_the_unchunked_position(self):
        cache.set(LAST_POPULATED_CONTACT_KEY, self.contacts[2].pk, None)

        populated, _, _ = self.backfill()

        self.assertEqual(populated, [self.contact_ids(3, 4)])

        # the retired key is only ever read, the job keeps its own position from here
        self.assertEqual(cache.get(LAST_POPULATED_CONTACT_KEY), self.contacts[2].pk)


class MaintenanceDispatchTest(PollSyncTestBase):
    def counts_nudge(self):
        with patch.object(rebuild_poll_counts, "apply_async") as mock_queue:
            rebuild_counts_dispatch()

        return mock_queue

    def prune_nudge(self):
        with patch.object(prune_poll_results, "apply_async") as mock_queue:
            queued = prune_results_dispatch()

        return queued, mock_queue

    def test_nudges_the_global_counts_job(self):
        now = timezone.now()

        self.counts_nudge()

        job = SyncJob.objects.get(job_type=COUNTS_JOB_TYPE)
        self.assertIsNone(job.org_id)
        self.assertEqual(job.scope, "")

        # a pass that finished a moment ago isn't started again
        end_run(job, ended_on=now - timedelta(hours=2))
        self.counts_nudge().assert_not_called()

        end_run(job, ended_on=now - timedelta(hours=21))
        self.counts_nudge().assert_called_once_with((job.id,), queue="slow")

        # nor is one still working through its polls, or a paused one
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_RUNNING)
        hold_lease(job)
        self.counts_nudge().assert_not_called()

        drop_lease(job)
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_PAUSED)
        self.counts_nudge().assert_not_called()

        # and a failing streak stretches the wait beyond the daily cadence
        end_run(job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(hours=21), failures=10)
        self.counts_nudge().assert_not_called()

        end_run(job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(days=2), failures=10)
        self.counts_nudge().assert_called_once()

    def test_measures_the_cadence_from_when_a_run_started(self):
        now = timezone.now()

        self.counts_nudge()
        job = SyncJob.objects.get(job_type=COUNTS_JOB_TYPE)

        # a pass that started 19 hours ago is not due again yet, however long it ran for
        end_run(job, started_on=now - timedelta(hours=19), ended_on=now - timedelta(hours=1))
        self.counts_nudge().assert_not_called()

        # but a pass that started 21 hours ago is, even though it only ended five hours ago
        # - measured from the end, a daily job taking hours would drift into two day gaps
        end_run(job, started_on=now - timedelta(hours=21), ended_on=now - timedelta(hours=5))
        self.counts_nudge().assert_called_once()

    def complete_prunes(self, ended_on):
        SyncJob.objects.filter(job_type=PRUNE_JOB_TYPE).update(
            status=SyncJob.STATUS_COMPLETE, started_on=ended_on, ended_on=ended_on
        )

    def test_nudges_a_prune_job_per_org(self):
        now = timezone.now()
        active_orgs = set(Org.objects.filter(is_active=True).values_list("pk", flat=True))

        queued, mock_queue = self.prune_nudge()

        self.assertEqual(set(queued), active_orgs)
        self.assertEqual(mock_queue.call_count, len(active_orgs))
        self.assertEqual(
            set(SyncJob.objects.filter(job_type=PRUNE_JOB_TYPE).values_list("org_id", flat=True)), active_orgs
        )

        self.complete_prunes(now - timedelta(hours=2))
        self.assertEqual(self.prune_nudge()[0], [])

        self.complete_prunes(now - timedelta(hours=21))
        self.assertEqual(set(self.prune_nudge()[0]), active_orgs)

        # a paused org's prune is left alone, the rest still run
        SyncJob.objects.filter(job_type=PRUNE_JOB_TYPE, org=self.nigeria).update(status=SyncJob.STATUS_PAUSED)
        self.assertNotIn(self.nigeria.pk, self.prune_nudge()[0])

    def test_nudges_a_single_org(self):
        self.assertIn(self.uganda.pk, self.prune_nudge()[0])

        self.complete_prunes(timezone.now() - timedelta(days=1))

        with patch.object(prune_poll_results, "apply_async") as mock_queue:
            self.assertEqual(prune_results_dispatch(self.nigeria.pk), [self.nigeria.pk])

        job = SyncJob.objects.get(org=self.nigeria, job_type=PRUNE_JOB_TYPE)
        mock_queue.assert_called_once_with((job.id,), queue="slow")


class MaintenanceShimTest(PollSyncTestBase):
    def test_rebuild_counts_queues_the_global_job(self):
        with patch.object(rebuild_poll_counts, "apply_async") as mock_queue:
            rebuild_counts()

        job = SyncJob.objects.get(job_type=COUNTS_JOB_TYPE)
        self.assertIsNone(job.org_id)
        mock_queue.assert_called_once_with((job.id,), queue="slow")

    def test_clear_old_poll_results_queues_the_orgs_prune(self):
        with patch.object(prune_poll_results, "apply_async") as mock_queue:
            clear_old_poll_results(self.nigeria.pk)

        job = SyncJob.objects.get(org=self.nigeria, job_type=PRUNE_JOB_TYPE)
        mock_queue.assert_called_once_with((job.id,), queue="slow")

    def test_update_results_age_gender_queues_backfills(self):
        with patch.object(backfill_age_gender, "apply_async") as mock_queue:
            update_results_age_gender(self.nigeria.pk)

        job = SyncJob.objects.get(org=self.nigeria, job_type=AGE_GENDER_JOB_TYPE)
        mock_queue.assert_called_once_with((job.id,), queue="slow")

        # without an org it covers every active one
        with patch.object(backfill_age_gender, "apply_async") as mock_queue:
            update_results_age_gender()

        self.assertEqual(mock_queue.call_count, Org.objects.filter(is_active=True).count())

        # an org id that resolves to nothing does nothing, rather than falling back to all
        with patch.object(backfill_age_gender, "apply_async") as mock_queue:
            update_results_age_gender(-1)

        mock_queue.assert_not_called()

    def test_shims_record_no_task_state(self):
        with (
            patch.object(rebuild_poll_counts, "apply_async"),
            patch.object(prune_poll_results, "apply_async"),
            patch.object(backfill_age_gender, "apply_async"),
        ):
            rebuild_counts()
            clear_old_poll_results(self.nigeria.pk)
            update_results_age_gender()

        # they only enqueue now, so they must not pass themselves off as having run
        self.assertFalse(TaskState.objects.exists())


class SyncStatusTest(PollSyncTestBase):
    def setUp(self):
        super(SyncStatusTest, self).setUp()

        Poll.objects.filter(id=self.poll.id).update(has_synced=True)
        self.poll.refresh_from_db()
        self.view = PollCRUDL.List()

    def test_reports_the_jobs_state(self):
        # no job yet, i.e. nothing has synced this flow since the sync jobs landed
        self.assertEqual(self.view.get_sync_status(self.poll), "Synced")

        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        self.assertEqual(self.view.get_sync_status(self.poll), "Synced")

        end_run(job, ended_on=timezone.now() - timedelta(hours=8))
        self.assertIn("8", self.view.get_sync_status(self.poll))

        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_RUNNING)
        hold_lease(job)
        self.assertIn("in progress", self.view.get_sync_status(self.poll))

    def test_reports_progress_for_an_unsynced_poll(self):
        Poll.objects.filter(id=self.poll.id).update(has_synced=False)

        self.assertIn("in progress", self.view.get_sync_status(Poll.objects.get(id=self.poll.id)))
