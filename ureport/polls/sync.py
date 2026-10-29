# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from dash.orgs.models import Org
from ureport.celery import app
from ureport.syncjobs.dispatch import Backoff, enqueue, in_flight, is_due
from ureport.syncjobs.locks import chunk_lock
from ureport.syncjobs.models import SyncJob
from ureport.syncjobs.tasks import chunked_task

logger = logging.getLogger(__name__)

RESULTS_JOB_TYPE = "poll-results"
ARCHIVES_JOB_TYPE = "poll-archives"
COUNTS_JOB_TYPE = "counts-rebuild"
PRUNE_JOB_TYPE = "poll-results-prune"
AGE_GENDER_JOB_TYPE = "age-gender-backfill"

SYNC_QUEUE = "sync"
SLOW_QUEUE = "slow"

# a results chunk is a bounded number of API pages, an archives chunk a single archive file
RESULTS_LEASE_SECONDS = 60 * 30
ARCHIVES_LEASE_SECONDS = 60 * 60 * 2

# a maintenance chunk is a handful of polls, but one poll's rebuild or its results delete
# can take a while on a big flow
MAINTENANCE_LEASE_SECONDS = 60 * 30

# how long to wait before the next chunk when the backend exhausted its rate limit
RATE_LIMITED_BACKOFF = 300

# counts are rebuilt this often mid-run so a long first sync still reaches the public site
REBUILD_COUNTS_EVERY = 5

# progress marker for an archives cursor reset that couldn't be applied yet, and how long a
# results run that is otherwise done waits before trying it again
ARCHIVES_RESET_PENDING = "archives_reset_pending"
ARCHIVES_RESET_BACKOFF = 300

# counters that mean a run actually changed results, i.e. counts are worth rebuilding
RESULT_CHANGE_KEYS = ("num_val_created", "num_val_updated", "num_path_created", "num_path_updated")

# how stale a job's last run may be before the dispatcher runs it again
MAIN_POLL_INTERVAL = timedelta(minutes=20)
RECENT_POLLS_INTERVAL = timedelta(hours=1)
OTHER_POLLS_INTERVAL = timedelta(hours=24)

# a failing job backs off exponentially, so a deterministically broken sync isn't retried at
# the dispatcher's full rate
FAILURE_BACKOFF = Backoff(base=timedelta(minutes=20), cap=timedelta(hours=24), max_doublings=10)

# other polls created this recently are covered by the recent polls cadence
OTHER_POLLS_NEW_WINDOW = timedelta(days=7)

# how stale a maintenance job's last run may be before its daily beat entry runs it again,
# left short of a day so a run that started late isn't skipped the next day
MAINTENANCE_INTERVAL = timedelta(hours=20)

# the counts rebuild only rebuilds polls whose results changed since their counts were, but each poll also gets a
# full rebuild on one night out of this many, picked by its pk so those are spread across nights. That reconciles
# what doesn't come with a results change, like edited questions or results updated outside a sync
COUNTS_FULL_REBUILD_DAYS = 7

# on its full rebuild night, a poll whose counts were rebuilt more recently than this is left alone
COUNTS_FULL_REBUILD_FRESH = timedelta(hours=12)

# how many polls a counts rebuild chunk considers, of which it rebuilds at most COUNTS_CHUNK_SIZE
COUNTS_SCAN_SIZE = 50

# how many polls a maintenance chunk walks - pruning is the heaviest, it deletes results
COUNTS_CHUNK_SIZE = 5
PRUNE_CHUNK_SIZE = 3
AGE_GENDER_CHUNK_SIZE = 5

# the age and gender backfill walks contacts a batch at a time, checkpointing each batch,
# and does a few of them per chunk so a big org doesn't need a message per thousand contacts
POPULATE_BATCH_SIZE = 1000
POPULATE_BATCHES_PER_CHUNK = 5

# results of polls are dropped once both the poll's date and its creation are older than
# this - a poll's date defaults to its flow's, so a new poll on an old flow still gets the
# full period
RESULTS_RETENTION = timedelta(days=365)

# a flow old enough to retire is retired by the end of its next results sync, so that nothing
# pulled before it is lost - when that was asked for is kept until its counts were rebuilt on
# the flow retired, however long that takes, as the prune deletes its results without
# rebuilding them once it's gone. A flow whose sync keeps failing is retired by the prune
# after a wait
RETIRE_KEY = "poll-retire:org:%d:flow:%s"
RETIRE_FALLBACK_WAIT = timedelta(days=3)

# how many flows a prune run asks to retire, so a backlog of them is spread over nights
# rather than queueing a sync of every one at once
PRUNE_MAX_REQUESTS = 50

# set while a full re-pull of a flow is under way, i.e. its results were deleted and are being
# pulled again, so its counts are left as they were rather than rebuilt from part of them
FULL_REPULL_KEY = "poll-full-repull:org:%d:flow:%s"
FULL_REPULL_KEY_TTL = 60 * 60 * 24 * 3

# an age and gender backfill populates the results, then rebuilds what they feed
STAGE_POPULATE = "populate"
STAGE_REBUILD = "rebuild"

# what a prune did with a poll, kept apart in the job's counters so that a poll failing
# every run is distinguishable from one that was merely busy
PRUNE_REQUESTED = "requested"
PRUNE_DEFERRED = "deferred"
PRUNE_RETIRED = "retired"
PRUNE_CLEARED = "cleared"
PRUNE_SKIPPED_SYNCING = "skipped_syncing"
PRUNE_SKIPPED_RETIRED = "skipped_retired"
PRUNE_SKIPPED_PROTECTED = "skipped_protected"
PRUNE_SKIPPED_PULLING = "skipped_pulling"
PRUNE_SKIPPED_REBUILDING = "skipped_rebuilding"
PRUNE_ERRORED = "errors"


def get_job_poll(org_id, flow_uuid):
    """
    Returns the poll a job syncs for, i.e. the newest active poll still syncing on that
    flow. Results are stored per (org, flow) so polls sharing a flow share one job.
    """
    from ureport.polls.models import Poll

    return (
        Poll.objects.filter(org_id=org_id, flow_uuid=flow_uuid, is_active=True, stopped_syncing=False)
        .exclude(flow_uuid="")
        .order_by("-created_on")
        .first()
    )


def queue_results_sync(org, flow_uuid, reset_cursor=False):
    """
    Ensures the results job for this flow exists and asks for a chunk of it to run.
    """
    return _queue(SyncJob.get_or_create_job(org, RESULTS_JOB_TYPE, flow_uuid), reset_cursor)


def queue_archives_sync(org, flow_uuid, reset_cursor=False):
    """
    Ensures the archives job for this flow exists and asks for a chunk of it to run.
    """
    return _queue(SyncJob.get_or_create_job(org, ARCHIVES_JOB_TYPE, flow_uuid), reset_cursor)


def queue_maintenance(job_type, org=None):
    """
    Ensures the maintenance job of this type exists - one per org, or one install wide for a
    job with no org - and asks for a chunk of it to run.
    """
    job = SyncJob.get_or_create_job(org, job_type)
    enqueue(job)

    return job


def is_flow_syncing(org_id, flow_uuid):
    """
    Whether a sync job is actively working on this flow's results - holding a live lease, or
    between chunks of a run, which release the lease while the next one waits in the queue.
    Callers that destroy a flow's results must not do so mid traversal.
    """
    now = timezone.now()
    jobs = SyncJob.objects.filter(
        org_id=org_id,
        job_type__in=(RESULTS_JOB_TYPE, ARCHIVES_JOB_TYPE),
        scope=flow_uuid,
        status=SyncJob.STATUS_RUNNING,
    )

    return any(in_flight(job, now) for job in jobs)


def _queue(job, reset_cursor=False):
    if reset_cursor:
        job.reset_cursor()

    enqueue(job)
    return job


def _get_backend(poll):
    return poll.org.get_backend(backend_slug=poll.backend.slug)


def _flow_poll_ids(job):
    from ureport.polls.models import Poll

    return list(Poll.objects.filter(org_id=job.org_id, flow_uuid=job.scope).values_list("pk", flat=True))


def _pull_after_delete_requested(job):
    """
    Whether a full re-pull was asked for on any of the polls sharing this flow. The flag is
    set per poll, so a refresh triggered from a duplicate poll of the flow counts too.
    """
    from ureport.polls.models import Poll

    for poll_id in _flow_poll_ids(job):
        if cache.get(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (job.org_id, poll_id), None) is not None:
            return True

    return False


def _delete_flow_results(job, poll):
    """
    Drops every result synced for the flow and the re-pull flags of all its polls -
    delete_poll_results only clears the flag of the poll it is called on, and the flags
    never expire.
    """
    from ureport.polls.models import Poll

    # the counts stay as they were until the archives have been walked again too, and a
    # retirement asked for before is moot - the flow is pulled again in full either way
    cache.set(FULL_REPULL_KEY % (job.org_id, job.scope), True, FULL_REPULL_KEY_TTL)
    cache.delete(RETIRE_KEY % (job.org_id, job.scope))

    # marked after the delete too, as a rebuild that started during it counted some of the deleted results
    Poll.mark_results_changed(job.org_id, job.scope)
    poll.delete_poll_results()
    Poll.mark_results_changed(job.org_id, job.scope)

    for poll_id in _flow_poll_ids(job):
        cache.delete(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (job.org_id, poll_id))


def _queue_archives_rewalk(poll):
    """
    Queues the archives job to walk the flow's archives from the start again. Returns
    whether the cursor reset landed: a job under a live lease keeps its cursor, and a
    completed cursor resumes below its last position, so a refused reset has to be retried
    or the archived half of a full re-pull is silently skipped.
    """
    job = SyncJob.get_or_create_job(poll.org, ARCHIVES_JOB_TYPE, poll.flow_uuid)

    reset = job.reset_cursor()
    if reset:
        enqueue(job)
    else:
        # the chunk holding the lease carries its own walk on, so it needs no message
        logger.warning("Archives job #%d is still running, deferring its cursor reset" % job.id)

    return reset


def _set_reset_pending(progress, pending):
    progress = dict(progress)
    if pending:
        progress[ARCHIVES_RESET_PENDING] = 1
    else:
        progress.pop(ARCHIVES_RESET_PENDING, None)

    return progress


def _changed_results(job):
    return _has_changes(job.progress or {})


def _has_changes(counts):
    return any(counts.get(key, 0) for key in RESULT_CHANGE_KEYS)


def _full_repull_pending(org_id, flow_uuid):
    return bool(cache.get(FULL_REPULL_KEY % (org_id, flow_uuid)))


def _end_full_repull(org_id, flow_uuid):
    """
    Ends a full re-pull of the flow if both of its halves are done, returning whether it did:
    its results sync has completed the run that pulled them again, and its archives have been
    walked from the start since. Called by the end of either sync, as whichever ends last
    ends the re-pull - a results run waiting for its archives reset to land is still running,
    so an archives walk ending before that doesn't, nor one ending while the results are
    still being pulled.
    """
    if not _full_repull_pending(org_id, flow_uuid):
        return False

    jobs = {
        j.job_type: j
        for j in SyncJob.objects.filter(
            org_id=org_id, job_type__in=(RESULTS_JOB_TYPE, ARCHIVES_JOB_TYPE), scope=flow_uuid
        )
    }
    results = jobs.get(RESULTS_JOB_TYPE)
    if not results or results.status != SyncJob.STATUS_COMPLETE or not _archives_walked(jobs.get(ARCHIVES_JOB_TYPE)):
        return False

    cache.delete(FULL_REPULL_KEY % (org_id, flow_uuid))
    return True


def _finalize_results(job):
    """
    Completes a results run: a flow waiting to be retired is retired now that everything up
    to this moment has been pulled, otherwise counts are rebuilt from everything the run
    changed, or everything a full re-pull it ends did, and the polls on the flow are marked
    synced. The position is mirrored to the cache key the unchunked task resumes from
    either way.
    """
    from ureport.polls.models import Poll

    after = (job.cursor or {}).get("after")
    if after:
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (job.org_id, job.scope), after, None)

    repulled = _end_full_repull(job.org_id, job.scope)

    poll = get_job_poll(job.org_id, job.scope)
    if not poll:
        return

    if cache.get(RETIRE_KEY % (job.org_id, job.scope)) and _retire_flow(job.org, job.scope, job) == PRUNE_RETIRED:
        return

    # during a full re-pull the counts wait for both of its halves to be done
    if (repulled or _changed_results(job)) and not _full_repull_pending(job.org_id, job.scope):
        # rebuilding refreshes the question caches of every poll on the flow itself
        poll.rebuild_poll_results_counts()

    Poll.objects.filter(org_id=job.org_id, flow_uuid=job.scope, has_synced=False).update(has_synced=True)


def _finalize_archives(job):
    """
    Completes an archives run: counts are rebuilt from everything the run changed, or
    everything a full re-pull it ends did. A flow waiting to be retired is retired by the end
    of its next results sync, once its archives have been walked.
    """
    from ureport.polls.models import Poll

    repulled = _end_full_repull(job.org_id, job.scope)

    poll = get_job_poll(job.org_id, job.scope)
    if not poll:
        return

    if (repulled or _changed_results(job)) and not _full_repull_pending(job.org_id, job.scope):
        poll.rebuild_poll_results_counts()

    Poll.objects.filter(org_id=job.org_id, flow_uuid=job.scope, has_synced=False).update(has_synced=True)


@chunked_task(
    RESULTS_JOB_TYPE,
    queue=SYNC_QUEUE,
    lease_seconds=RESULTS_LEASE_SECONDS,
    finalize=_finalize_results,
    name="polls.sync_poll_results",
)
def sync_poll_results(job):
    from ureport.polls.models import Poll
    from ureport.utils import json_date_to_datetime

    poll = get_job_poll(job.org_id, job.scope)
    if not poll:
        return True

    cursor = dict(job.cursor or {})
    progress = dict(job.progress or {})
    first_chunk = not progress
    reset_pending = bool(progress.get(ARCHIVES_RESET_PENDING))

    if _pull_after_delete_requested(job):
        # the restart has to be durable before anything is deleted: deleting consumes the
        # flag and the legacy position key, so a crash in between would leave the old
        # cursor resuming an incremental pull over results that are gone. Crashing after
        # this checkpoint instead just deletes and re-pulls again, which is harmless.
        job.checkpoint(cursor={})
        cursor = {}

        _delete_flow_results(job, poll)

        # everything synced so far is discarded, so the archives have to be walked again too
        reset_pending = not _queue_archives_rewalk(poll)
        job.checkpoint(progress=_set_reset_pending(job.progress, reset_pending))
    else:
        if reset_pending:
            reset_pending = not _queue_archives_rewalk(poll)

        if not cursor:
            # resume where the unchunked task left off rather than re-pulling everything
            last_pull = cache.get(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (poll.org_id, poll.flow_uuid), None)
            if last_pull:
                cursor = {"after": last_pull}

        if first_chunk and not poll.has_synced:
            # runs older than the API's retention are only in the archives, which the
            # first sync of a flow has to walk separately
            flow_date_json = poll.get_flow_date()
            has_archives_results = flow_date_json is None or (
                json_date_to_datetime(flow_date_json) + timedelta(days=90) < timezone.now()
            )
            if has_archives_results:
                queue_archives_sync(poll.org, poll.flow_uuid)

    result = _get_backend(poll).pull_results_chunk(poll, cursor)
    if _has_changes(result.counts):
        Poll.mark_results_changed(job.org_id, job.scope)

    progress = _set_reset_pending(job.add_progress(chunks=1, **result.counts), reset_pending)
    job.checkpoint(cursor=result.cursor, progress=progress)

    if result.done:
        # the next run starts on fresh progress, so a run ending with the reset still pending
        # would drop it, and the archived results deleted with the rest would never be pulled again
        return ARCHIVES_RESET_BACKOFF if reset_pending else True

    if progress.get("chunks", 0) % REBUILD_COUNTS_EVERY == 0 and not _full_repull_pending(job.org_id, job.scope):
        poll.rebuild_poll_results_counts()

        # a rebuild of a big flow can outlast the lease, so renew before the next chunk -
        # if it's gone this raises and the chunk is dropped rather than writing on
        job.checkpoint()

    return RATE_LIMITED_BACKOFF if result.rate_limited else False


@chunked_task(
    ARCHIVES_JOB_TYPE,
    queue=SYNC_QUEUE,
    lease_seconds=ARCHIVES_LEASE_SECONDS,
    finalize=_finalize_archives,
    name="polls.sync_poll_archives",
)
def sync_poll_archives(job):
    from ureport.polls.models import Poll

    poll = get_job_poll(job.org_id, job.scope)
    if not poll:
        return True

    result = _get_backend(poll).pull_results_from_archives_chunk(poll, dict(job.cursor or {}))
    if _has_changes(result.counts):
        Poll.mark_results_changed(job.org_id, job.scope)

    job.checkpoint(cursor=result.cursor, progress=job.add_progress(chunks=1, **result.counts))

    if result.done:
        return True

    return RATE_LIMITED_BACKOFF if result.rate_limited else False


@app.task(name="polls.sync_polls_dispatch")
def sync_polls_dispatch(org_id=None):
    """
    Nudges the poll results jobs that are due, at the cadence each poll's visibility
    warrants. Jobs that are already running are left to their own continuations.
    """
    orgs = Org.objects.filter(is_active=True)
    if org_id:
        orgs = orgs.filter(id=org_id)

    for org in orgs:
        try:
            dispatch_org_polls(org)
        except Exception:
            logger.error("Error dispatching poll syncs for org #%d" % org.pk, exc_info=True)


def dispatch_org_polls(org):
    from ureport.polls.models import Poll

    handled = set()

    unsynced = (
        Poll.objects.filter(org=org, is_active=True, has_synced=False, stopped_syncing=False)
        .exclude(flow_uuid="")
        .values_list("flow_uuid", flat=True)
    )
    dispatch_flows(org, unsynced, handled=handled)

    main_poll = Poll.get_main_poll(org)
    if main_poll:
        dispatch_flows(org, [main_poll.flow_uuid], interval=MAIN_POLL_INTERVAL, handled=handled)

    recent_polls = Poll.get_recent_polls(org).values_list("flow_uuid", flat=True)
    dispatch_flows(org, recent_polls, interval=RECENT_POLLS_INTERVAL, handled=handled)

    other_polls = Poll.get_other_polls(org).exclude(created_on__gt=timezone.now() - OTHER_POLLS_NEW_WINDOW)
    dispatch_flows(org, other_polls.values_list("flow_uuid", flat=True), interval=OTHER_POLLS_INTERVAL, handled=handled)

    dispatch_archives(org)


def dispatch_archives(org):
    """
    Nudges unfinished archive traversals. They are queued once by the results sync, so
    without this an interrupted or failed one would never be retried - while the polls on
    the flow already tell the public site their results are complete. Returns the flows
    actually queued.
    """
    now = timezone.now()
    queued = []

    jobs = SyncJob.objects.filter(org=org, job_type=ARCHIVES_JOB_TYPE).exclude(status=SyncJob.STATUS_COMPLETE)
    for job in jobs:
        if is_due(job, now, backoff=FAILURE_BACKOFF):
            enqueue(job)
            queued.append(job.scope)

    return queued


def dispatch_flows(org, flow_uuids, interval=None, handled=None):
    """
    Queues a chunk of the results job of every given flow that is due at the given cadence,
    an interval of None meaning due whatever its last run. Flows already in the handled set
    are skipped, so a flow covered by a tighter cadence isn't queued again by a looser one.
    Returns the flows actually queued.
    """
    now = timezone.now()
    handled = handled if handled is not None else set()
    queued = []

    for flow_uuid in flow_uuids:
        if not flow_uuid or flow_uuid in handled:
            continue

        handled.add(flow_uuid)

        job = SyncJob.get_or_create_job(org, RESULTS_JOB_TYPE, flow_uuid)
        if is_due(job, now, interval=interval, backoff=FAILURE_BACKOFF):
            _queue(job)
            queued.append(flow_uuid)

    return queued


# ------------------------------------------------------------------------------
# Maintenance jobs: the periodic passes over polls that keep counts fresh, retire
# polls too old to keep results for, and backfill segments onto existing results.
# Each walks in pk (or contact id) order so a killed worker resumes where it
# stopped. The counts rebuild and the prune are nudged by beat; the age and gender
# backfill is only ever triggered by hand, as it was before, so re-triggering it is
# also how a run stranded by a dead worker is picked back up - safe at any time,
# since a job resumes from its cursor rather than starting the walk over.
# ------------------------------------------------------------------------------


@chunked_task(
    COUNTS_JOB_TYPE, queue=SLOW_QUEUE, lease_seconds=MAINTENANCE_LEASE_SECONDS, name="polls.rebuild_poll_counts"
)
def rebuild_poll_counts(job):
    """
    Rebuilds the results counts of a bounded number of polls per chunk, across every org -
    this is one install wide job, which is what replaces the multi day lock the unchunked
    task held for the whole pass. Each run walks the syncing polls whose counts are due a
    rebuild once, in pk order, and the next run starts over from the first of them.
    """
    from ureport.polls.models import Poll

    if job.new_run:
        # a run has to cover every due poll, so the position the last one left behind is dropped
        # - durably, or a chunk that failed before its first checkpoint would leave the retry
        # resuming below a completed run's position and walking nothing
        job.checkpoint(cursor={})

    after_pk = (job.cursor or {}).get("after_pk") or 0

    # a poll that stopped syncing has no results left to count and its caches were rebuilt
    # when it stopped, so this pass has nothing to keep fresh for it. The tradeoff is that
    # retired polls lose the daily cache refresh they used to get: their cached results
    # never expire and are recalculated on read, but a cache flush leaves them uncached
    # until something asks for them
    polls = list(
        Poll.objects.filter(is_active=True, stopped_syncing=False, pk__gt=after_pk).order_by("pk")[:COUNTS_SCAN_SIZE]
    )
    if not polls:
        return True

    rebuilt = skipped = 0

    for poll in polls:
        # checked as each poll comes up rather than for the chunk up front, as rebuilding a
        # poll rebuilds every poll of its flow and a sync may rebuild one meanwhile
        if not _counts_rebuild_due(poll, job.started_on):
            skipped += 1
            continue

        poll.rebuild_poll_results_counts()
        rebuilt += 1

        # checkpointed per poll rather than per chunk: rebuilding a big flow can take
        # minutes, and a chunk that ran out of lease must not write on
        job.checkpoint(cursor={"after_pk": poll.pk}, progress=_add_nonzero_progress(job, rebuilt=1, skipped=skipped))
        skipped = 0

        if rebuilt >= COUNTS_CHUNK_SIZE:
            return False

    job.checkpoint(cursor={"after_pk": polls[-1].pk}, progress=_add_nonzero_progress(job, skipped=skipped))
    return False


def _add_nonzero_progress(job, **counts):
    return job.add_progress(**{key: value for key, value in counts.items() if value})


def _counts_rebuild_due(poll, run_on):
    """
    Whether the counts rebuild run started at run_on has to rebuild the poll's counts: ones
    never rebuilt, ones whose results changed after their last rebuild started, and ones on
    their full rebuild night that weren't rebuilt recently. A flow being pulled again in
    full isn't, as the end of the re-pull rebuilds it once it has all of its results again.
    """
    if _full_repull_pending(poll.org_id, poll.flow_uuid):
        return False

    changed_on, rebuilt_on = poll.get_counts_stamps()

    if rebuilt_on is None or (changed_on is not None and changed_on > rebuilt_on):
        return True

    night = run_on.date().toordinal() % COUNTS_FULL_REBUILD_DAYS
    return poll.pk % COUNTS_FULL_REBUILD_DAYS == night and rebuilt_on < run_on - COUNTS_FULL_REBUILD_FRESH


@chunked_task(
    PRUNE_JOB_TYPE, queue=SLOW_QUEUE, lease_seconds=MAINTENANCE_LEASE_SECONDS, name="polls.prune_poll_results"
)
def prune_poll_results(job):
    """
    Retires the flows of an org's polls that are too old to keep syncing, then deletes their
    results, a bounded number of polls per chunk. A flow is retired by the end of the sync
    the prune asks for, so that its counts are rebuilt one last time on everything pulled
    up to then and nothing can be pulled in after - see _retire_flow - and its results are
    deleted by a later run. As retiring a flow retires every poll on it, a flow is only
    retired once none of the polls syncing it is within the retention period, nor the main
    poll. Polls whose flow is still being synced are stepped over rather than waited for,
    and reconsidered by a later run.
    """
    from ureport.polls.models import Poll, PollResult

    org = job.org
    now = timezone.now()

    if job.new_run:
        # a run reconsiders every old poll, so it starts from the first of them - see
        # rebuild_poll_counts for why that reset is checkpointed before any work
        job.checkpoint(cursor={})

    after_pk = (job.cursor or {}).get("after_pk") or 0

    has_results = Exists(PollResult.objects.filter(org_id=org.pk, flow=OuterRef("flow_uuid")))
    flow_syncing = Exists(_syncing_flow_polls(org).filter(flow_uuid=OuterRef("flow_uuid")))
    flow_protected = Exists(_protected_flow_polls(org, now).filter(flow_uuid=OuterRef("flow_uuid")))

    polls = (
        Poll.objects.filter(org=org, pk__gt=after_pk)
        .filter(Q(stopped_syncing=False) | (has_results & ~flow_syncing))
        .exclude(poll_date__gte=now - RESULTS_RETENTION)
        .exclude(created_on__gte=now - RESULTS_RETENTION)
        .exclude(flow_protected)
    )
    main_poll = Poll.get_main_poll(org)
    if main_poll:
        polls = polls.exclude(flow_uuid=main_poll.flow_uuid)

    polls = list(polls.order_by("pk")[:PRUNE_CHUNK_SIZE])
    if not polls:
        return True

    for poll in polls:
        can_request = (job.progress or {}).get(PRUNE_REQUESTED, 0) < PRUNE_MAX_REQUESTS
        outcome = _prune_poll(org, poll, can_request)

        # the position advances past a poll that was skipped or errored too, so that one
        # unhappy poll can't stall everything behind it - the next run reconsiders it
        job.checkpoint(cursor={"after_pk": poll.pk}, progress=job.add_progress(**{outcome: 1}))

    return False


def _syncing_flow_polls(org):
    """
    The polls of an org that keep their flow syncing - see get_job_poll
    """
    from ureport.polls.models import Poll

    return Poll.objects.filter(org=org, is_active=True, stopped_syncing=False)


def _protected_flow_polls(org, now):
    """
    The polls of an org syncing a flow that is too recent to retire
    """
    cutoff = now - RESULTS_RETENTION

    return _syncing_flow_polls(org).filter(Q(poll_date__gte=cutoff) | Q(created_on__gte=cutoff))


def _archives_walked(archives_job):
    """
    Whether the flow's archives have been walked to the end since its results were last
    pulled again in full: a job that has never been created isn't needed, one that hasn't
    finished a walk - or was sent back to the start, which leaves its cursor empty - is. A
    reset its results sync is still waiting to apply keeps that sync's run going, so it is
    never pending by the end of one.
    """
    if archives_job is None:
        return True

    return archives_job.status == SyncJob.STATUS_COMPLETE and bool(archives_job.cursor)


def _retire_flow(org, flow_uuid, holder=None, fallback=False):
    """
    Retires every poll on a flow and rebuilds its counts one last time, returning what
    became of it. Called by the end of a results sync of the flow, whose job holder is, or
    by the prune for a flow whose sync kept failing, which retires it on what it has rather
    than waiting for its archives.

    The polls are retired before the counts are rebuilt, under a lock on the flow's sync
    jobs that a chunk has to wait on to claim them, and only while no chunk but the
    caller's is under way: a chunk that claims one after that sees no poll to sync for, so
    nothing is written that the rebuild doesn't count.
    """
    from ureport.polls.models import Poll

    now = timezone.now()
    key = RETIRE_KEY % (org.pk, flow_uuid)
    main_poll = Poll.get_main_poll(org)

    with transaction.atomic():
        jobs = {
            j.job_type: j
            for j in SyncJob.objects.select_for_update().filter(
                org=org, job_type__in=(RESULTS_JOB_TYPE, ARCHIVES_JOB_TYPE), scope=flow_uuid
            )
        }
        if any((holder is None or j.id != holder.id) and in_flight(j, now) for j in jobs.values()):
            return PRUNE_SKIPPED_SYNCING

        if not fallback and not _archives_walked(jobs.get(ARCHIVES_JOB_TYPE)):
            return PRUNE_SKIPPED_PULLING

        # locked, so a poll set up on the flow meanwhile is either seen here or set up after
        # it is retired - in which case it pulls all of the flow's results again
        polls = list(Poll.objects.select_for_update().filter(org=org, flow_uuid=flow_uuid))
        if all(p.stopped_syncing for p in polls):
            return PRUNE_SKIPPED_RETIRED

        is_main = main_poll is not None and main_poll.flow_uuid == flow_uuid
        if is_main or _protected_flow_polls(org, now).filter(flow_uuid=flow_uuid).exists():
            cache.delete(key)
            return PRUNE_SKIPPED_PROTECTED

        # until the rebuild below replaced all of the counts, the prune has to rebuild them
        # before deleting the results, so the request is kept for good from here - set before
        # the polls are, so that a crash in between can't leave a flow retired without it
        cache.set(key, now, None)

        Poll.objects.filter(pk__in=[p.pk for p in polls]).update(stopped_syncing=True)

    if _full_repull_pending(org.pk, flow_uuid):
        # only the fallback retires a flow whose full re-pull isn't done, and its counts were
        # left as they were before its results were deleted - more of them than it has now
        cache.delete(key)
        cache.delete(FULL_REPULL_KEY % (org.pk, flow_uuid))
        logger.info("Retired flow %s on org #%d on the counts it had before it was pulled again" % (flow_uuid, org.pk))
        return PRUNE_RETIRED

    poll = Poll.objects.get(pk=polls[0].pk)
    if poll.rebuild_poll_results_counts(retiring=True):
        cache.delete(key)

    logger.info("Retired flow %s on org #%d" % (flow_uuid, org.pk))
    return PRUNE_RETIRED


def _prune_poll(org, poll, can_request):
    """
    Does the next step of retiring one poll's flow, returning what that was. A flow still
    being synced is left alone - its results must not be deleted mid traversal. A retired
    flow has its results deleted, unless a newer poll on the flow is syncing it again and
    the results are that poll's, or none are left, which is how the duplicated polls of a
    flow are recognised. A flow still syncing is asked to retire by the end of its next
    sync, or retired here if that sync hasn't happened in RETIRE_FALLBACK_WAIT.
    """
    from ureport.polls.models import Poll

    if is_flow_syncing(org.pk, poll.flow_uuid):
        logger.info("Skipping clearing old results for poll #%d on org #%d as it is still syncing" % (poll.pk, org.pk))
        return PRUNE_SKIPPED_SYNCING

    # the valkey lock is only taken by the unchunked pulls, kept here for the release they
    # still exist in - a chunked sync announces itself with its job lease instead
    key = Poll.POLL_PULL_RESULTS_TASK_LOCK % (org.pk, poll.flow_uuid)

    with chunk_lock(key, Poll.POLL_SYNC_LOCK_TIMEOUT) as acquired:
        if not acquired:
            logger.info(
                "Skipping clearing old results for poll #%d on org #%d as it is still syncing" % (poll.pk, org.pk)
            )
            return PRUNE_SKIPPED_SYNCING

        # refresh the object from the DB
        poll.refresh_from_db()

        try:
            if poll.stopped_syncing:
                return _delete_retired_results(org, poll)

            return _request_retirement(org, poll, can_request)
        except Exception:
            # one poll that fails every time would otherwise stall every poll after it, as
            # the traversal can only move past polls it has finished with
            logger.error(
                "Error clearing old poll results for poll #%s on org #%s" % (poll.id, poll.org_id),
                exc_info=True,
                extra={"stack": True},
            )
            return PRUNE_ERRORED


def _request_retirement(org, poll, can_request):
    # a flow whose polls are all inactive has no sync to wait for, as none is run for them
    if not _syncing_flow_polls(org).filter(flow_uuid=poll.flow_uuid).exists():
        return _retire_flow(org, poll.flow_uuid, fallback=True)

    key = RETIRE_KEY % (org.pk, poll.flow_uuid)
    requested_on = cache.get(key)

    if not requested_on:
        if not can_request:
            return PRUNE_DEFERRED

        cache.set(key, timezone.now(), None)
        queue_results_sync(org, poll.flow_uuid)
        return PRUNE_REQUESTED

    # a sync paused by hand is waited for however long, as there is no telling what it missed
    paused = SyncJob.objects.filter(
        org=org, job_type__in=(RESULTS_JOB_TYPE, ARCHIVES_JOB_TYPE), scope=poll.flow_uuid, status=SyncJob.STATUS_PAUSED
    ).exists()

    if requested_on > timezone.now() - RETIRE_FALLBACK_WAIT or paused:
        queue_results_sync(org, poll.flow_uuid)
        return PRUNE_SKIPPED_PULLING

    return _retire_flow(org, poll.flow_uuid, fallback=True)


def _delete_retired_results(org, poll):
    from ureport.polls.models import PollResult

    if (
        not PollResult.objects.filter(org_id=org.pk, flow=poll.flow_uuid).exists()
        or _syncing_flow_polls(org).filter(flow_uuid=poll.flow_uuid).exists()
    ):
        logger.info(
            "Skipping clearing old results for poll #%d on org #%d as it appear to be duplicated" % (poll.pk, org.pk)
        )
        return PRUNE_SKIPPED_RETIRED

    # a retirement still asked for is one whose rebuild didn't replace all of the counts, and
    # the counts left now are the flow's for good. Otherwise the counts were rebuilt when the
    # flow was retired, and rebuilding them from what is left of its results would only
    # undercount them
    key = RETIRE_KEY % (org.pk, poll.flow_uuid)
    if cache.get(key):
        if not poll.rebuild_poll_results_counts(retiring=True):
            logger.info(
                "Skipping clearing old results for poll #%d on org #%d as its counts weren't all rebuilt"
                % (poll.pk, org.pk)
            )
            return PRUNE_SKIPPED_REBUILDING

        cache.delete(key)

    poll.delete_poll_results()

    logger.info("Cleared poll results for poll #%s on org #%s" % (poll.id, poll.org_id))
    return PRUNE_CLEARED


@chunked_task(
    AGE_GENDER_JOB_TYPE, queue=SLOW_QUEUE, lease_seconds=MAINTENANCE_LEASE_SECONDS, name="polls.backfill_age_gender"
)
def backfill_age_gender(job):
    """
    Backfills the age and gender of an org's poll results, then rebuilds the counts those
    segments feed. Contacts are walked in id order a batch at a time, then the org's polls
    in pk order. Contact ids are global and only ever grow, so the position the populate
    pass reached is kept between runs and the next one carries on from it rather than
    rewalking every contact the org has ever had.
    """
    from ureport.polls.models import Poll
    from ureport.utils import LAST_POPULATED_CONTACT_KEY

    org = job.org

    if job.new_run:
        # where a new run's populate pass starts: the position this job's last run reached,
        # or for a job that has never run, the position the unchunked task left in its cache
        # key. That key is only ever read - the walk it belongs to is retired
        watermark = (job.cursor or {}).get("populate_watermark") or cache.get(LAST_POPULATED_CONTACT_KEY, 0) or 0

        # checkpointed before any work for the same reason as rebuild_poll_counts: a chunk
        # that failed before its first checkpoint must not leave the retry resuming from
        # where the last run ended
        cursor = {"stage": STAGE_POPULATE, "after_contact_id": watermark}
        job.checkpoint(cursor=cursor)
    else:
        cursor = dict(job.cursor or {})

    if cursor.get("stage") == STAGE_POPULATE:
        return _populate_chunk(job, org, cursor)

    after_pk = cursor.get("after_pk") or 0

    polls = list(Poll.objects.filter(org=org, pk__gt=after_pk).order_by("pk")[:AGE_GENDER_CHUNK_SIZE])
    if not polls:
        return True

    for poll in polls:
        poll.rebuild_poll_results_counts()

        job.checkpoint(
            cursor={**cursor, "stage": STAGE_REBUILD, "after_pk": poll.pk}, progress=job.add_progress(rebuilt=1)
        )

    return False


def _populate_chunk(job, org, cursor):
    """
    Copies age and gender onto the results of a few batches of the org's contacts, each
    batch checkpointed and renewing the lease, so an interrupted pass resumes at the batch
    it stopped on instead of starting the org's contacts over.
    """
    from ureport.contacts.models import Contact
    from ureport.utils import populate_age_and_gender_for_contacts

    after_contact_id = cursor.get("after_contact_id") or 0

    for _ in range(POPULATE_BATCHES_PER_CHUNK):
        contact_ids = list(
            Contact.objects.filter(org=org, id__gt=after_contact_id)
            .order_by("id")
            .values_list("id", flat=True)[:POPULATE_BATCH_SIZE]
        )

        if not contact_ids:
            # the contacts are exhausted, so how far this pass got becomes where the next
            # run starts, and the counts these segments feed are rebuilt next
            job.checkpoint(cursor={"stage": STAGE_REBUILD, "populate_watermark": after_contact_id})
            return False

        populate_age_and_gender_for_contacts(contact_ids)
        after_contact_id = contact_ids[-1]

        job.checkpoint(
            cursor={"stage": STAGE_POPULATE, "after_contact_id": after_contact_id},
            progress=job.add_progress(populated=len(contact_ids)),
        )

    return False


@app.task(name="polls.rebuild_counts_dispatch")
def rebuild_counts_dispatch():
    """
    Nudges the install wide counts rebuild job. A pass still working through its polls when
    the next one comes round is left to its own continuations rather than started again,
    and a failing one backs off. Returns the job id if it was queued.
    """
    job = SyncJob.get_or_create_job(None, COUNTS_JOB_TYPE)

    if not is_due(job, timezone.now(), interval=MAINTENANCE_INTERVAL, backoff=FAILURE_BACKOFF):
        logger.info("Job #%d (%s) not queued, %s" % (job.id, COUNTS_JOB_TYPE, job.get_status_display()))
        return None

    enqueue(job)
    return job.id


@app.task(name="polls.prune_results_dispatch")
def prune_results_dispatch(org_id=None):
    """
    Nudges the old results prune job of every active org that is due for one. Returns the
    orgs actually queued.
    """
    orgs = Org.objects.filter(is_active=True)
    if org_id:
        orgs = orgs.filter(id=org_id)

    now = timezone.now()
    queued = []

    for org in orgs:
        job = SyncJob.get_or_create_job(org, PRUNE_JOB_TYPE)
        if is_due(job, now, interval=MAINTENANCE_INTERVAL, backoff=FAILURE_BACKOFF):
            enqueue(job)
            queued.append(org.pk)

    return queued
