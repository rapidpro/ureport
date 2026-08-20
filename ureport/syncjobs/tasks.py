import logging
import traceback
import uuid

from celery.exceptions import MaxRetriesExceededError

from django.core.cache import cache
from django.utils import timezone

from ureport.celery import app

from .models import DEFAULT_LEASE_SECONDS, STATUS_CACHE_KEY, LeaseLost, SyncJob

logger = logging.getLogger(__name__)

# how long after a lease expires a blocked redelivery waits before retrying its claim
LEASE_RETRY_GRACE = 5

# how many problem jobs the monitor task describes in detail, counts cover the rest
MAX_REPORTED_JOBS = 50


@app.task(name="syncjobs.check_jobs")
def check_jobs():
    """
    Records the state of the sync jobs, and which of them need an operator's attention -
    abandoned by a dead worker, or failing the same way run after run. The status views
    read this rather than the jobs table, so they cost nothing per request.
    """
    now = timezone.now()

    stale = SyncJob.objects.stale().order_by("modified_on")
    failing = SyncJob.objects.failing().order_by("-consecutive_failures")

    # the detail is for humans to read, so only enough of it to work through
    stale_jobs = {f"{job.id}": job.as_status(now) for job in stale[:MAX_REPORTED_JOBS]}
    failing_jobs = {f"{job.id}": job.as_status(now) for job in failing[:MAX_REPORTED_JOBS]}

    totals = dict(
        running=SyncJob.objects.filter(status=SyncJob.STATUS_RUNNING).count(),
        stale=stale.count(),
        failing=failing.count(),
    )

    for key, job in stale_jobs.items():
        logger.warning("Job #%s (%s:%s) stale for %ss", key, job["job_type"], job["scope"], job["stale_for"])

    output = dict(
        by_type=SyncJob.count_by_type(),
        stale_jobs=stale_jobs,
        failing_jobs=failing_jobs,
        totals=totals,
        checked_on=now.isoformat(),
    )
    cache.set(STATUS_CACHE_KEY, output, None)


def chunked_task(job_type, queue="celery", lease_seconds=DEFAULT_LEASE_SECONDS, finalize=None, name=None):
    """
    Creates a Celery task that runs a SyncJob one bounded chunk at a time. The decorated
    function performs a single chunk of work: it reads its resume position from job.cursor,
    calls job.checkpoint(...) alongside its data writes, and returns True when the job has
    no work left, False (or None) to have a continuation task enqueued immediately, or a
    number of seconds to have the continuation delayed - e.g. to back off after hitting an
    API rate limit without losing the chunk's progress.

    Every caller - beat nudges, continuations, redeliveries, manual triggers - invokes the
    task the same way, with the job id. The atomic claim serializes execution: an
    invocation that finds the job under a live lease retries once shortly after the lease
    expires (so a chunk redelivered after a worker death is resumed from the last
    checkpoint rather than lost), and gives up quietly otherwise.

    The optional finalize hook runs when a run completes (e.g. rebuilding counts). It MUST
    be idempotent: it runs at least once per completed run and can run again after crashes,
    takeovers or duplicate triggers. If the worker dies between completing and finalizing,
    the job's needs_finalize flag makes the next invocation run the leftover finalization
    first - against the completed run's state, before this invocation's run touches it.
    """

    def decorator(chunk_func):
        task_name = name or f"syncjobs.{job_type}"

        @app.task(name=task_name, bind=True, queue=queue, acks_late=True, reject_on_worker_lost=True)
        def _task(self, job_id):
            job = SyncJob.objects.filter(id=job_id).first()
            if not job:
                logger.warning("Job #%s no longer exists, skipping", job_id)
                return

            # keep the pre-claim state so a leftover finalization sees the run it belongs
            # to, not the fresh run the claim below starts
            snapshot = SyncJob.objects.get(id=job_id)

            # unique per execution so two deliveries of the same message can't share a lease
            owner = f"{self.request.hostname or 'local'}:{self.request.id or 'direct'}:{uuid.uuid4().hex[:8]}"

            job = job.claim(owner, lease_seconds)
            if job is None:
                _retry_if_leased(self, job_id)
                return

            try:
                if snapshot.needs_finalize:
                    if finalize:
                        finalize(snapshot)
                    job.clear_finalize()

                done = chunk_func(job)
            except LeaseLost:
                # another worker owns the job now - drop our work, the new holder resumes
                # from the last committed checkpoint
                logger.warning("Job #%s (%s) lease lost mid chunk, discarding", job_id, job_type)
                return
            except Exception:
                job.record_failure(traceback.format_exc())
                raise

            if done is True:
                if not job.mark_complete(needs_finalize=bool(finalize)):
                    return  # job was taken over - the new holder owns finalization
                if finalize:
                    try:
                        finalize(job)
                    except Exception:
                        # record the failure so backoff engages and release the lease so
                        # the retry needn't wait out its expiry; needs_finalize stays set
                        # so the retry runs the leftover finalization before anything else
                        job.record_failure(traceback.format_exc())
                        raise
                    job.clear_finalize()
                job.release_lease()
            else:
                # a numeric return is a requested delay before the continuation (bool is
                # an int subclass, so False must be checked first)
                countdown = done if not isinstance(done, bool) and isinstance(done, (int, float)) else None

                # enqueue before releasing so a continuation that lands early retries
                # against our still-held lease instead of racing the release
                _task.apply_async((job_id,), queue=queue, countdown=countdown)
                job.release_lease()

        def _retry_if_leased(task_self, job_id):
            """
            A failed claim against a live lease may be a redelivery of a chunk whose worker
            died - the message is our only prompt to resume, so reschedule it for just
            after the lease expires instead of dropping it.
            """
            current = SyncJob.objects.filter(id=job_id).first()
            now = timezone.now()

            if (
                current
                and current.status != SyncJob.STATUS_PAUSED
                and current.lease_expires_on
                and current.lease_expires_on > now
            ):
                remaining = (current.lease_expires_on - now).total_seconds()
                try:
                    raise task_self.retry(countdown=remaining + LEASE_RETRY_GRACE, max_retries=2)
                except MaxRetriesExceededError:
                    logger.warning("Job #%s (%s) still leased after retries, giving up", job_id, job_type)
            else:
                logger.info("Job #%s (%s) not claimable, skipping", job_id, job_type)

        return _task

    return decorator
