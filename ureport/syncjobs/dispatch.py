from collections import namedtuple
from datetime import timedelta

from .models import DEFAULT_LEASE_SECONDS, SyncJob
from .tasks import JOB_TASKS

# an exponential wait after a failure: the first one waits base, each further one doubles it
# up to max_doublings times, and none of them waits longer than cap
Backoff = namedtuple("Backoff", ("base", "cap", "max_doublings"))


def enqueue(job, countdown=None):
    """
    Asks for a chunk of this job to run, on the queue its task is declared with. Enqueueing
    is all a trigger does - the task itself decides whether the job is claimable.
    """
    task = JOB_TASKS.get(job.job_type)
    if task is None:
        raise KeyError(f"no task registered for job type '{job.job_type}' - is the module declaring it imported?")

    options = dict(queue=task.queue)
    if countdown is not None:
        options["countdown"] = countdown

    task.apply_async((job.id,), **options)


def is_due(job, now, *, interval=None, backoff=None):
    """
    Whether a dispatcher should nudge this job: it isn't paused, no run is already moving,
    and enough time has passed since its last run - the cadence asked for, an interval of
    None meaning any run that isn't moving is due, or the wait its failure streak has
    earned. The failure backoff matters because a job that fails deterministically would
    otherwise be retried on every pass.
    """
    if job.status == SyncJob.STATUS_PAUSED or in_flight(job, now):
        return False

    if backoff and job.consecutive_failures:
        # a wait after the failure rather than a cadence, so it is measured from the end of
        # the run that failed - and never lets a job be retried faster than its own cadence,
        # which a run long enough to outlast that cadence would otherwise do
        doublings = min(job.consecutive_failures - 1, backoff.max_doublings)
        wait = min(backoff.base * 2**doublings, backoff.cap)
        if interval:
            wait = max(wait, interval)

        return not (job.ended_on and job.ended_on > now - wait)

    # the cadence is how often a run should start, so it is measured from the last start. A
    # run that never ended isn't waited out at all: there is nothing to schedule the next one
    # from, and nudging is how a chain that died without recording a failure is picked up
    if interval and job.ended_on:
        # a job that ended without ever starting only comes out of a fixture, but the fall
        # back keeps one from being read as never having run at all
        anchor = job.started_on or job.ended_on
        if anchor > now - interval:
            return False

    return True


def in_flight(job, now, *, include_pending=False):
    """
    Whether a run is already being driven, so that nudging it would only start a duplicate
    chain of chunks: a live lease, or a running job that checkpointed recently - chunks
    release the lease between continuations, so a healthy run looks idle from here while its
    next message waits in the queue.

    A running job that stopped checkpointing is deliberately not in flight: nudging it is how
    a chain that died without recording a failure gets picked back up.

    With include_pending, a job that hasn't run yet but was touched recently counts too -
    for callers whose enqueue records the nudge, where a fresh modified_on means a message
    is already on the queue. A job whose row was only just created has never been nudged
    though, and its caller has to tell those two apart itself - get_or_create's created flag
    is what does it.
    """
    if job.lease_expires_on and job.lease_expires_on > now:
        return True

    if not _recently_touched(job, now):
        return False

    statuses = (SyncJob.STATUS_RUNNING, SyncJob.STATUS_PENDING) if include_pending else (SyncJob.STATUS_RUNNING,)

    return job.status in statuses


def _recently_touched(job, now):
    """
    Whether anything has happened to this job lately - a claim, a checkpoint, or a nudge -
    measured generously enough that a chunk taking its whole lease still counts.
    """
    task = JOB_TASKS.get(job.job_type)
    lease_seconds = getattr(task, "lease_seconds", DEFAULT_LEASE_SECONDS)

    return bool(job.modified_on) and job.modified_on > now - timedelta(seconds=2 * lease_seconds)
