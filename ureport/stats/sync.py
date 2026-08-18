# -*- coding: utf-8 -*-

import logging
from contextlib import contextmanager
from datetime import timedelta

from django_valkey import get_valkey_connection
from valkey.exceptions import LockError

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

# the counter rebuild replaces every counter an org has and they carry no unique constraint,
# so two rebuilds running at once leave the org's counts permanently doubled - which the
# squash task then merges into plausible looking data. The lease alone doesn't prevent that:
# a redelivered message becomes claimable the moment the lease expires, while the original
# chunk may still be running. So the recalculation takes a lock whose timeout comfortably
# outlives both the lease and the broker's redelivery window.
REBUILD_LOCK_KEY = "rebuild-contacts-activities-counts"
REBUILD_LOCK_TIMEOUT = REBUILD_LEASE_SECONDS * 4

# how long to wait before trying the recalculation again when another worker holds its lock
LOCK_BACKOFF = 300

# the task keys the pre-chunking tasks were disabled per org by, honored for the release
# they still exist in - a chunked job is stopped by pausing it instead
LEGACY_TASK_KEYS = {
    ENGAGEMENT_JOB_TYPE: "refresh-engagement-data",
    PRUNE_JOB_TYPE: "delete-old-contact-activities",
}

# how stale a job's last run may be before the dispatcher runs it again. A little under a
# day, so that a run which started late doesn't push the next one out to the following night.
DAILY_INTERVAL = timedelta(hours=20)

# a failing job backs off exponentially from its normal cadence, so a deterministically
# broken refresh isn't retried every night forever: 20h, 40h, 80h, 160h, then the cap
FAILURE_BACKOFF = DAILY_INTERVAL
MAX_FAILURE_BACKOFF = timedelta(days=7)
MAX_BACKOFF_DOUBLINGS = 4


def engagement_combos():
    """
    The engagement data an org's refresh covers, as a deterministic list so that a cursor
    into it means the same thing to the chunk that resumes from it. A release that changes
    the metrics or segments changes the list, which is why the cursor carries its length -
    see _resume_index.
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
    if _should_stop(org, job.job_type):
        return _abort_run(job, ENGAGEMENT_LEASE_SECONDS)

    combos = engagement_combos()
    index = _resume_index(job.cursor, len(combos))
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
        cursor={} if done else {"combo_index": index, "combo_count": len(combos)},
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
    if _should_stop(org, job.job_type):
        return _abort_run(job, PRUNE_LEASE_SECONDS)

    # recomputed per chunk rather than frozen for the run - it only ever moves forward, and
    # a run spanning midnight pruning a few extra hours of activities is harmless
    cutoff = timezone.now() - ACTIVITY_RETENTION

    deleted = 0
    exhausted = False

    for _ in range(PRUNE_BATCHES_PER_CHUNK):
        # unordered - which expired activities go first doesn't matter, and asking for an
        # order would only cost a sort
        batch_ids = list(
            ContactActivity.objects.filter(org=org, date__lte=cutoff).values_list("id", flat=True)[:PRUNE_BATCH_SIZE]
        )
        if not batch_ids:
            exhausted = True
            break

        ContactActivity.objects.filter(id__in=batch_ids).delete()
        deleted += len(batch_ids)

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
    visibly incomplete between chunks - and it holds a lock while it does, as two of them at
    once would double the org's counts rather than replace them.
    """
    from .models import ContactActivity, PollEngagementDailyCount

    org = job.org
    if _should_stop(org, job.job_type):
        return _abort_run(job, REBUILD_LEASE_SECONDS)

    cursor = dict(job.cursor)

    if not cursor.get("stage"):
        with _rebuild_lock(org) as acquired:
            if not acquired:
                logger.info("Rebuild lock held for org #%d, backing off", org.id)
                job.checkpoint(progress=job.add_progress(lock_backoffs=1), lease_seconds=REBUILD_LEASE_SECONDS)
                return LOCK_BACKOFF

            counters = ContactActivity.recalculate_contact_activity_counts(org)

            job.checkpoint(
                cursor={"stage": STAGE_ENGAGEMENT, "combo_index": 0, "combo_count": len(rebuild_combos())},
                progress=job.add_progress(chunks=1, counters=len(counters)),
                lease_seconds=REBUILD_LEASE_SECONDS,
            )

        return False

    combos = rebuild_combos()
    index = _resume_index(cursor, len(combos))
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
        cursor={} if done else {"stage": STAGE_ENGAGEMENT, "combo_index": index, "combo_count": len(combos)},
        progress=job.add_progress(chunks=1, combos=len(batch)),
        lease_seconds=REBUILD_LEASE_SECONDS,
    )

    return done


TASKS = {
    ENGAGEMENT_JOB_TYPE: refresh_engagement,
    PRUNE_JOB_TYPE: prune_contact_activities,
    REBUILD_JOB_TYPE: rebuild_contact_activity_counts,
}


@contextmanager
def _rebuild_lock(org):
    """
    Takes this org's counter rebuild lock for the duration of one recalculation, yielding
    whether it was taken. Never blocks - a chunk that can't have it backs off rather than
    tying up a worker.
    """
    lock = get_valkey_connection().lock(TaskState.get_lock_key(org, REBUILD_LOCK_KEY), timeout=REBUILD_LOCK_TIMEOUT)
    acquired = lock.acquire(blocking=False)

    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except LockError:
                # the chunk outlived the lock's timeout - don't let that fail an otherwise
                # successful chunk or mask an in-flight exception
                logger.warning("Unable to release rebuild lock for org #%d as it is no longer owned", org.id)


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


def _abort_run(job, lease_seconds):
    """
    Ends a run that has nothing left to do - see _should_stop - without leaving a half
    finished cursor for the next one to resume from, and marks it aborted so that
    finalization knows it isn't a completed refresh.
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

    job, created = _ensure_job(org, job_type)

    if not created and (job.status == SyncJob.STATUS_PAUSED or _in_flight(job, timezone.now())):
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

        job, created = _ensure_job(org, job_type)
        if not created and not _is_due(job, DAILY_INTERVAL, now):
            continue

        _enqueue(job)
        queued.append(job_type)

    return queued


def _ensure_job(org, job_type):
    """
    Returns this org's job of the given type and whether it had to be created. A job created
    here has never been enqueued, which the checks against nudging it can't tell on their own
    - a pending row looks the same whether its message is on the queue or was never sent.
    """
    return SyncJob.objects.get_or_create(org=org, job_type=job_type)


def _enqueue(job):
    TASKS[job.job_type].apply_async((job.id,), queue=QUEUE)

    # nothing writes to the row until a worker claims it, so record the nudge - it is what
    # tells the next pass that a pending job already has a message on the queue
    now = timezone.now()
    SyncJob.objects.filter(id=job.id).update(modified_on=now)
    job.modified_on = now


def _is_disabled(org, job_type):
    task_key = LEGACY_TASK_KEYS.get(job_type)

    return bool(task_key) and TaskState.objects.filter(org=org, task_key=task_key, is_disabled=True).exists()


def _is_due(job, interval, now):
    """
    A job is due unless it is paused, a run is still moving or waiting to be picked up, or
    its last run ended recently enough - for the cadence asked for, or for the backoff its
    failure streak has earned. The failure backoff matters because a job that fails
    deterministically would otherwise be retried at the dispatcher's full rate forever.
    """
    if job.status == SyncJob.STATUS_PAUSED or _in_flight(job, now) or _recently_nudged(job, now):
        return False

    wait = interval
    if job.consecutive_failures:
        doublings = min(job.consecutive_failures - 1, MAX_BACKOFF_DOUBLINGS)
        wait = max(wait, min(FAILURE_BACKOFF * 2**doublings, MAX_FAILURE_BACKOFF))

    return not (job.ended_on and job.ended_on > now - wait)


def _in_flight(job, now):
    """
    Whether a run is already being driven: a live lease, a running job that checkpointed
    recently, or a pending one whose first message hasn't been picked up yet. Chunks release
    the lease between continuations, so a healthy run looks idle from here while its next
    message waits in the queue - and so does a job nobody has claimed yet. Nudging either
    only duplicates a message, and a surplus one landing after the run completes starts a
    whole fresh pass.

    A job that stopped moving entirely is deliberately not in flight: nudging it is how a
    chain that died without recording a failure, or a message the broker lost, gets picked
    back up.
    """
    if job.lease_expires_on and job.lease_expires_on > now:
        return True

    if not _recently_touched(job, now):
        return False

    return job.status in (SyncJob.STATUS_RUNNING, SyncJob.STATUS_PENDING)


def _recently_nudged(job, now):
    """
    Whether the row was touched after its last run ended, which for a job that isn't running
    means a message was queued for it and hasn't been picked up yet. The dispatcher waits
    that out rather than queueing another on its next pass - unlike an explicit trigger,
    which is someone asking for a run now and only defers to one actually in flight.
    """
    return bool(job.ended_on) and job.modified_on > job.ended_on and _recently_touched(job, now)


def _recently_touched(job, now):
    """
    Whether anything has happened to this job lately - a claim, a checkpoint, or a nudge -
    measured generously enough that a chunk taking its whole lease still counts.
    """
    stale_after = now - timedelta(seconds=2 * LEASE_SECONDS[job.job_type])

    return bool(job.modified_on) and job.modified_on > stale_after


@app.task(name="stats.stats_dispatch")
def stats_dispatch(org_id=None):
    """
    Nudges the daily stats jobs that are due. Jobs already being worked on, or already
    queued, are left alone, so beat can run this on every slot of its nightly window - the
    first slot starts the orgs that are due and the rest are retry slots for the ones whose
    run failed or was interrupted.
    """
    orgs = Org.objects.filter(is_active=True)
    if org_id:
        orgs = orgs.filter(id=org_id)

    for org in orgs:
        try:
            dispatch_org_stats(org)
        except Exception:
            logger.error("Error dispatching stats jobs for org #%d" % org.pk, exc_info=True)
