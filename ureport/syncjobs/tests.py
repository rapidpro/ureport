import uuid
from datetime import timedelta
from unittest.mock import patch

from celery.exceptions import Retry

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dash.orgs.models import Org
from ureport.syncjobs.dispatch import Backoff, enqueue, in_flight, is_due
from ureport.syncjobs.models import (
    ABORTED,
    DEFAULT_LEASE_SECONDS,
    MAX_ERROR_LENGTH,
    MAX_ERROR_SUMMARY_LENGTH,
    STATUS_CACHE_KEY,
    LeaseLost,
    SyncJob,
)
from ureport.syncjobs.tasks import JOB_TASKS, MAX_REPORTED_JOBS, check_jobs, chunked_task
from ureport.syncjobs.testing import (
    SyncJobTestMixin,
    drop_lease,
    end_run,
    expire_lease,
    hold_lease,
    make_stale,
    make_task,
    reload,
    run_task,
    run_to_completion,
)
from ureport.tests import UreportTest


class SyncJobTest(SyncJobTestMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(None, "test-sync", "flow-1")

    def test_get_or_create_is_idempotent(self):
        again = SyncJob.get_or_create_job(None, "test-sync", "flow-1")
        self.assertEqual(self.job.id, again.id)

        other = SyncJob.get_or_create_job(None, "test-sync", "flow-2")
        self.assertNotEqual(self.job.id, other.id)

    def test_unique_constraint(self):
        # global jobs (null org) are unique per (job_type, scope) too - nulls_distinct=False
        with self.assertRaises(IntegrityError), transaction.atomic():
            SyncJob.objects.create(org=None, job_type="test-sync", scope="flow-1")

        user = User.objects.create_user("admin", "admin@example.com")
        org = Org.objects.create(name="Test", subdomain="test", created_by=user, modified_by=user)

        SyncJob.objects.create(org=org, job_type="test-sync", scope="flow-1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            SyncJob.objects.create(org=org, job_type="test-sync", scope="flow-1")

    def test_claim_only_one_winner(self):
        contender = SyncJob.objects.get(id=self.job.id)

        claimed = self.job.claim("worker-1")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.status, SyncJob.STATUS_RUNNING)
        self.assertEqual(claimed.lease_owner, "worker-1")
        self.assertIsNotNone(claimed.started_on)

        self.assertIsNone(contender.claim("worker-2"))

    def test_claim_after_lease_expiry_resumes(self):
        self.job.claim("worker-1")
        started_on = self.job.started_on
        self.job.checkpoint(cursor={"after": "t1"}, progress={"chunks": 2})

        # lease still live so another worker can't take it
        contender = SyncJob.objects.get(id=self.job.id)
        self.assertIsNone(contender.claim("worker-2"))

        # expire the lease as if worker-1 died mid chunk
        SyncJob.objects.filter(id=self.job.id).update(lease_expires_on=timezone.now() - timedelta(seconds=1))

        contender = SyncJob.objects.get(id=self.job.id)
        resumed = contender.claim("worker-2")
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed.lease_owner, "worker-2")

        # a resume keeps the interrupted run's cursor, progress and start time
        self.assertEqual(resumed.cursor, {"after": "t1"})
        self.assertEqual(resumed.progress, {"chunks": 2})
        self.assertEqual(resumed.started_on, started_on)

    def test_claim_released_running_job_resumes(self):
        # the between-chunks state every continuation claims from
        self.job.claim("worker-1")
        self.job.checkpoint(cursor={"after": "t1"}, progress={"chunks": 1})
        self.job.release_lease()

        continuation = SyncJob.objects.get(id=self.job.id)
        resumed = continuation.claim("worker-2")
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed.progress, {"chunks": 1})
        self.assertEqual(resumed.cursor, {"after": "t1"})

    def test_claim_complete_job_starts_new_run(self):
        self.job.claim("worker-1")
        self.job.checkpoint(cursor={"after": "t1"}, progress={"chunks": 5})
        self.job.mark_complete()
        self.job.release_lease()
        first_started_on = self.job.started_on

        job = SyncJob.objects.get(id=self.job.id)
        claimed = job.claim("worker-2")
        self.assertIsNotNone(claimed)

        # a new run keeps the cursor but resets progress and start time
        self.assertEqual(claimed.cursor, {"after": "t1"})
        self.assertEqual(claimed.progress, {})
        self.assertGreater(claimed.started_on, first_started_on)
        self.assertIsNone(claimed.ended_on)

    def test_complete_job_with_live_lease_not_claimable(self):
        # the lease held through finalization must block new runs
        self.job.claim("worker-1")
        self.job.mark_complete(needs_finalize=True)
        self.assertEqual(self.job.status, SyncJob.STATUS_COMPLETE)

        thief = SyncJob.objects.get(id=self.job.id)
        self.assertIsNone(thief.claim("worker-2"))

        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.lease_owner, "worker-1")
        self.assertTrue(current.needs_finalize)

    def test_paused_job_not_claimable(self):
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_PAUSED)
        job = SyncJob.objects.get(id=self.job.id)
        self.assertIsNone(job.claim("worker-1"))

        # the row is untouched by the failed claim
        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.status, SyncJob.STATUS_PAUSED)
        self.assertIsNone(current.lease_owner)

    def test_checkpoint_requires_lease(self):
        # never-claimed job can't checkpoint
        with self.assertRaises(LeaseLost):
            self.job.checkpoint(cursor={"after": "t0"})

        self.job.claim("worker-1")

        # another worker takes over after our lease expires
        SyncJob.objects.filter(id=self.job.id).update(lease_expires_on=timezone.now() - timedelta(seconds=1))
        SyncJob.objects.get(id=self.job.id).claim("worker-2")

        with self.assertRaises(LeaseLost):
            self.job.checkpoint(cursor={"after": "t2"})

        # the usurper's job state is untouched by our attempt
        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.lease_owner, "worker-2")
        self.assertNotEqual(current.cursor, {"after": "t2"})

    def test_checkpoint_renews_lease(self):
        self.job.claim("worker-1", lease_seconds=60)
        first_expiry = self.job.lease_expires_on

        self.job.checkpoint(cursor={"after": "t1"}, lease_seconds=600)
        self.assertGreater(self.job.lease_expires_on, first_expiry)
        self.assertEqual(self.job.cursor, {"after": "t1"})

    def test_checkpoint_renews_for_the_declared_lease(self):
        # a job nobody declared a lease for - one claimed by hand, or re-fetched by a chunk
        # rather than the one its task handed it - renews for the default
        self.job.claim("worker-1", lease_seconds=60)

        self.job.checkpoint(cursor={"after": "t1"})
        self.assertAlmostEqual(
            (self.job.lease_expires_on - timezone.now()).total_seconds(), DEFAULT_LEASE_SECONDS, delta=30
        )

        # and one a task stamped renews for as long as that task claimed it
        self.job.lease_seconds = 1800
        self.job.checkpoint(cursor={"after": "t2"})
        self.assertAlmostEqual((self.job.lease_expires_on - timezone.now()).total_seconds(), 1800, delta=30)

    def test_claim_reports_whether_it_started_a_run(self):
        claimed = self.job.claim("worker-1")
        self.assertTrue(claimed.new_run)
        claimed.checkpoint(cursor={"after": "t1"})
        claimed.release_lease()

        # the continuation of a run in flight resumes it, so it isn't a new one - and the
        # state the job was in before the claim can't say that: a run may have ended between
        # reading it and claiming, which is what a duplicate delivery does
        self.assertFalse(reload(self.job).claim("worker-2").new_run)

        # nor is the retry of a failed one
        self.job.refresh_from_db()
        self.job.record_failure("boom")
        self.assertFalse(reload(self.job).claim("worker-3").new_run)

        # but the next claim of a job whose run ended is
        self.job.refresh_from_db()
        self.job.mark_complete()
        self.job.release_lease()
        self.assertTrue(reload(self.job).claim("worker-4").new_run)

        # an unclaimed job is running nothing, so nothing about it is fresh
        self.assertFalse(SyncJob.get_or_create_job(None, "test-sync", "flow-2").new_run)

    def test_abort(self):
        self.job.claim("worker-1")
        self.job.checkpoint(cursor={"stage": "contacts"}, progress={"chunks": 2})

        # aborting is done, with nothing left for the next run to resume from
        self.assertTrue(self.job.abort(skipped=1))
        self.assertJobState(self.job, cursor={}, progress={"chunks": 2, ABORTED: 1, "skipped": 1})

        # the marker is the framework's own, so an app counter can't be mistaken for it
        self.assertNotIn("aborted", reload(self.job).progress)

        # unless the chunk knows where the next run should pick up
        self.assertTrue(self.job.abort(cursor={"last_until": "t1"}))
        self.assertJobState(self.job, cursor={"last_until": "t1"})

    def test_back_off(self):
        self.job.claim("worker-1")
        modified_on = self.job.modified_on

        # nothing to record, so nothing is written - the delay is all the chunk wanted
        self.assertEqual(self.job.back_off(300), 300)
        self.assertJobState(self.job, modified_on=modified_on, progress={})

        self.assertEqual(self.job.back_off(300, lock_backoffs=1), 300)
        self.assertJobState(self.job, progress={"lock_backoffs": 1})

    def test_reset_cursor(self):
        self.job.claim("worker-1", lease_seconds=600)
        self.job.checkpoint(cursor={"after": "t1"}, progress={"chunks": 2})

        # its worker owns the cursor while the lease is live, so the reset is refused
        self.assertFalse(self.job.reset_cursor())
        self.assertJobState(self.job, cursor={"after": "t1"})

        drop_lease(self.job)
        self.assertTrue(self.job.reset_cursor())

        # only the position is dropped - the run it belongs to is left as it was
        self.assertJobState(self.job, cursor={}, progress={"chunks": 2}, status=SyncJob.STATUS_RUNNING)

    def test_non_owner_cannot_mutate(self):
        self.job.claim("worker-1")

        # worker-2 takes over after worker-1's lease expires
        SyncJob.objects.filter(id=self.job.id).update(lease_expires_on=timezone.now() - timedelta(seconds=1))
        SyncJob.objects.get(id=self.job.id).claim("worker-2")

        # stale worker-1 updates are refused and report it
        self.assertFalse(self.job.mark_complete())
        self.assertFalse(self.job.clear_finalize())
        self.assertFalse(self.job.release_lease())
        self.assertFalse(self.job.record_failure("boom"))

        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.lease_owner, "worker-2")
        self.assertEqual(current.status, SyncJob.STATUS_RUNNING)
        self.assertEqual(current.last_error, "")

        # and once a worker has released, its own stale object can't mutate the unowned row
        current.release_lease()
        self.assertFalse(current.mark_complete())
        self.assertEqual(SyncJob.objects.get(id=self.job.id).status, SyncJob.STATUS_RUNNING)

    def test_add_progress(self):
        self.job.claim("worker-1")
        self.job.checkpoint(progress={"created": 10, "updated": 2})

        merged = self.job.add_progress(created=5, ignored=1)
        self.assertEqual(merged, {"created": 15, "updated": 2, "ignored": 1})

        # add_progress itself writes nothing
        self.assertEqual(SyncJob.objects.get(id=self.job.id).progress, {"created": 10, "updated": 2})

    def test_complete_and_finalize_flow(self):
        self.job.claim("worker-1")
        self.assertTrue(self.job.mark_complete(needs_finalize=True))

        self.assertEqual(self.job.status, SyncJob.STATUS_COMPLETE)
        self.assertTrue(self.job.needs_finalize)
        self.assertIsNotNone(self.job.ended_on)
        # lease is kept through finalization so no new run starts under it
        self.assertEqual(self.job.lease_owner, "worker-1")

        self.assertTrue(self.job.clear_finalize())
        self.assertTrue(self.job.release_lease())

        current = SyncJob.objects.get(id=self.job.id)
        self.assertFalse(current.needs_finalize)
        self.assertIsNone(current.lease_owner)

    def test_record_failure(self):
        self.job.claim("worker-1")
        self.assertTrue(self.job.record_failure("boom"))

        self.assertEqual(self.job.status, SyncJob.STATUS_FAILED)
        self.assertEqual(self.job.consecutive_failures, 1)
        self.assertEqual(self.job.last_error, "boom")
        self.assertIsNone(self.job.lease_owner)

        # failed jobs are immediately claimable for a retry
        retry = SyncJob.objects.get(id=self.job.id).claim("worker-2")
        self.assertIsNotNone(retry)

        # completing a run clears the failure streak
        retry.mark_complete()
        self.assertEqual(retry.consecutive_failures, 0)
        self.assertEqual(retry.last_error, "")

    def test_record_failure_truncates_error(self):
        self.job.claim("worker-1")
        self.job.record_failure("x" * (MAX_ERROR_LENGTH * 2))
        self.assertEqual(len(self.job.last_error), MAX_ERROR_LENGTH)


class ChunkedTaskTest(SyncJobTestMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(None, "test-sync", "flow-1")

    def test_runs_chunks_to_completion(self):
        task, ran = make_task(chunks_to_run=3)

        with patch.object(task, "apply_async") as mock_continue:
            # each continuation is enqueued, not executed - drive them by hand as a worker would
            task(self.job.id)
            mock_continue.assert_called_once_with((self.job.id,), queue="testq", countdown=None)
            task(self.job.id)
            task(self.job.id)
            self.assertEqual(mock_continue.call_count, 2)

        self.assertEqual(ran, [0, 1, 2])

        self.assertJobState(
            self.job, status=SyncJob.STATUS_COMPLETE, cursor={"chunk": 3}, progress={"chunks": 3}, lease_owner=None
        )

    def test_trigger_against_live_lease_retries_after_expiry(self):
        task, ran = make_task(chunks_to_run=2)

        # a job someone else is running under a live lease - e.g. a redelivered chunk
        # whose original worker is still alive
        self.job.claim("other-worker", lease_seconds=600)

        with patch.object(task, "apply_async") as mock_continue:
            with self.assertRaises(Retry):
                task(self.job.id)

        self.assertEqual(ran, [])
        mock_continue.assert_not_called()

        # the job itself is untouched
        self.assertJobState(self.job, lease_owner="other-worker")

    def test_trigger_against_paused_job_skips(self):
        task, ran = make_task(chunks_to_run=2)
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_PAUSED)

        mock_continue = run_task(task, self.job.id)  # no retry, no error

        self.assertEqual(ran, [])
        mock_continue.assert_not_called()

    def test_finalize_runs_once_on_completion(self):
        finalized = []
        task, ran = make_task(chunks_to_run=1, finalize=lambda job: finalized.append(job.id))

        run_task(task, self.job.id)

        self.assertEqual(finalized, [self.job.id])
        self.assertJobState(self.job, needs_finalize=False, lease_owner=None)

    def test_crashed_finalize_is_retried_with_completed_runs_state(self):
        finalized = []
        task, ran = make_task(chunks_to_run=2, finalize=lambda job: finalized.append(dict(job.progress)))

        # simulate a worker that completed a run with real progress but died before finalizing
        self.job.claim("dead-worker")
        self.job.checkpoint(progress={"chunks": 7, "created": 700})
        self.job.mark_complete(needs_finalize=True)
        drop_lease(self.job)

        run_task(task, self.job.id)

        # the leftover finalization saw the completed run's progress, not the fresh run's
        # reset state, and ran before the new run's first chunk
        self.assertEqual(finalized[0], {"chunks": 7, "created": 700})
        self.assertEqual(ran, [0])

    def test_chunk_failure_records_and_reraises(self):
        task, ran = make_task(chunks_to_run=3, fail_on_chunk=1)

        with patch.object(task, "apply_async"):
            task(self.job.id)  # chunk 0 succeeds
            with self.assertRaises(ValueError):
                task(self.job.id)  # chunk 1 fails

        # cursor still points at the failed chunk so a retry resumes there
        job = self.assertJobState(
            self.job, status=SyncJob.STATUS_FAILED, consecutive_failures=1, cursor={"chunk": 1}, lease_owner=None
        )
        self.assertIn("failing on chunk 1", job.last_error)

        # the failed job is claimable again and the retry resumes from the cursor
        task2, ran2 = make_task(chunks_to_run=3)
        run_task(task2, self.job.id, times=2)

        self.assertEqual(ran2, [1, 2])
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)

    def test_failing_finalize_records_failure_and_is_retried(self):
        attempts = []

        def finalize(job):
            attempts.append(job.id)
            if len(attempts) == 1:
                raise ValueError("finalize blew up")

        task, ran = make_task(chunks_to_run=1, finalize=finalize)

        with patch.object(task, "apply_async"):
            with self.assertRaises(ValueError):
                task(self.job.id)

        # the work completed but the failed finalization is recorded and retryable:
        # failure counted, lease released so the retry needn't wait out its expiry,
        # and needs_finalize still set so the retry finalizes before anything else
        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_FAILED,
            consecutive_failures=1,
            needs_finalize=True,
            lease_owner=None,
        )

        run_task(task, self.job.id)

        # the retry runs the leftover finalization first, then its own completion's -
        # at-least-once semantics, which is why finalize hooks must be idempotent
        self.assertEqual(len(attempts), 3)
        self.assertJobState(self.job, needs_finalize=False, status=SyncJob.STATUS_COMPLETE, consecutive_failures=0)

    def test_chunk_can_delay_continuation(self):
        delayed = []

        @chunked_task("test-sync", queue="testq", name=f"test.sync.{uuid.uuid4().hex}")
        def sync_backoff(job):
            done = job.cursor.get("chunk", 0) >= 1
            job.checkpoint(cursor={"chunk": job.cursor.get("chunk", 0) + 1})
            if done:
                return True
            delayed.append(True)
            return 300  # e.g. rate limited - continue in five minutes

        with patch.object(sync_backoff, "apply_async") as mock_continue:
            sync_backoff(self.job.id)
            mock_continue.assert_called_once_with((self.job.id,), queue="testq", countdown=300)
            sync_backoff(self.job.id)

        self.assertEqual(delayed, [True])
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)

    def test_missing_job_is_skipped(self):
        task, ran = make_task(chunks_to_run=1)

        mock_continue = run_task(task, -1)

        self.assertEqual(ran, [])
        mock_continue.assert_not_called()

    def test_continuation_of_paused_job_stops_quietly(self):
        task, ran = make_task(chunks_to_run=3)

        with patch.object(task, "apply_async") as mock_continue:
            task(self.job.id)
            self.assertEqual(mock_continue.call_count, 1)

            # an operator pauses between chunks - the queued continuation stops the run,
            # without retrying against a lease that isn't there
            self.assertTrue(reload(self.job).pause())
            task(self.job.id)

        self.assertEqual(ran, [0])
        self.assertEqual(mock_continue.call_count, 1)
        self.assertJobState(self.job, status=SyncJob.STATUS_PAUSED)

    def test_continuation_after_force_resync_restarts(self):
        task, ran = make_task(chunks_to_run=4)

        with patch.object(task, "apply_async"):
            task(self.job.id)
            task(self.job.id)
            self.assertEqual(ran, [0, 1])

            # the old cursor can't come back through the continuation that was already
            # queued when the resync was requested
            self.assertTrue(reload(self.job).force_resync())
            task(self.job.id)

        self.assertEqual(ran, [0, 1, 0])
        self.assertJobState(self.job, cursor={"chunk": 1}, progress={"chunks": 1})


class ChunkedTaskStateTest(SyncJobTestMixin, TestCase):
    """
    What the framework tells a chunk about the claim it is running under, and what it does
    with what the chunk tells it back.
    """

    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(None, "test-sync", "flow-1")

    def test_chunk_checkpoints_with_the_declared_lease(self):
        renewals = []

        @chunked_task("test-sync", queue="testq", lease_seconds=1800, name=f"test.sync.{uuid.uuid4().hex}")
        def sync_leases(job):
            job.checkpoint(cursor={"chunk": 1})
            renewals.append(job.lease_expires_on)

            # a chunk that knows better can still say so
            job.checkpoint(lease_seconds=60)
            renewals.append(job.lease_expires_on)
            return True

        run_task(sync_leases, self.job.id)

        now = timezone.now()
        self.assertAlmostEqual((renewals[0] - now).total_seconds(), 1800, delta=30)
        self.assertAlmostEqual((renewals[1] - now).total_seconds(), 60, delta=30)

    def test_new_run_marks_the_first_chunk_of_a_run(self):
        seen = []

        @chunked_task("test-sync", queue="testq", name=f"test.sync.{uuid.uuid4().hex}")
        def sync_runs(job):
            seen.append(job.new_run)
            chunk = job.cursor.get("chunk", 0)
            job.checkpoint(cursor={"chunk": chunk + 1})
            return chunk >= 1

        # a job that has never run starts one, and its continuation resumes that same run
        self.assertEqual(run_to_completion(sync_runs, self.job.id), 2)
        self.assertEqual(seen, [True, False])

        # the next claim of a completed job starts a fresh run
        seen.clear()
        run_task(sync_runs, self.job.id)
        self.assertEqual(seen, [True])

        # while a failed run is retried rather than restarted
        seen.clear()
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_FAILED)
        run_task(sync_runs, self.job.id)
        self.assertEqual(seen, [False])

    def test_aborted_run_completes_without_finalizing(self):
        finalized = []

        @chunked_task(
            "test-sync", queue="testq", finalize=lambda job: finalized.append(job.id), name=f"test.{uuid.uuid4().hex}"
        )
        def sync_aborts(job):
            return job.abort(skipped=1)

        run_task(sync_aborts, self.job.id)

        # there is nothing for finalization to report on, but the run is still finished and
        # its lease released, and nothing is left over for the next one
        self.assertEqual(finalized, [])
        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_COMPLETE,
            cursor={},
            progress={ABORTED: 1, "skipped": 1},
            needs_finalize=False,
            lease_owner=None,
        )

    def test_leftover_finalize_of_an_aborted_run_is_skipped(self):
        finalized = []
        task, ran = make_task(chunks_to_run=1, finalize=lambda job: finalized.append(job.id))

        # a worker that aborted a run and died before clearing its finalize flag
        self.job.claim("dead-worker")
        self.job.checkpoint(progress={ABORTED: 1})
        self.job.mark_complete(needs_finalize=True)
        drop_lease(self.job)

        run_task(task, self.job.id)

        # the leftover finalization went with the run it belonged to, this run's still ran
        self.assertEqual(finalized, [self.job.id])
        self.assertEqual(ran, [0])

    def test_one_task_per_job_type(self):
        make_task(chunks_to_run=1)

        # two tasks for a type would each drive the other's jobs, on whatever queue and
        # lease they happened to declare
        with self.assertRaises(ImproperlyConfigured):

            @chunked_task("test-sync", queue="testq", name=f"test.sync.{uuid.uuid4().hex}")
            def sync_again(job):
                return True

    def test_chunk_can_back_off_and_record_why(self):
        @chunked_task("test-sync", queue="testq", name=f"test.sync.{uuid.uuid4().hex}")
        def sync_blocked(job):
            if job.progress.get("lock_backoffs"):
                job.checkpoint(cursor={"chunk": 1})
                return True

            return job.back_off(300, lock_backoffs=1)

        mock_continue = run_task(sync_blocked, self.job.id)

        mock_continue.assert_called_once_with((self.job.id,), queue="testq", countdown=300)
        self.assertJobState(self.job, progress={"lock_backoffs": 1}, cursor={})

        run_task(sync_blocked, self.job.id)
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={"chunk": 1})


class DispatchTest(SyncJobTestMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(None, "test-sync", "flow-1")

        # the task this job type is run by, i.e. what the registry resolves for it - and
        # with it the lease everything here is measured against
        self.task, _ = make_task(chunks_to_run=2)

    def test_enqueue_routes_to_the_job_types_task(self):
        task, ran = make_task(chunks_to_run=1, queue="slowq")
        self.assertEqual(JOB_TASKS["test-sync"], task)

        with patch.object(task, "apply_async") as mock_enqueue:
            enqueue(self.job)
            enqueue(self.job, countdown=300)

        # the job knows its type, and the queue comes with the task that type is run by
        self.assertEqual(mock_enqueue.call_args_list[0][0], ((self.job.id,),))
        self.assertEqual(mock_enqueue.call_args_list[0][1], dict(queue="slowq"))
        self.assertEqual(mock_enqueue.call_args_list[1][1], dict(queue="slowq", countdown=300))

    def test_in_flight_under_a_live_lease(self):
        self.assertFalse(in_flight(self.job, timezone.now()))

        # a chunk is being worked on, whatever state the row is otherwise in
        hold_lease(self.job)
        self.assertTrue(in_flight(self.job, timezone.now()))

    def test_in_flight_between_chunks(self):
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_RUNNING)

        # the lease is released between continuations, so a moving run looks idle from here
        self.assertTrue(in_flight(reload(self.job), timezone.now()))

        # but a run that stopped checkpointing is deliberately not in flight - nudging it is
        # how a chain that died without recording a failure gets picked back up
        job = make_stale(self.job, 2 * DEFAULT_LEASE_SECONDS + 60)
        self.assertFalse(in_flight(job, timezone.now()))

    def test_in_flight_of_a_pending_job(self):
        now = timezone.now()

        # a job nobody has claimed is only in flight for callers whose enqueue records the
        # nudge on the row, i.e. where a fresh modified_on means a message is on the queue
        self.assertFalse(in_flight(self.job, now))
        self.assertTrue(in_flight(self.job, now, include_pending=True))

        job = make_stale(self.job, 2 * DEFAULT_LEASE_SECONDS + 60)
        self.assertFalse(in_flight(job, now, include_pending=True))

    def test_in_flight_of_an_unregistered_job_type(self):
        job = SyncJob.get_or_create_job(None, "no-such-task", "flow-1")
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_RUNNING)

        # nothing declares how long its chunks take, so the default lease is what it gets
        self.assertTrue(in_flight(reload(job), timezone.now()))
        self.assertFalse(in_flight(make_stale(job, 2 * DEFAULT_LEASE_SECONDS + 60), timezone.now()))

    def test_is_due_measures_the_cadence_from_the_last_start(self):
        now = timezone.now()
        hourly = timedelta(hours=1)

        # a job that has never run is due at any cadence
        self.assertTrue(is_due(self.job, now, interval=hourly))

        job = end_run(self.job, started_on=now - timedelta(minutes=30), ended_on=now - timedelta(minutes=5))
        self.assertFalse(is_due(job, now, interval=hourly))

        # no cadence asked for means any run that isn't moving is due
        self.assertTrue(is_due(job, now))

        job = end_run(self.job, started_on=now - timedelta(hours=2), ended_on=now - timedelta(minutes=5))
        self.assertTrue(is_due(job, now, interval=hourly))

        # a run that ended without ever starting - an abort, say - falls back to its end
        job = end_run(self.job, started_on=None, ended_on=now - timedelta(minutes=5))
        self.assertFalse(is_due(job, now, interval=hourly))

    def test_is_due_waits_out_the_failure_backoff(self):
        now = timezone.now()
        backoff = Backoff(base=timedelta(minutes=20), cap=timedelta(hours=2), max_doublings=3)

        job = end_run(self.job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(minutes=5), failures=1)
        self.assertTrue(is_due(job, now))  # nobody asked for a backoff
        self.assertFalse(is_due(job, now, backoff=backoff))

        job = end_run(self.job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(minutes=25), failures=1)
        self.assertTrue(is_due(job, now, backoff=backoff))

        # each further failure doubles the wait - 20, 40, 80 minutes ...
        job = end_run(self.job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(minutes=25), failures=3)
        self.assertFalse(is_due(job, now, backoff=backoff))

        # ... up to the cap, however long the streak
        job = end_run(self.job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(hours=1), failures=9)
        self.assertFalse(is_due(job, now, backoff=backoff))

        job = end_run(self.job, status=SyncJob.STATUS_FAILED, ended_on=now - timedelta(hours=3), failures=9)
        self.assertTrue(is_due(job, now, backoff=backoff))

    def test_failure_backoff_never_outpaces_the_cadence(self):
        # a run long enough to outlast its own cadence keeps the cadence open from then on,
        # so the backoff is what has to hold a failing job back - the ladder's early rungs
        # must not retry it faster than it would run when healthy
        now = timezone.now()
        daily = timedelta(hours=24)
        backoff = Backoff(base=timedelta(minutes=20), cap=timedelta(days=7), max_doublings=10)

        job = end_run(
            self.job,
            status=SyncJob.STATUS_FAILED,
            started_on=now - timedelta(days=3),
            ended_on=now - timedelta(hours=2),
            failures=1,
        )
        self.assertFalse(is_due(job, now, interval=daily, backoff=backoff))

        # and once the cadence itself is up, it is due
        job = end_run(
            self.job,
            status=SyncJob.STATUS_FAILED,
            started_on=now - timedelta(days=3),
            ended_on=now - timedelta(days=2),
            failures=1,
        )
        self.assertTrue(is_due(job, now, interval=daily, backoff=backoff))

        # a streak whose ladder climbs past the cadence stretches the wait beyond it
        job = end_run(
            self.job,
            status=SyncJob.STATUS_FAILED,
            started_on=now - timedelta(days=3),
            ended_on=now - timedelta(days=2),
            failures=9,  # 20 minutes doubled eight times, i.e. more than three days
        )
        self.assertFalse(is_due(job, now, interval=daily, backoff=backoff))

    def test_is_due_nudges_a_run_that_never_ended(self):
        # a chain that died without recording a failure left no end to schedule from, and
        # the run it was still in the middle of says nothing about when the next one is due
        now = timezone.now()
        SyncJob.objects.filter(id=self.job.id).update(
            status=SyncJob.STATUS_RUNNING, started_on=now - timedelta(minutes=5), ended_on=None
        )

        job = make_stale(self.job, 2 * DEFAULT_LEASE_SECONDS + 60)
        self.assertTrue(is_due(job, now, interval=timedelta(hours=24)))

    def test_is_due_leaves_paused_and_moving_jobs_alone(self):
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_PAUSED)
        self.assertFalse(is_due(reload(self.job), timezone.now()))

        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_RUNNING)
        self.assertFalse(is_due(reload(self.job), timezone.now()))


class SyncJobQueriesTest(TestCase):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(None, "test-sync", "flow-1")

    def test_stale_respects_grace(self):
        # a job whose worker is still renewing its lease is working, not stale
        self.job.claim("worker-1", lease_seconds=600)
        self.assertEqual(list(SyncJob.objects.stale()), [])

        # a lease that expired moments ago may still be taken over by a redelivered chunk
        expire_lease(self.job, 60)
        self.assertEqual(list(SyncJob.objects.stale()), [])
        self.assertEqual(list(SyncJob.objects.stale(grace_seconds=30)), [self.job])

        # the grace is measured from the expiry, not from now
        self.assertEqual(list(SyncJob.objects.stale(grace_seconds=61)), [])
        self.assertEqual(list(SyncJob.objects.stale(grace_seconds=59)), [self.job])

        expire_lease(self.job, 60 * 30)
        self.assertEqual(list(SyncJob.objects.stale()), [self.job])

    def test_stale_covers_lost_continuations(self):
        # the between-chunks state - no lease to expire, the continuation is queued
        self.job.claim("worker-1")
        self.job.release_lease()
        self.assertEqual(list(SyncJob.objects.stale()), [])

        # but if that continuation never arrives the run is just as abandoned
        make_stale(self.job, 60 * 30)
        self.assertEqual(list(SyncJob.objects.stale()), [self.job])

    def test_stale_ignores_ended_runs(self):
        self.job.claim("worker-1")
        self.job.record_failure("boom")
        expire_lease(self.job, 60 * 30)
        make_stale(self.job, 60 * 30)

        self.assertEqual(list(SyncJob.objects.stale()), [])

    def test_failing_respects_threshold(self):
        other = SyncJob.get_or_create_job(None, "test-sync", "flow-2")
        SyncJob.objects.filter(id=self.job.id).update(consecutive_failures=2)
        SyncJob.objects.filter(id=other.id).update(consecutive_failures=3)

        self.assertEqual(list(SyncJob.objects.failing()), [other])
        self.assertEqual(list(SyncJob.objects.failing(threshold=2).order_by("id")), [self.job, other])
        self.assertEqual(list(SyncJob.objects.failing(threshold=4)), [])

    def test_failing_ignores_paused_jobs(self):
        SyncJob.objects.filter(id=self.job.id).update(consecutive_failures=5)
        self.assertEqual(list(SyncJob.objects.failing()), [self.job])

        # a job stopped on purpose shouldn't keep alerting about why it was stopped
        self.assertTrue(self.job.pause())
        self.assertEqual(list(SyncJob.objects.failing()), [])

    def test_error_summary(self):
        self.assertEqual(self.job.error_summary, "")

        self.job.last_error = "Traceback (most recent call last):\n  File x\nValueError: boom\n"
        self.assertEqual(self.job.error_summary, "ValueError: boom")

        self.job.last_error = "x" * 500
        self.assertEqual(len(self.job.error_summary), MAX_ERROR_SUMMARY_LENGTH)


class OperatorActionsTest(SyncJobTestMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(None, "test-sync", "flow-1")

    def test_pause_refused_under_live_lease(self):
        self.job.claim("worker-1", lease_seconds=600)
        self.assertFalse(self.job.pause())

        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.status, SyncJob.STATUS_RUNNING)
        self.assertEqual(current.lease_owner, "worker-1")

    def test_pause_between_chunks(self):
        self.job.claim("worker-1")
        self.job.checkpoint(cursor={"after": "t1"})
        self.job.release_lease()

        self.assertTrue(self.job.pause())
        self.assertEqual(self.job.status, SyncJob.STATUS_PAUSED)

        # the paused job is no longer claimable, and its cursor is kept for the resume
        self.assertIsNone(SyncJob.objects.get(id=self.job.id).claim("worker-2"))
        self.assertEqual(self.job.cursor, {"after": "t1"})

    def test_pause_allowed_once_lease_expires(self):
        self.job.claim("worker-1")
        expire_lease(self.job)

        self.assertTrue(self.job.pause())

        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.status, SyncJob.STATUS_PAUSED)

        # the lapsed lease is dropped with the pause, see test_paused_job_survives_its_worker
        self.assertIsNone(current.lease_owner)
        self.assertIsNone(current.lease_expires_on)

    def test_paused_job_survives_its_worker(self):
        # a worker whose lease lapsed is still alive and still finishing its chunk
        self.job.claim("worker-1")
        expire_lease(self.job)
        self.assertTrue(self.job.pause())

        # its writes must not take the job back out of the paused state
        worker_view = SyncJob.objects.get(id=self.job.id)
        worker_view.lease_owner = "worker-1"

        self.assertFalse(worker_view.mark_complete())
        self.assertFalse(worker_view.record_failure("boom"))
        self.assertFalse(worker_view.clear_finalize())

        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.status, SyncJob.STATUS_PAUSED)
        self.assertEqual(current.last_error, "")
        self.assertIsNone(current.claim("worker-1"))

    def test_resume(self):
        # only a paused job can be resumed
        self.assertFalse(self.job.resume())
        self.assertEqual(self.job.status, SyncJob.STATUS_PENDING)

        self.job.claim("worker-1")
        self.job.checkpoint(cursor={"chunk": 3}, progress={"chunks": 3})
        self.job.release_lease()
        self.assertTrue(self.job.pause())

        # a run paused in flight resumes rather than restarting, so it keeps its progress
        self.assertTrue(self.job.resume())
        self.assertEqual(self.job.status, SyncJob.STATUS_RUNNING)
        self.assertIsNone(self.job.lease_owner)

        claimed = SyncJob.objects.get(id=self.job.id).claim("worker-2")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.progress, {"chunks": 3})
        self.assertEqual(claimed.cursor, {"chunk": 3})

    def test_resume_of_job_between_runs(self):
        # nothing in flight - a completed job goes back to waiting for its next trigger
        self.job.claim("worker-1")
        self.job.checkpoint(cursor={"after": "t1"}, progress={"chunks": 3})
        self.job.mark_complete()
        self.job.release_lease()
        self.assertTrue(self.job.pause())

        self.assertTrue(self.job.resume())
        self.assertEqual(self.job.status, SyncJob.STATUS_PENDING)

        # and the next claim starts a fresh run from the carried forward cursor
        claimed = SyncJob.objects.get(id=self.job.id).claim("worker-2")
        self.assertEqual(claimed.progress, {})
        self.assertEqual(claimed.cursor, {"after": "t1"})

    def test_force_resync_refused_under_live_lease(self):
        self.job.claim("worker-1", lease_seconds=600)
        self.job.checkpoint(cursor={"after": "t1"}, progress={"chunks": 2})

        self.assertFalse(self.job.force_resync())

        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.cursor, {"after": "t1"})
        self.assertEqual(current.progress, {"chunks": 2})
        self.assertEqual(current.status, SyncJob.STATUS_RUNNING)

    def test_force_resync_clears_position(self):
        self.job.claim("worker-1")
        self.job.checkpoint(cursor={"after": "t1"}, progress={"chunks": 2})
        self.job.record_failure("boom")

        self.assertTrue(self.job.force_resync())

        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.status, SyncJob.STATUS_PENDING)
        self.assertEqual(current.cursor, {})
        self.assertEqual(current.progress, {})
        self.assertIsNone(current.started_on)
        self.assertIsNone(current.ended_on)
        self.assertIsNone(current.lease_owner)
        self.assertIsNone(current.lease_expires_on)
        self.assertFalse(current.needs_finalize)

        # the failure streak stays until a run actually completes
        self.assertEqual(current.consecutive_failures, 1)

        # the next run starts from scratch
        claimed = SyncJob.objects.get(id=self.job.id).claim("worker-2")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.cursor, {})

    def test_force_resync_of_completed_job_drops_finalization(self):
        self.job.claim("worker-1")
        self.job.mark_complete(needs_finalize=True)
        self.job.release_lease()

        self.assertTrue(self.job.force_resync())
        self.assertFalse(SyncJob.objects.get(id=self.job.id).needs_finalize)


class CheckJobsTest(TestCase):
    def setUp(self):
        cache.delete(STATUS_CACHE_KEY)
        self.addCleanup(cache.delete, STATUS_CACHE_KEY)

    def test_no_problems(self):
        healthy = SyncJob.get_or_create_job(None, "test-sync", "flow-1")
        healthy.claim("worker-1", lease_seconds=600)
        SyncJob.get_or_create_job(None, "other-sync", "backend")

        check_jobs()

        output = cache.get(STATUS_CACHE_KEY)
        self.assertEqual(output["stale_jobs"], {})
        self.assertEqual(output["failing_jobs"], {})
        self.assertEqual(output["totals"], dict(running=1, stale=0, failing=0))
        self.assertEqual(output["by_type"], {"test-sync": {"Running": 1}, "other-sync": {"Pending": 1}})
        self.assertIsNotNone(output["checked_on"])

    def test_reports_stale_and_failing_jobs(self):
        stale = SyncJob.get_or_create_job(None, "test-sync", "flow-1")
        stale.claim("dead-worker")
        stale.checkpoint(progress={"chunks": 4})
        expired_on = timezone.now() - timedelta(hours=1)
        SyncJob.objects.filter(id=stale.id).update(lease_expires_on=expired_on)

        failing = SyncJob.get_or_create_job(None, "test-sync", "flow-2")
        SyncJob.objects.filter(id=failing.id).update(
            status=SyncJob.STATUS_FAILED, consecutive_failures=4, last_error="Traceback:\n  File x\nValueError: boom"
        )

        check_jobs()

        output = cache.get(STATUS_CACHE_KEY)
        self.assertEqual(list(output["stale_jobs"]), [f"{stale.id}"])

        stale_status = output["stale_jobs"][f"{stale.id}"]
        self.assertEqual(stale_status["id"], stale.id)
        self.assertIsNone(stale_status["org"])
        self.assertEqual(stale_status["job_type"], "test-sync")
        self.assertEqual(stale_status["scope"], "flow-1")
        self.assertEqual(stale_status["status"], "Running")
        self.assertEqual(stale_status["progress"], {"chunks": 4})
        self.assertEqual(stale_status["last_error"], "")
        self.assertEqual(stale_status["lease_expires_on"], expired_on.isoformat())
        self.assertEqual(stale_status["stale_for"], 3600)

        self.assertEqual(list(output["failing_jobs"]), [f"{failing.id}"])
        failing_status = output["failing_jobs"][f"{failing.id}"]
        self.assertEqual(failing_status["id"], failing.id)
        self.assertEqual(failing_status["scope"], "flow-2")
        self.assertEqual(failing_status["consecutive_failures"], 4)
        self.assertEqual(failing_status["last_error"], "ValueError: boom")
        self.assertIsNone(failing_status["lease_expires_on"])
        self.assertIsNone(failing_status["stale_for"])

        self.assertEqual(output["totals"], dict(running=1, stale=1, failing=1))

    def test_detail_is_capped_but_totals_are_not(self):
        for num in range(MAX_REPORTED_JOBS + 5):
            job = SyncJob.get_or_create_job(None, "test-sync", f"flow-{num}")
            SyncJob.objects.filter(id=job.id).update(consecutive_failures=3)

        check_jobs()

        output = cache.get(STATUS_CACHE_KEY)
        self.assertEqual(len(output["failing_jobs"]), MAX_REPORTED_JOBS)
        self.assertEqual(output["totals"]["failing"], MAX_REPORTED_JOBS + 5)


class StatusReportTest(TestCase):
    def setUp(self):
        cache.delete(STATUS_CACHE_KEY)
        self.addCleanup(cache.delete, STATUS_CACHE_KEY)

    def test_report_without_monitor_output(self):
        self.assertEqual(
            SyncJob.get_status_report(),
            dict(
                by_type={},
                stale_jobs={},
                failing_jobs={},
                totals=dict(running=0, stale=0, failing=0),
                checked_on=None,
            ),
        )
        self.assertEqual(SyncJob.get_status_counts(), dict(running=0, stale=0, failing=0, checked_on=None))

    def test_report_reads_only_the_cache(self):
        running = SyncJob.get_or_create_job(None, "test-sync", "flow-1")
        running.claim("worker-1")
        check_jobs()

        # a job that appears after the check isn't counted until the next one
        SyncJob.get_or_create_job(None, "other-sync", "backend")

        with self.assertNumQueries(0):
            report = SyncJob.get_status_report()
            counts = SyncJob.get_status_counts()

        self.assertEqual(report["by_type"], {"test-sync": {"Running": 1}})
        self.assertEqual(counts["running"], 1)
        self.assertIsNotNone(counts["checked_on"])

        # and the public counts carry no scopes, orgs or error text
        self.assertEqual(set(counts), {"running", "stale", "failing", "checked_on"})


class SyncJobCRUDLTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(self.uganda, "test-sync", "flow-1")
        self.other_job = SyncJob.get_or_create_job(self.nigeria, "other-sync", "backend")

        cache.delete(STATUS_CACHE_KEY)
        self.addCleanup(cache.delete, STATUS_CACHE_KEY)

    def test_list(self):
        list_url = reverse("syncjobs.syncjob_list")

        # the controls are operational, so no org admin gets to see them
        self.login(self.admin)
        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.superuser)
        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        # every org's jobs, not just the one whose site we're on
        self.assertEqual(set(response.context["object_list"]), {self.job, self.other_job})

        response = self.client.get(list_url + "?job_type=other-sync", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(list(response.context["object_list"]), [self.other_job])

        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_FAILED)
        response = self.client.get(list_url + "?status=F", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(list(response.context["object_list"]), [self.job])

        response = self.client.get(list_url + "?search=flow-1", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(list(response.context["object_list"]), [self.job])

    def test_list_shows_last_check(self):
        self.job.claim("worker-1", lease_seconds=600)
        check_jobs()

        self.login(self.superuser)
        response = self.client.get(reverse("syncjobs.syncjob_list"), SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["report"]["totals"], dict(running=1, stale=0, failing=0))

    def test_actions(self):
        pause_url = reverse("syncjobs.syncjob_pause", args=[self.job.id])
        resume_url = reverse("syncjobs.syncjob_resume", args=[self.job.id])
        resync_url = reverse("syncjobs.syncjob_force_resync", args=[self.job.id])

        self.login(self.admin)
        self.assertLoginRedirect(self.client.post(pause_url, SERVER_NAME="uganda.ureport.io"))
        self.assertEqual(SyncJob.objects.get(id=self.job.id).status, SyncJob.STATUS_PENDING)

        self.login(self.superuser)

        # nothing to control by GET - the actions only apply on a post
        response = self.client.get(pause_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 405)

        response = self.client.post(pause_url, SERVER_NAME="uganda.ureport.io", follow=True)
        self.assertEqual(SyncJob.objects.get(id=self.job.id).status, SyncJob.STATUS_PAUSED)
        self.assertContains(response, f"Paused job #{self.job.id}")

        response = self.client.post(resume_url, SERVER_NAME="uganda.ureport.io", follow=True)
        self.assertEqual(SyncJob.objects.get(id=self.job.id).status, SyncJob.STATUS_PENDING)
        self.assertContains(response, f"Resumed job #{self.job.id}")

        SyncJob.objects.filter(id=self.job.id).update(cursor={"after": "t1"}, progress={"chunks": 2})
        response = self.client.post(resync_url, SERVER_NAME="uganda.ureport.io", follow=True)

        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.cursor, {})
        self.assertEqual(current.progress, {})

    def test_actions_refused_while_job_is_running(self):
        self.job.claim("worker-1", lease_seconds=600)
        self.job.checkpoint(cursor={"after": "t1"})

        self.login(self.superuser)
        response = self.client.post(
            reverse("syncjobs.syncjob_pause", args=[self.job.id]), SERVER_NAME="uganda.ureport.io", follow=True
        )
        self.assertContains(response, "being worked on")

        response = self.client.post(
            reverse("syncjobs.syncjob_force_resync", args=[self.job.id]), SERVER_NAME="uganda.ureport.io", follow=True
        )
        self.assertContains(response, "being worked on")

        # the worker's run is untouched by both
        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.status, SyncJob.STATUS_RUNNING)
        self.assertEqual(current.lease_owner, "worker-1")
        self.assertEqual(current.cursor, {"after": "t1"})

    def test_resume_of_unpaused_job_is_refused(self):
        self.login(self.superuser)
        response = self.client.post(
            reverse("syncjobs.syncjob_resume", args=[self.job.id]), SERVER_NAME="uganda.ureport.io", follow=True
        )
        self.assertContains(response, "isn&#x27;t paused")
