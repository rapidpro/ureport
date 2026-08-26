"""
Plumbing for testing sync jobs: the arrange code every app that runs them needs - putting a
job into a given state, and driving its task the way a worker would, one chunk per delivery
with the continuation enqueue captured rather than executed.
"""

import uuid
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from django_valkey import get_valkey_connection

from django.utils import timezone

from .models import SyncJob
from .tasks import JOB_TASKS, chunked_task

DEFAULT_MAX_CHUNKS = 20

# tells apart "leave this as it is" from an explicitly asked for null
UNSET = object()


def make_task(chunks_to_run, finalize=None, fail_on_chunk=None, job_type="test-sync", queue="testq"):
    """
    Builds a chunked task that pretends to have the given number of chunks of work,
    recording each chunk it runs. Returns the task and the list it records into.
    """
    ran = []

    # a test's task stands in for whatever else runs this job type, which the registry
    # otherwise refuses - SyncJobTestMixin puts back what was registered before the test
    JOB_TASKS.pop(job_type, None)

    @chunked_task(job_type, queue=queue, finalize=finalize, name=f"test.sync.{uuid.uuid4().hex}")
    def sync_test(job):
        chunk = job.cursor.get("chunk", 0)
        if fail_on_chunk is not None and chunk == fail_on_chunk:
            raise ValueError(f"failing on chunk {chunk}")

        ran.append(chunk)
        job.checkpoint(cursor={"chunk": chunk + 1}, progress=job.add_progress(chunks=1))
        return chunk + 1 >= chunks_to_run

    return sync_test, ran


def run_task(task, job_id, times=1):
    """
    Runs the task the given number of times, as a worker would with each delivery. Returns
    the patched apply_async, i.e. the continuations those runs asked for.
    """
    with patch.object(task, "apply_async") as mock_enqueue:
        for _ in range(times):
            task(job_id)

    return mock_enqueue


def run_to_completion(task, job_id, max_chunks=DEFAULT_MAX_CHUNKS):
    """
    Drives the job until a run of it completes, returning how many chunks that took. Fails
    rather than looping forever on a job that never finishes, and rather than passing off
    the other ways a chunk can stop asking for a continuation - a lost lease, a pause - as
    a completed run.
    """
    with patch.object(task, "apply_async") as mock_enqueue:
        for chunks in range(1, max_chunks + 1):
            asked_for = mock_enqueue.call_count
            task(job_id)

            if mock_enqueue.call_count == asked_for:
                job = SyncJob.objects.get(id=job_id)
                if job.status != SyncJob.STATUS_COMPLETE or job.needs_finalize or job.lease_owner:
                    raise AssertionError(f"job #{job_id} stopped without completing its run: {job}")

                return chunks

    raise AssertionError(f"job #{job_id} still not done after {max_chunks} chunks")


def reload(job):
    """
    The job as it now is in the database, leaving the caller's own copy alone.
    """
    return SyncJob.objects.get(id=job.id)


def hold_lease(job, owner="worker-1", seconds=600):
    """
    Puts a live lease on the job without claiming it, i.e. someone else is working on it.
    """
    return _update(job, lease_owner=owner, lease_expires_on=timezone.now() + timedelta(seconds=seconds))


def expire_lease(job, seconds_ago=1):
    """
    Expires the lease the job holds, as if its worker died mid chunk.
    """
    return _update(job, lease_expires_on=timezone.now() - timedelta(seconds=seconds_ago))


def drop_lease(job):
    """
    Drops the job's lease without going through its holder, i.e. the between chunks state.
    """
    return _update(job, lease_owner=None, lease_expires_on=None)


def make_stale(job, seconds_ago):
    """
    Backdates when the job was last touched, i.e. it stopped checkpointing that long ago.
    """
    return _update(job, modified_on=timezone.now() - timedelta(seconds=seconds_ago))


def end_run(job, status=SyncJob.STATUS_COMPLETE, ended_on=None, started_on=UNSET, failures=None, **updates):
    """
    Leaves the job as a run that ended - completed by default, failed with a streak of that
    many failures when failures is given - which is the state a dispatcher reads a cadence
    and a backoff from. A run that ended has started, so started_on defaults to when it
    ended: pass one to give the run a length, or None for a row nothing ever claimed.
    """
    ended_on = ended_on or timezone.now()
    if failures is not None:
        updates["consecutive_failures"] = failures

    return _update(
        job, status=status, started_on=ended_on if started_on is UNSET else started_on, ended_on=ended_on, **updates
    )


@contextmanager
def held_lock(key, timeout=60):
    """
    Holds a lock for the duration of the block, i.e. something else has it.
    """
    lock = get_valkey_connection().lock(key, timeout=timeout)
    if not lock.acquire(blocking=False):
        raise AssertionError(f"lock {key} is already held")

    try:
        yield lock
    finally:
        lock.release()


def _update(job, **updates):
    SyncJob.objects.filter(id=job.id).update(**updates)
    job.refresh_from_db()

    return job


class SyncJobTestMixin:
    """
    Assertions and patching helpers for tests that drive sync jobs.
    """

    def setUp(self):
        super().setUp()

        # the task registry is process wide, so a test declaring its own tasks would
        # otherwise leave them running the job types of every test after it
        registered = dict(JOB_TASKS)
        self.addCleanup(self._restore_job_tasks, registered)

    def _restore_job_tasks(self, registered):
        JOB_TASKS.clear()
        JOB_TASKS.update(registered)

    def assertJobState(self, job, **expected):
        """
        Asserts the given fields of the job as it now is in the database.
        """
        current = reload(job)

        for field, value in expected.items():
            self.assertEqual(getattr(current, field), value, f"unexpected {field} on job #{job.id}")

        return current

    def start_patch(self, patcher):
        """
        Starts a patcher for the duration of the test, returning its mock.
        """
        mock = patcher.start()
        self.addCleanup(patcher.stop)

        return mock
