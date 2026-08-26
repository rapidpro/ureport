# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from django.utils import timezone

from dash.orgs.models import Org, TaskState
from ureport.celery import app
from ureport.syncjobs.dispatch import Backoff, enqueue, in_flight, is_due
from ureport.syncjobs.locks import chunk_lock
from ureport.syncjobs.models import DEFAULT_LEASE_SECONDS, SyncJob
from ureport.syncjobs.tasks import JOB_TASKS, chunked_task

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

# how often a run of these jobs should start. A little under a day, so that a run which
# starts late doesn't push the next one out to the following night.
DAILY_INTERVAL = timedelta(hours=20)

# a failing job backs off exponentially from its normal cadence, so a deterministically
# broken refresh isn't retried every night forever: 20h, 40h, 80h, 160h, then the cap
FAILURE_BACKOFF = Backoff(base=DAILY_INTERVAL, cap=timedelta(days=7), max_doublings=4)


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
        return job.abort()

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

    job.checkpoint(progress=job.add_progress(chunks=1, deleted=deleted))

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
        return job.abort()

    cursor = dict(job.cursor)

    if not cursor.get("stage"):
        with _rebuild_lock(org) as acquired:
            if not acquired:
                logger.info("Rebuild lock held for org #%d, backing off", org.id)
                return job.back_off(LOCK_BACKOFF, lock_backoffs=1)

            counters = ContactActivity.recalculate_contact_activity_counts(org)

            job.checkpoint(
                cursor={"stage": STAGE_ENGAGEMENT, "combo_index": 0, "combo_count": len(rebuild_combos())},
                progress=job.add_progress(chunks=1, counters=len(counters)),
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
    )

    return done


def _rebuild_lock(org):
    """
    Serializes one org's counter recalculation, which two workers at once would double
    rather than replace - see REBUILD_LOCK_TIMEOUT. Held for the chunk that does the
    recalculation, not for the whole run.
    """
    return chunk_lock(TaskState.get_lock_key(org, REBUILD_LOCK_KEY), REBUILD_LOCK_TIMEOUT)


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

        job, created = SyncJob.objects.get_or_create(org=org, job_type=job_type)
        if not created and not _should_nudge(job, now):
            continue

        _enqueue(job)
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
    window is the one in_flight allows a running job, so a nudge is trusted for as long as
    a chunk of this job may take to start moving.
    """
    if not job.ended_on or not job.modified_on or job.modified_on <= job.ended_on:
        return False

    lease_seconds = getattr(JOB_TASKS.get(job.job_type), "lease_seconds", DEFAULT_LEASE_SECONDS)

    return job.modified_on > now - timedelta(seconds=2 * lease_seconds)


def _enqueue(job):
    enqueue(job)

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
    orgs = Org.objects.filter(is_active=True)
    if org_id:
        orgs = orgs.filter(id=org_id)

    for org in orgs:
        try:
            dispatch_org_stats(org)
        except Exception:
            logger.error("Error dispatching stats jobs for org #%d" % org.pk, exc_info=True)
