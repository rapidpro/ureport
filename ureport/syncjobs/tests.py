import uuid
from datetime import timedelta
from unittest.mock import patch

from celery.exceptions import Retry

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from dash.orgs.models import Org
from ureport.syncjobs.models import MAX_ERROR_LENGTH, LeaseLost, SyncJob
from ureport.syncjobs.tasks import chunked_task


class SyncJobTest(TestCase):
    def setUp(self):
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


def _make_task(chunks_to_run, finalize=None, fail_on_chunk=None):
    """
    Builds a chunked task that pretends to have the given number of chunks of work,
    recording each chunk it runs.
    """
    ran = []

    @chunked_task("test-sync", queue="testq", finalize=finalize, name=f"test.sync.{uuid.uuid4().hex}")
    def sync_test(job):
        chunk = job.cursor.get("chunk", 0)
        if fail_on_chunk is not None and chunk == fail_on_chunk:
            raise ValueError(f"failing on chunk {chunk}")

        ran.append(chunk)
        job.checkpoint(cursor={"chunk": chunk + 1}, progress=job.add_progress(chunks=1))
        return chunk + 1 >= chunks_to_run

    return sync_test, ran


class ChunkedTaskTest(TestCase):
    def setUp(self):
        self.job = SyncJob.get_or_create_job(None, "test-sync", "flow-1")

    def test_runs_chunks_to_completion(self):
        task, ran = _make_task(chunks_to_run=3)

        with patch.object(task, "apply_async") as mock_continue:
            # each continuation is enqueued, not executed - drive them by hand as a worker would
            task(self.job.id)
            mock_continue.assert_called_once_with((self.job.id,), queue="testq", countdown=None)
            task(self.job.id)
            task(self.job.id)
            self.assertEqual(mock_continue.call_count, 2)

        self.assertEqual(ran, [0, 1, 2])

        job = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.cursor, {"chunk": 3})
        self.assertEqual(job.progress, {"chunks": 3})
        self.assertIsNone(job.lease_owner)

    def test_trigger_against_live_lease_retries_after_expiry(self):
        task, ran = _make_task(chunks_to_run=2)

        # a job someone else is running under a live lease - e.g. a redelivered chunk
        # whose original worker is still alive
        self.job.claim("other-worker", lease_seconds=600)

        with patch.object(task, "apply_async") as mock_continue:
            with self.assertRaises(Retry):
                task(self.job.id)

        self.assertEqual(ran, [])
        mock_continue.assert_not_called()

        # the job itself is untouched
        current = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(current.lease_owner, "other-worker")

    def test_trigger_against_paused_job_skips(self):
        task, ran = _make_task(chunks_to_run=2)
        SyncJob.objects.filter(id=self.job.id).update(status=SyncJob.STATUS_PAUSED)

        with patch.object(task, "apply_async") as mock_continue:
            task(self.job.id)  # no retry, no error

        self.assertEqual(ran, [])
        mock_continue.assert_not_called()

    def test_finalize_runs_once_on_completion(self):
        finalized = []
        task, ran = _make_task(chunks_to_run=1, finalize=lambda job: finalized.append(job.id))

        with patch.object(task, "apply_async"):
            task(self.job.id)

        self.assertEqual(finalized, [self.job.id])
        job = SyncJob.objects.get(id=self.job.id)
        self.assertFalse(job.needs_finalize)
        self.assertIsNone(job.lease_owner)

    def test_crashed_finalize_is_retried_with_completed_runs_state(self):
        finalized = []
        task, ran = _make_task(chunks_to_run=2, finalize=lambda job: finalized.append(dict(job.progress)))

        # simulate a worker that completed a run with real progress but died before finalizing
        self.job.claim("dead-worker")
        self.job.checkpoint(progress={"chunks": 7, "created": 700})
        self.job.mark_complete(needs_finalize=True)
        SyncJob.objects.filter(id=self.job.id).update(lease_owner=None, lease_expires_on=None)

        with patch.object(task, "apply_async"):
            task(self.job.id)

        # the leftover finalization saw the completed run's progress, not the fresh run's
        # reset state, and ran before the new run's first chunk
        self.assertEqual(finalized[0], {"chunks": 7, "created": 700})
        self.assertEqual(ran, [0])

    def test_chunk_failure_records_and_reraises(self):
        task, ran = _make_task(chunks_to_run=3, fail_on_chunk=1)

        with patch.object(task, "apply_async"):
            task(self.job.id)  # chunk 0 succeeds
            with self.assertRaises(ValueError):
                task(self.job.id)  # chunk 1 fails

        job = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(job.status, SyncJob.STATUS_FAILED)
        self.assertEqual(job.consecutive_failures, 1)
        self.assertIn("failing on chunk 1", job.last_error)
        # cursor still points at the failed chunk so a retry resumes there
        self.assertEqual(job.cursor, {"chunk": 1})
        self.assertIsNone(job.lease_owner)

        # the failed job is claimable again and the retry resumes from the cursor
        task2, ran2 = _make_task(chunks_to_run=3)
        with patch.object(task2, "apply_async"):
            task2(self.job.id)
            task2(self.job.id)

        self.assertEqual(ran2, [1, 2])
        self.assertEqual(SyncJob.objects.get(id=self.job.id).status, SyncJob.STATUS_COMPLETE)

    def test_failing_finalize_records_failure_and_is_retried(self):
        attempts = []

        def finalize(job):
            attempts.append(job.id)
            if len(attempts) == 1:
                raise ValueError("finalize blew up")

        task, ran = _make_task(chunks_to_run=1, finalize=finalize)

        with patch.object(task, "apply_async"):
            with self.assertRaises(ValueError):
                task(self.job.id)

        # the work completed but the failed finalization is recorded and retryable:
        # failure counted, lease released so the retry needn't wait out its expiry,
        # and needs_finalize still set so the retry finalizes before anything else
        job = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(job.status, SyncJob.STATUS_FAILED)
        self.assertEqual(job.consecutive_failures, 1)
        self.assertTrue(job.needs_finalize)
        self.assertIsNone(job.lease_owner)

        with patch.object(task, "apply_async"):
            task(self.job.id)

        # the retry runs the leftover finalization first, then its own completion's -
        # at-least-once semantics, which is why finalize hooks must be idempotent
        self.assertEqual(len(attempts), 3)
        job = SyncJob.objects.get(id=self.job.id)
        self.assertFalse(job.needs_finalize)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.consecutive_failures, 0)

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
        self.assertEqual(SyncJob.objects.get(id=self.job.id).status, SyncJob.STATUS_COMPLETE)

    def test_missing_job_is_skipped(self):
        task, ran = _make_task(chunks_to_run=1)

        with patch.object(task, "apply_async") as mock_continue:
            task(-1)

        self.assertEqual(ran, [])
        mock_continue.assert_not_called()
