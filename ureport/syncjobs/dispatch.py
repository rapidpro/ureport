import zlib
from collections import namedtuple
from datetime import datetime, timedelta, timezone as tzone

from .models import DEFAULT_LEASE_SECONDS, SyncJob
from .tasks import JOB_TASKS

# an exponential wait after a failure: the first one waits base, each further one doubles it
# up to max_doublings times, and none of them waits longer than cap
Backoff = namedtuple("Backoff", ("base", "cap", "max_doublings"))

# what the periods of a phased cadence are counted from
PERIOD_EPOCH = datetime(2000, 1, 1, tzinfo=tzone.utc)

# the most a phased job waits after a run before it can be due again, however long its cadence
PHASED_RERUN_GAP = timedelta(hours=1)


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


def spread_phase(key, interval):
    """
    A fixed offset into the interval for the given key, so that jobs on the same cadence
    have their periods start at different times rather than all at once.
    """
    return timedelta(seconds=zlib.crc32(key.encode()) % int(interval.total_seconds()))


def period_start(now, interval, phase):
    """
    The start of the period of the given cadence and phase that now falls in.
    """
    return now - (now - PERIOD_EPOCH - phase) % interval


def is_due(job, now, *, interval=None, phase=None, backoff=None):
    """
    Whether a dispatcher should nudge this job: it isn't paused, no run is already moving,
    and enough time has passed since its last run - the cadence asked for, an interval of
    None meaning any run that isn't moving is due, or the wait its failure streak has
    earned. The failure backoff matters because a job that fails deterministically would
    otherwise be retried on every pass.

    Without a phase the cadence is measured from the last start, so a dispatcher that only
    looks every so often runs the job up to one of its passes late, and the next run is
    measured from that late start - the job's start time walks later by up to a pass every
    period. With a phase the job is instead due once per fixed period, from that period's
    start, so it runs on the first pass after it whenever the last run happened to start.
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

    # the cadence is how often a run should start, so it is measured from the last start, or
    # from the period's start with a phase. A run that never ended isn't waited out at all:
    # there is nothing to schedule the next one from, and nudging is how a chain that died
    # without recording a failure is picked up
    if interval and job.ended_on:
        # a job that ended without ever starting only comes out of a fixture, but the fall
        # back keeps one from being read as never having run at all
        anchor = job.started_on or job.ended_on

        if phase is None:
            if anchor > now - interval:
                return False

        # a run that started late in the last period, near the start of this one, doesn't
        # make the job due again straight away. The gap is kept short, as every job whose
        # period started within it is held back until it passes - jobs that last ran
        # together, after an outage say, would otherwise all be released at once again
        elif anchor >= period_start(now, interval, phase) or anchor > now - min(interval / 2, PHASED_RERUN_GAP):
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
