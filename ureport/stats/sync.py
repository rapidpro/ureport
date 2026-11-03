# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from django.utils import timezone

from dash.orgs.models import Org, TaskState
from ureport.celery import app
from ureport.syncjobs.dispatch import Backoff, enqueue, in_flight, is_due
from ureport.syncjobs.models import DEFAULT_LEASE_SECONDS, SyncJob
from ureport.syncjobs.tasks import JOB_TASKS, chunked_task

logger = logging.getLogger(__name__)

ENGAGEMENT_JOB_TYPE = "engagement-refresh"

QUEUE = "slow"

# each of these is a handful of aggregate queries over the org's counters, so a chunk does
# a few of them rather than the whole product of segments and metrics
ENGAGEMENT_BATCH_SIZE = 3

# must comfortably exceed the slowest single chunk - a lease that expires mid chunk loses
# that chunk's work
ENGAGEMENT_LEASE_SECONDS = 60 * 30

# the task keys the pre-chunking tasks were disabled per org by, honored for the release
# they still exist in - a chunked job is stopped by pausing it instead
LEGACY_TASK_KEYS = {
    ENGAGEMENT_JOB_TYPE: "refresh-engagement-data",
}

# how often a run of these jobs should start. A little under a day, so that a run which
# starts late doesn't push the next one out to the following night.
DAILY_INTERVAL = timedelta(hours=20)

# a failing job backs off exponentially from its normal cadence, so a deterministically
# broken refresh isn't retried every night forever: 20h, 40h, 80h, 160h, then the cap
FAILURE_BACKOFF = Backoff(base=DAILY_INTERVAL, cap=timedelta(days=7), max_doublings=4)

# the dispatcher spreads the orgs' runs over this many seconds rather than starting them all
# at once, to flatten the load of the nightly refresh. _recently_nudged trusts a delayed
# nudge for this long on top of its usual window, so the next pass doesn't queue another.
DISPATCH_SPREAD_SECONDS = 60 * 30


def engagement_combos():
    """
    The engagement data an org's refresh covers, as a deterministic list so that a cursor
    into it means the same thing to the chunk that resumes from it. Each combination is
    refreshed for every time filter at once, as they are all derived from the same counts.
    A release that changes the metrics or segments changes the list, which is why the
    cursor carries its length - see _resume_index.
    """
    from .models import PollEngagementDailyCount

    return [
        (segment, metric)
        for segment in PollEngagementDailyCount.DATA_SEGMENTS
        for metric in PollEngagementDailyCount.DATA_METRICS
    ]


def finalize_engagement_refresh(job):
    """
    Runs once per completed refresh: the average response rate is derived from the same
    counters, so it is recalculated when they have all been refreshed. Idempotent - it
    recomputes from the counters and overwrites its cached value.
    """
    from .models import PollStatsCounter

    org = job.org
    if not org:
        return

    PollStatsCounter.calculate_average_response_rate(org)


@chunked_task(
    ENGAGEMENT_JOB_TYPE,
    queue=QUEUE,
    lease_seconds=ENGAGEMENT_LEASE_SECONDS,
    finalize=finalize_engagement_refresh,
    name="stats.refresh_engagement",
)
def refresh_engagement(job):
    """
    Refreshes a batch of one org's engagement data. The cursor is the position reached in
    the combination list, and is reset by the chunk that finishes it so that the next run
    starts a fresh pass rather than resuming past the end of the last one.
    """
    from .models import PollEngagementDailyCount

    org = job.org
    if _should_stop(org, job.job_type):
        return job.abort()

    combos = engagement_combos()
    index = _resume_index(job.cursor, len(combos))
    batch = combos[index : index + ENGAGEMENT_BATCH_SIZE]

    for segment, metric in batch:
        PollEngagementDailyCount.refresh_engagement_data(org, metric, segment)
        logger.info("Refreshed engagement data for org #%d, segment - %s, metric - %s", org.id, segment, metric)

    index += len(batch)
    done = index >= len(combos)

    job.checkpoint(
        cursor={} if done else {"combo_index": index, "combo_count": len(combos)},
        progress=job.add_progress(chunks=1, combos=len(batch)),
    )

    return done


def _should_stop(org, job_type):
    """
    Whether the run has nothing left to do for this org: it went away, was deactivated, or
    had this work disabled. Checked by every chunk rather than only at enqueue, so that a
    disable lands on the run in flight instead of a dozen continuations later.
    """
    return not org or not org.is_active or _is_disabled(org, job_type)


def _resume_index(cursor, combo_count):
    """
    Where in the combination list a chunk picks up. A bare index means nothing once the list
    changes under a run - a release that adds or removes a metric would leave the rest of
    the pass pointing at the wrong combinations, silently skipping a contiguous tail of them
    - so the length it was taken against is checkpointed with it and a mismatch starts the
    pass over. One repeated pass is cheaper than stale data nobody notices.
    """
    if cursor.get("combo_count") != combo_count:
        return 0

    return cursor.get("combo_index") or 0


def enqueue_org_job(org, job_type):
    """
    Ensures this org has a job of the given type and nudges it unless a run is already being
    worked on. Unlike the dispatcher this ignores the cadence - it is someone asking for a
    run now. Returns the job id if it was enqueued, None otherwise.
    """
    if _is_disabled(org, job_type):
        logger.info("Job type %s disabled for org #%d, skipping", job_type, org.id)
        return None

    # a job created here has never been enqueued, which the check below can't tell on its
    # own - a pending row looks the same whether its message is on the queue or was never sent
    job, created = SyncJob.objects.get_or_create(org=org, job_type=job_type)

    if not created and (job.status == SyncJob.STATUS_PAUSED or in_flight(job, timezone.now(), include_pending=True)):
        logger.info("Job #%d (%s) not nudged, %s", job.id, job_type, job.get_status_display())
        return None

    _enqueue(job)
    return job.id


def dispatch_org_stats(org, countdown=None):
    """
    Ensures this org's daily stats jobs exist and nudges the ones that are due, delayed by the
    given number of seconds. Returns the job types actually enqueued.
    """
    now = timezone.now()
    queued = []

    for job_type in (ENGAGEMENT_JOB_TYPE,):
        if _is_disabled(org, job_type):
            logger.info("Job type %s disabled for org #%d, skipping", job_type, org.id)
            continue

        job, created = SyncJob.objects.get_or_create(org=org, job_type=job_type)
        if not created and not _should_nudge(job, now):
            continue

        _enqueue(job, countdown=countdown)
        queued.append(job_type)

    return queued


def _should_nudge(job, now):
    """
    Whether the dispatcher queues a chunk of this job: nothing is already working on it or
    queued for it, and the shared cadence and failure backoff say it is due.
    """
    if in_flight(job, now, include_pending=True) or _recently_nudged(job, now):
        return False

    return is_due(job, now, interval=DAILY_INTERVAL, backoff=FAILURE_BACKOFF)


def _recently_nudged(job, now):
    """
    Whether the row was touched after its last run ended, which for a job that isn't running
    means a message was queued for it and hasn't been picked up yet. A job keeps the status
    of its last run until a worker claims the nudge, so in_flight can't see this one - and
    without it the dispatcher would queue another message on every pass until one is. The
    window is the one in_flight allows a running job plus the longest delay the dispatcher
    gives a nudge, so a nudge is trusted for as long as a chunk of this job may take to
    start moving once its delay is up.
    """
    if not job.ended_on or not job.modified_on or job.modified_on <= job.ended_on:
        return False

    lease_seconds = getattr(JOB_TASKS.get(job.job_type), "lease_seconds", DEFAULT_LEASE_SECONDS)

    return job.modified_on > now - timedelta(seconds=2 * lease_seconds + DISPATCH_SPREAD_SECONDS)


def _enqueue(job, countdown=None):
    enqueue(job, countdown=countdown)

    # nothing writes to the row until a worker claims it, so record the nudge - it is what
    # tells the next pass that this job already has a message on the queue
    now = timezone.now()
    SyncJob.objects.filter(id=job.id).update(modified_on=now)
    job.modified_on = now


def _is_disabled(org, job_type):
    task_key = LEGACY_TASK_KEYS.get(job_type)

    return bool(task_key) and TaskState.objects.filter(org=org, task_key=task_key, is_disabled=True).exists()


@app.task(name="stats.stats_dispatch")
def stats_dispatch(org_id=None):
    """
    Nudges the daily stats jobs that are due. Jobs already being worked on, or already
    queued, are left alone, so beat can run this on every slot of its nightly window - the
    first slot starts the orgs that are due and the rest are retry slots for the ones whose
    run failed or was interrupted.
    """
    orgs = Org.objects.filter(is_active=True).order_by("id")
    if org_id:
        orgs = orgs.filter(id=org_id)
    orgs = list(orgs)

    for i, org in enumerate(orgs):
        try:
            dispatch_org_stats(org, countdown=(i * DISPATCH_SPREAD_SECONDS // len(orgs)) or None)
        except Exception:
            logger.error("Error dispatching stats jobs for org #%d" % org.pk, exc_info=True)
