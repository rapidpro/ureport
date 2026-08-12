# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from django.utils import timezone

from dash.orgs.models import Org, TaskState
from ureport.celery import app
from ureport.syncjobs.models import SyncJob
from ureport.syncjobs.tasks import chunked_task

logger = logging.getLogger(__name__)

ENGAGEMENT_JOB_TYPE = "engagement-refresh"
PRUNE_JOB_TYPE = "activities-prune"
REBUILD_JOB_TYPE = "activities-rebuild"

QUEUE = "slow"

# each of these is a handful of aggregate queries over the org's counters, so a chunk does
# a few of them rather than the whole product of filters, segments and metrics
ENGAGEMENT_BATCH_SIZE = 3

# the rebuild's engagement pass only covers one metric, so it can afford wider chunks
REBUILD_BATCH_SIZE = 5
REBUILD_METRIC = "active-users"

# a rebuild run recalculates the org's counters first, then refreshes what they feed
STAGE_ENGAGEMENT = "engagement"

# contact activities are kept for this long, and pruned this many rows at a time
ACTIVITY_RETENTION = timedelta(days=400)
PRUNE_BATCH_SIZE = 1000
PRUNE_BATCHES_PER_CHUNK = 20

# must comfortably exceed the slowest single chunk - a lease that expires mid chunk loses
# that chunk's work. The rebuild's first chunk is one unbounded pass over the org's
# activities, so it gets the same headroom as the contact sync's unbounded stages.
ENGAGEMENT_LEASE_SECONDS = 60 * 30
PRUNE_LEASE_SECONDS = 60 * 20
REBUILD_LEASE_SECONDS = 60 * 30

LEASE_SECONDS = {
    ENGAGEMENT_JOB_TYPE: ENGAGEMENT_LEASE_SECONDS,
    PRUNE_JOB_TYPE: PRUNE_LEASE_SECONDS,
    REBUILD_JOB_TYPE: REBUILD_LEASE_SECONDS,
}

# the task keys the pre-chunking tasks were disabled per org by, honored for the release
# they still exist in - a chunked job is stopped by pausing it instead
LEGACY_TASK_KEYS = {
    ENGAGEMENT_JOB_TYPE: "refresh-engagement-data",
    PRUNE_JOB_TYPE: "delete-old-contact-activities",
}

# how stale a job's last run may be before the dispatcher runs it again. These used to be
# fixed daily beat times, so the interval is a little under a day - the point is that each
# org gets one run a day, not that it happens at a particular hour.
DAILY_INTERVAL = timedelta(hours=20)

# a failing job backs off exponentially from this, so a deterministically broken refresh
# isn't retried on every pass the dispatcher makes
FAILURE_BACKOFF = timedelta(hours=1)
MAX_FAILURE_BACKOFF = timedelta(days=7)
MAX_BACKOFF_DOUBLINGS = 10


def engagement_combos():
    """
    The engagement data an org's refresh covers, as a deterministic list so that a cursor
    into it means the same thing to the chunk that resumes from it. A release that changes
    the metrics or segments changes the list, at worst costing one run a repeated or
    skipped combination.
    """
    from .models import PollEngagementDailyCount

    return [
        (time_filter, segment, metric)
        for time_filter in PollEngagementDailyCount.DATA_TIME_FILTERS
        for segment in PollEngagementDailyCount.DATA_SEGMENTS
        for metric in PollEngagementDailyCount.DATA_METRICS
    ]


def rebuild_combos():
    """
    The engagement data a counter rebuild invalidates, i.e. every segment and time filter of
    the metric the contact activity counters feed.
    """
    from .models import PollEngagementDailyCount

    return [
        (time_filter, segment)
        for time_filter in PollEngagementDailyCount.DATA_TIME_FILTERS
        for segment in PollEngagementDailyCount.DATA_SEGMENTS
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

    # an aborted run refreshed nothing, so there is nothing to derive from it
    if job.progress.get("aborted"):
        logger.info("Job #%d (%s) aborted, skipping finalization", job.id, ENGAGEMENT_JOB_TYPE)
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
    if not org or not org.is_active:
        return _abort_run(job, ENGAGEMENT_LEASE_SECONDS)

    combos = engagement_combos()
    index = job.cursor.get("combo_index") or 0
    batch = combos[index : index + ENGAGEMENT_BATCH_SIZE]

    for time_filter, segment, metric in batch:
        PollEngagementDailyCount.refresh_engagement_data(org, metric, segment, time_filter)
        logger.info(
            "Refreshed engagement data for org #%d, time_filter - %s, segment - %s, metric - %s",
            org.id,
            time_filter,
            segment,
            metric,
        )

    index += len(batch)
    done = index >= len(combos)

    job.checkpoint(
        cursor={} if done else {"combo_index": index},
        progress=job.add_progress(chunks=1, combos=len(batch)),
        lease_seconds=ENGAGEMENT_LEASE_SECONDS,
    )

    return done


@chunked_task(PRUNE_JOB_TYPE, queue=QUEUE, lease_seconds=PRUNE_LEASE_SECONDS, name="stats.prune_contact_activities")
def prune_contact_activities(job):
    """
    Deletes a bounded number of batches of one org's expired contact activities. The
    deletion is its own resume position - each chunk works on what is still older than the
    cutoff - so nothing has to be carried in the cursor, and a chunk replayed after a crash
    simply deletes the next rows rather than the ones already gone.
    """
    from .models import ContactActivity

    org = job.org
    if not org or not org.is_active:
        return _abort_run(job, PRUNE_LEASE_SECONDS)

    # recomputed per chunk rather than frozen for the run - it only ever moves forward, and
    # a run spanning midnight pruning a few extra hours of activities is harmless
    cutoff = timezone.now() - ACTIVITY_RETENTION

    deleted = 0
    exhausted = False

    for _ in range(PRUNE_BATCHES_PER_CHUNK):
        batch_ids = list(
            ContactActivity.objects.filter(org=org, date__lte=cutoff)
            .order_by("id")
            .values_list("id", flat=True)[:PRUNE_BATCH_SIZE]
        )
        if not batch_ids:
            exhausted = True
            break

        batch_deleted, _counts_by_model = ContactActivity.objects.filter(id__in=batch_ids).delete()
        deleted += batch_deleted

    logger.info("Deleted %d contact activities older than %s on org #%d", deleted, cutoff, org.id)

    job.checkpoint(progress=job.add_progress(chunks=1, deleted=deleted), lease_seconds=PRUNE_LEASE_SECONDS)

    return exhausted


@chunked_task(
    REBUILD_JOB_TYPE, queue=QUEUE, lease_seconds=REBUILD_LEASE_SECONDS, name="stats.rebuild_contact_activity_counts"
)
def rebuild_contact_activity_counts(job):
    """
    Rebuilds one org's contact activity counters, then refreshes the engagement data they
    feed a batch at a time. The recalculation is a single chunk - it is bounded by the org's
    activities and rewrites the counters wholesale, so splitting it would leave the counters
    visibly incomplete between chunks.
    """
    from .models import ContactActivity, PollEngagementDailyCount

    org = job.org
    if not org or not org.is_active:
        return _abort_run(job, REBUILD_LEASE_SECONDS)

    cursor = dict(job.cursor)

    if not cursor.get("stage"):
        counters = ContactActivity.recalculate_contact_activity_counts(org)

        job.checkpoint(
            cursor={"stage": STAGE_ENGAGEMENT, "combo_index": 0},
            progress=job.add_progress(chunks=1, counters=len(counters)),
            lease_seconds=REBUILD_LEASE_SECONDS,
        )
        return False

    combos = rebuild_combos()
    index = cursor.get("combo_index") or 0
    batch = combos[index : index + REBUILD_BATCH_SIZE]

    for time_filter, segment in batch:
        PollEngagementDailyCount.refresh_engagement_data(org, REBUILD_METRIC, segment, time_filter)
        logger.info(
            "Refreshed rebuilt engagement data for org #%d, time_filter - %s, segment - %s, metric - %s",
            org.id,
            time_filter,
            segment,
            REBUILD_METRIC,
        )

    index += len(batch)
    done = index >= len(combos)

    job.checkpoint(
        cursor={} if done else {"stage": STAGE_ENGAGEMENT, "combo_index": index},
        progress=job.add_progress(chunks=1, combos=len(batch)),
        lease_seconds=REBUILD_LEASE_SECONDS,
    )

    return done


TASKS = {
    ENGAGEMENT_JOB_TYPE: refresh_engagement,
    PRUNE_JOB_TYPE: prune_contact_activities,
    REBUILD_JOB_TYPE: rebuild_contact_activity_counts,
}


def _abort_run(job, lease_seconds):
    """
    Ends a run whose org went away or was deactivated, without leaving a half finished
    cursor for the next one to resume from, and marks it aborted so that finalization knows
    it isn't a completed refresh.
    """
    job.checkpoint(cursor={}, progress=job.add_progress(aborted=1), lease_seconds=lease_seconds)
    return True


def enqueue_org_job(org, job_type):
    """
    Ensures this org has a job of the given type and nudges it unless a run is already being
    worked on. Returns the job id if it was enqueued, None otherwise.
    """
    if _is_disabled(org, job_type):
        logger.info("Job type %s disabled for org #%d, skipping", job_type, org.id)
        return None

    job = SyncJob.get_or_create_job(org, job_type)

    if job.status == SyncJob.STATUS_PAUSED or _in_flight(job, timezone.now()):
        logger.info("Job #%d (%s) not nudged, %s", job.id, job_type, job.get_status_display())
        return None

    _enqueue(job)
    return job.id


def dispatch_org_stats(org):
    """
    Ensures this org's daily stats jobs exist and nudges the ones that are due. Returns the
    job types actually enqueued.
    """
    now = timezone.now()
    queued = []

    for job_type in (ENGAGEMENT_JOB_TYPE, PRUNE_JOB_TYPE):
        if _is_disabled(org, job_type):
            logger.info("Job type %s disabled for org #%d, skipping", job_type, org.id)
            continue

        job = SyncJob.get_or_create_job(org, job_type)
        if not _is_due(job, DAILY_INTERVAL, now):
            continue

        _enqueue(job)
        queued.append(job_type)

    return queued


def _enqueue(job):
    TASKS[job.job_type].apply_async((job.id,), queue=QUEUE)


def _is_disabled(org, job_type):
    task_key = LEGACY_TASK_KEYS.get(job_type)

    return bool(task_key) and TaskState.objects.filter(org=org, task_key=task_key, is_disabled=True).exists()


def _is_due(job, interval, now):
    """
    A job is due unless it is paused, a run is still moving, or its last run ended recently
    enough - for the cadence asked for, or for the backoff its failure streak has earned.
    The failure backoff matters because a job that fails deterministically would otherwise
    be retried at the dispatcher's full rate forever.
    """
    if job.status == SyncJob.STATUS_PAUSED or _in_flight(job, now):
        return False

    wait = interval
    if job.consecutive_failures:
        doublings = min(job.consecutive_failures - 1, MAX_BACKOFF_DOUBLINGS)
        wait = max(wait, min(FAILURE_BACKOFF * 2**doublings, MAX_FAILURE_BACKOFF))

    return not (job.ended_on and job.ended_on > now - wait)


def _in_flight(job, now):
    """
    Whether a run is still moving: a live lease, or a running job that checkpointed
    recently - chunks release the lease between continuations, so a healthy run looks idle
    from here while its next message waits in the queue. A running job that stopped
    checkpointing is deliberately not in flight: nudging it is how a chain that died without
    recording a failure gets picked back up.
    """
    if job.lease_expires_on and job.lease_expires_on > now:
        return True

    stale_after = now - timedelta(seconds=2 * LEASE_SECONDS[job.job_type])

    return job.status == SyncJob.STATUS_RUNNING and bool(job.modified_on) and job.modified_on > stale_after


@app.task(name="stats.stats_dispatch")
def stats_dispatch(org_id=None):
    """
    Nudges the daily stats jobs that are due. Jobs already being worked on are left to their
    own continuations, so this can run as often as the shortest cadence needs.
    """
    orgs = Org.objects.filter(is_active=True)
    if org_id:
        orgs = orgs.filter(id=org_id)

    for org in orgs:
        try:
            dispatch_org_stats(org)
        except Exception:
            logger.error("Error dispatching stats jobs for org #%d" % org.pk, exc_info=True)
