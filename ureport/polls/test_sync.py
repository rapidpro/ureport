# -*- coding: utf-8 -*-

from datetime import timedelta, timezone as tzone

from mock import patch

from django.core.cache import cache
from django.utils import timezone

from dash.categories.models import Category
from dash.orgs.models import TaskState
from ureport.backend import ChunkResult
from ureport.backend.rapidpro import RapidProBackend
from ureport.polls.models import Poll, PollResult
from ureport.polls.sync import (
    ARCHIVES_JOB_TYPE,
    RATE_LIMITED_BACKOFF,
    RESULTS_JOB_TYPE,
    dispatch_org_polls,
    sync_poll_archives,
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
)
from ureport.polls.views import PollCRUDL
from ureport.syncjobs.models import SyncJob
from ureport.tests import UreportTest
from ureport.utils import datetime_to_json_date


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


class PollSyncTestBase(UreportTest):
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

    def start_patch(self, patcher):
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def test_seeds_cursor_from_legacy_cache_key(self):
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, "uuid-1"), "2026-08-01T10:00:00.000Z", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(
                counts=results_counts(num_val_created=3), cursor={"after": "2026-08-02T10:00:00.000Z"}, done=True
            )
            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

        self.assertEqual(mock_chunk.call_args[0][1], {"after": "2026-08-01T10:00:00.000Z"})

    def test_starts_from_scratch_without_legacy_position(self):
        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": None}, done=True)
            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

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

            with patch.object(sync_poll_results, "apply_async") as mock_continue:
                sync_poll_results(self.job.id)

                mock_continue.assert_called_once_with((self.job.id,), queue="sync", countdown=None)

                job = self.get_job()
                self.assertEqual(job.status, SyncJob.STATUS_RUNNING)
                self.assertEqual(job.cursor, {"after": "t1", "resume": "c1"})

                # the continuation picks up from the checkpointed position
                sync_poll_results(self.job.id)

        self.assertEqual(mock_chunk.call_args_list[1][0][1], {"after": "t1", "resume": "c1"})

        job = self.get_job()
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.cursor, {"after": "t2"})
        self.assertEqual(job.progress["chunks"], 2)
        self.assertEqual(job.progress["num_val_created"], 3)
        self.assertEqual(job.progress["num_synced"], 15)

    def test_backs_off_when_rate_limited(self):
        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(
                counts=results_counts(), cursor={"after": "t1", "resume": "c1"}, rate_limited=True
            )
            with patch.object(sync_poll_results, "apply_async") as mock_continue:
                sync_poll_results(self.job.id)

        mock_continue.assert_called_once_with((self.job.id,), queue="sync", countdown=RATE_LIMITED_BACKOFF)
        self.assertEqual(self.get_job().cursor, {"after": "t1", "resume": "c1"})

    def test_rebuilds_counts_periodically(self):
        # a run four chunks in, i.e. between chunks of an interrupted traversal
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_RUNNING, progress={"chunks": 4})

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(num_val_created=1), cursor={"after": "t5"})

            with patch.object(sync_poll_results, "apply_async"):
                # the fifth chunk rebuilds so partial results reach the public site
                sync_poll_results(self.job.id)
                self.mock_rebuild.assert_called_once()

                self.mock_rebuild.reset_mock()
                sync_poll_results(self.job.id)
                self.mock_rebuild.assert_not_called()

    def test_queues_archives_on_first_sync(self):
        self.mock_flow_date.return_value = None

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t1"}, done=True)

            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

        archives_job = self.get_job(ARCHIVES_JOB_TYPE)
        self.mock_queue_archives.assert_called_once_with((archives_job.id,), queue="sync")

    def test_no_archives_for_recent_flow_or_synced_poll(self):
        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t1"}, done=True)

            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)
                self.mock_queue_archives.assert_not_called()

                # nor once the polls on the flow have completed their first sync
                self.mock_flow_date.return_value = None
                sync_poll_results(self.job.id)
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

            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

        # the traversal starts over, the deleted results are gone and the archives are walked again
        self.assertEqual(mock_chunk.call_args[0][1], {})
        self.assertFalse(PollResult.objects.filter(org=self.nigeria, flow="uuid-1").exists())
        self.assertIsNone(cache.get(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk)))
        self.assertEqual(self.get_job(ARCHIVES_JOB_TYPE).cursor, {})
        self.mock_queue_archives.assert_called_once_with((archives_job.id,), queue="sync")

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

                job = self.get_job()
                self.assertEqual(job.status, SyncJob.STATUS_FAILED)
                self.assertEqual(job.cursor, {})

                # the retry pulls from scratch rather than resuming past the deleted results
                sync_poll_results(self.job.id)

        self.assertEqual(mock_chunk.call_args[0][1], {})

    def test_restarts_when_a_duplicate_poll_asks_for_it(self):
        # the newest poll of the flow is the one the job syncs, but the flag can be set on
        # any poll sharing it
        newest = self.create_poll(self.nigeria, "Poll newest", "uuid-1", self.education_nigeria, self.admin)
        SyncJob.objects.filter(id=self.job.id).update(cursor={"after": "t1"})

        cache.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.nigeria.pk, self.poll.pk), "2026-08-01", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t2"}, done=True)

            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

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

            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

                # its worker still owns the cursor, so the reset is deferred, not dropped
                self.assertEqual(self.get_job(ARCHIVES_JOB_TYPE).cursor, {"before": "2026-01-01"})
                self.assertEqual(self.get_job().progress["archives_reset_pending"], 1)

                SyncJob.objects.filter(id=archives_job.id).update(lease_owner=None, lease_expires_on=None)
                sync_poll_results(self.job.id)

        self.assertEqual(self.get_job(ARCHIVES_JOB_TYPE).cursor, {})
        self.assertNotIn("archives_reset_pending", self.get_job().progress)

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

                sync_poll_results(self.job.id)

        # one job, nudged by both attempts - the failed one never got to run the archives
        self.assertEqual(SyncJob.objects.filter(job_type=ARCHIVES_JOB_TYPE, scope="uuid-1").count(), 1)
        self.assertEqual(self.mock_queue_archives.call_count, 2)

    def test_finalize_skips_rebuild_when_nothing_changed(self):
        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(num_val_ignored=7), cursor={}, done=True)

            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

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

            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

        # the leftover finalize saw the completed run's counters, this run's changed nothing
        self.mock_rebuild.assert_called_once()
        self.assertTrue(Poll.objects.get(id=self.poll.id).has_synced)
        self.assertFalse(self.get_job().needs_finalize)
        self.assertEqual(cache.get(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, "uuid-1")), "t2")

    def test_completed_cursor_is_not_reseeded_from_the_legacy_key(self):
        # a stale legacy position must never pull a caught up job backwards
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_COMPLETE, cursor={"after": "t2"})
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.nigeria.pk, "uuid-1"), "t0", None)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"after": "t3"}, done=True)

            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

        self.assertEqual(mock_chunk.call_args[0][1], {"after": "t2"})

    def test_finalize_marks_synced_and_mirrors_position(self):
        same_flow = self.create_poll(self.nigeria, "Poll same flow", "uuid-1", self.education_nigeria, self.admin)

        with patch.object(RapidProBackend, "pull_results_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(
                counts=results_counts(num_val_created=1), cursor={"after": "2026-08-11T09:00:00.000Z"}, done=True
            )
            with patch.object(sync_poll_results, "apply_async"):
                sync_poll_results(self.job.id)

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
            with patch.object(sync_poll_results, "apply_async") as mock_continue:
                sync_poll_results(self.job.id)

        mock_chunk.assert_not_called()
        mock_continue.assert_not_called()
        self.mock_rebuild.assert_not_called()
        self.assertEqual(self.get_job().status, SyncJob.STATUS_COMPLETE)


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

            with (
                patch.object(sync_poll_archives, "apply_async") as mock_continue,
                patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild,
            ):
                sync_poll_archives(self.job.id)
                mock_continue.assert_called_once_with((self.job.id,), queue="sync", countdown=None)

                sync_poll_archives(self.job.id)

        self.assertEqual(mock_chunk.call_args_list[1][0][1], {"before": "2026-07-01", "seen": ["a"]})
        mock_rebuild.assert_called_once()

        job = self.get_job(ARCHIVES_JOB_TYPE)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress["chunks"], 2)

        self.poll.refresh_from_db()
        self.assertTrue(self.poll.has_synced)

    def test_finalize_skips_rebuild_without_results(self):
        with patch.object(RapidProBackend, "pull_results_from_archives_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(counts=results_counts(), cursor={"before": "2026-06-01"}, done=True)

            with (
                patch.object(sync_poll_archives, "apply_async"),
                patch.object(Poll, "rebuild_poll_results_counts") as mock_rebuild,
            ):
                sync_poll_archives(self.job.id)

        mock_rebuild.assert_not_called()
        self.poll.refresh_from_db()
        self.assertTrue(self.poll.has_synced)

    def test_backs_off_when_rate_limited(self):
        with patch.object(RapidProBackend, "pull_results_from_archives_chunk") as mock_chunk:
            mock_chunk.return_value = ChunkResult(
                counts=results_counts(), cursor={"before": "2026-07-01"}, rate_limited=True
            )
            with patch.object(sync_poll_archives, "apply_async") as mock_continue:
                sync_poll_archives(self.job.id)

        mock_continue.assert_called_once_with((self.job.id,), queue="sync", countdown=RATE_LIMITED_BACKOFF)


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
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_COMPLETE, ended_on=timezone.now())

        self.assertIn("uuid-1", self.dispatch())

    def test_respects_cadence_of_completed_jobs(self):
        now = timezone.now()
        self.assertEqual(self.dispatch(), {"uuid-1", "uuid-main", "uuid-other"})

        SyncJob.objects.filter(org=self.nigeria, job_type=RESULTS_JOB_TYPE).update(
            status=SyncJob.STATUS_COMPLETE, ended_on=now - timedelta(minutes=10)
        )
        self.assertEqual(self.dispatch(), {"uuid-1"})

        # the main poll is due again after twenty minutes, the other poll only after a day
        SyncJob.objects.filter(org=self.nigeria, job_type=RESULTS_JOB_TYPE).update(
            status=SyncJob.STATUS_COMPLETE, ended_on=now - timedelta(minutes=30)
        )
        self.assertEqual(self.dispatch(), {"uuid-1", "uuid-main"})

        SyncJob.objects.filter(org=self.nigeria, job_type=RESULTS_JOB_TYPE).update(
            status=SyncJob.STATUS_COMPLETE, ended_on=now - timedelta(days=2)
        )
        self.assertEqual(self.dispatch(), {"uuid-1", "uuid-main", "uuid-other"})

    def test_skips_jobs_under_a_live_lease(self):
        SyncJob.objects.filter(id=SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1").id).update(
            lease_owner="worker-1", lease_expires_on=timezone.now() + timedelta(minutes=5)
        )

        self.assertNotIn("uuid-1", self.dispatch())

    def test_skips_a_run_between_chunks(self):
        # chunks release the lease between continuations, so a moving run looks idle here
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_RUNNING, modified_on=timezone.now())

        self.assertNotIn("uuid-1", self.dispatch())

        # but a run that stopped checkpointing is picked back up - the recovery nudge for a
        # chain that died without recording a failure
        SyncJob.objects.filter(id=job.id).update(modified_on=timezone.now() - timedelta(hours=3))

        self.assertIn("uuid-1", self.dispatch())

    def test_backs_off_failing_jobs(self):
        now = timezone.now()
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")

        # a failed job is not retried at the dispatcher's rate, even at the always-due cadence
        SyncJob.objects.filter(id=job.id).update(
            status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(minutes=5), consecutive_failures=1
        )
        self.assertNotIn("uuid-1", self.dispatch())

        SyncJob.objects.filter(id=job.id).update(ended_on=now - timedelta(minutes=25))
        self.assertIn("uuid-1", self.dispatch())

        # and the streak stretches the wait
        SyncJob.objects.filter(id=job.id).update(consecutive_failures=3)
        self.assertNotIn("uuid-1", self.dispatch())

        SyncJob.objects.filter(id=job.id).update(ended_on=now - timedelta(hours=3))
        self.assertIn("uuid-1", self.dispatch())

    def test_never_queues_paused_jobs(self):
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_PAUSED)

        self.assertNotIn("uuid-1", self.dispatch())

    def test_nudges_unfinished_archive_traversals(self):
        now = timezone.now()
        failed = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=failed.id).update(
            status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(hours=2), consecutive_failures=1
        )
        done = SyncJob.get_or_create_job(self.nigeria, ARCHIVES_JOB_TYPE, "uuid-main")
        SyncJob.objects.filter(id=done.id).update(status=SyncJob.STATUS_COMPLETE, ended_on=now)
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
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_COMPLETE, cursor={"before": "2026-01-01"})

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


class ClearOldResultsTest(PollSyncTestBase):
    def setUp(self):
        super(ClearOldResultsTest, self).setUp()

        Poll.objects.filter(id=self.poll.id).update(
            poll_date=timezone.now() - timedelta(days=500), created_on=timezone.now() - timedelta(days=500)
        )

    def clear(self):
        with (
            patch.object(Poll, "rebuild_poll_results_counts"),
            patch.object(Poll, "delete_poll_results") as mock_delete,
        ):
            clear_old_poll_results(self.nigeria.pk)

        return mock_delete

    def test_leaves_a_flow_alone_while_its_sync_holds_the_lease(self):
        job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE, "uuid-1")
        SyncJob.objects.filter(id=job.id).update(
            status=SyncJob.STATUS_RUNNING,
            lease_owner="worker-1",
            lease_expires_on=timezone.now() + timedelta(minutes=5),
        )

        self.clear().assert_not_called()
        self.assertFalse(Poll.objects.get(id=self.poll.id).stopped_syncing)

        # once the lease is gone the results can be cleared
        SyncJob.objects.filter(id=job.id).update(lease_owner=None, lease_expires_on=None)

        self.clear().assert_called_once()
        self.assertTrue(Poll.objects.get(id=self.poll.id).stopped_syncing)


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

        SyncJob.objects.filter(id=job.id).update(
            status=SyncJob.STATUS_COMPLETE, ended_on=timezone.now() - timedelta(hours=8)
        )
        self.assertIn("8", self.view.get_sync_status(self.poll))

        SyncJob.objects.filter(id=job.id).update(
            status=SyncJob.STATUS_RUNNING, lease_expires_on=timezone.now() + timedelta(minutes=5)
        )
        self.assertIn("in progress", self.view.get_sync_status(self.poll))

    def test_reports_progress_for_an_unsynced_poll(self):
        Poll.objects.filter(id=self.poll.id).update(has_synced=False)

        self.assertIn("in progress", self.view.get_sync_status(Poll.objects.get(id=self.poll.id)))
