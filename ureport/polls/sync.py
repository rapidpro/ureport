# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from dash.orgs.models import Org
from ureport.celery import app
from ureport.syncjobs.models import SyncJob
from ureport.syncjobs.tasks import chunked_task

logger = logging.getLogger(__name__)

RESULTS_JOB_TYPE = "poll-results"
ARCHIVES_JOB_TYPE = "poll-archives"

SYNC_QUEUE = "sync"

# a results chunk is a bounded number of API pages, an archives chunk a single archive file
RESULTS_LEASE_SECONDS = 60 * 30
ARCHIVES_LEASE_SECONDS = 60 * 60 * 2

# how long to wait before the next chunk when the backend exhausted its rate limit
RATE_LIMITED_BACKOFF = 300

# counts are rebuilt this often mid-run so a long first sync still reaches the public site
REBUILD_COUNTS_EVERY = 5

# progress marker for an archives cursor reset that couldn't be applied yet
ARCHIVES_RESET_PENDING = "archives_reset_pending"

# counters that mean a run actually changed results, i.e. counts are worth rebuilding
RESULT_CHANGE_KEYS = ("num_val_created", "num_val_updated", "num_path_created", "num_path_updated")

# how stale a job's last run may be before the dispatcher runs it again
MAIN_POLL_INTERVAL = timedelta(minutes=20)
RECENT_POLLS_INTERVAL = timedelta(hours=1)
OTHER_POLLS_INTERVAL = timedelta(hours=24)

# a failing job backs off exponentially from this, so a deterministically broken sync isn't
# retried at the dispatcher's full rate
FAILURE_BACKOFF = timedelta(minutes=20)
MAX_FAILURE_BACKOFF = timedelta(hours=24)
MAX_BACKOFF_DOUBLINGS = 10

# other polls created this recently are covered by the recent polls cadence
OTHER_POLLS_NEW_WINDOW = timedelta(days=7)


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
    return _queue(sync_poll_results, SyncJob.get_or_create_job(org, RESULTS_JOB_TYPE, flow_uuid), reset_cursor)


def queue_archives_sync(org, flow_uuid, reset_cursor=False):
    """
    Ensures the archives job for this flow exists and asks for a chunk of it to run.
    """
    return _queue(sync_poll_archives, SyncJob.get_or_create_job(org, ARCHIVES_JOB_TYPE, flow_uuid), reset_cursor)


def is_flow_syncing(org_id, flow_uuid):
    """
    Whether a sync job is actively working on this flow's results, i.e. holds a live lease.
    Callers that destroy a flow's results must not do so mid traversal.
    """
    return SyncJob.objects.filter(
        org_id=org_id,
        job_type__in=(RESULTS_JOB_TYPE, ARCHIVES_JOB_TYPE),
        scope=flow_uuid,
        status=SyncJob.STATUS_RUNNING,
        lease_expires_on__gt=timezone.now(),
    ).exists()


def _queue(task, job, reset_cursor=False):
    if reset_cursor:
        _reset_cursor(job)

    _enqueue(task, job)
    return job


def _enqueue(task, job):
    task.apply_async((job.id,), queue=SYNC_QUEUE)


def _reset_cursor(job):
    """
    Sends a job back to the start of its traversal, e.g. when the results it synced have
    been deleted. A job under a live lease is left alone - its worker owns the cursor -
    so callers must retry a refused reset rather than assume it landed.
    """
    now = timezone.now()
    updated = (
        SyncJob.objects.filter(id=job.id)
        .filter(Q(lease_expires_on__isnull=True) | Q(lease_expires_on__lt=now))
        .update(cursor={}, modified_on=now)
    )
    if updated:
        job.refresh_from_db()

    return bool(updated)


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

    poll.delete_poll_results()

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

    reset = _reset_cursor(job)
    if not reset:
        logger.warning("Archives job #%d is still running, deferring its cursor reset" % job.id)

    _enqueue(sync_poll_archives, job)
    return reset


def _set_reset_pending(progress, pending):
    progress = dict(progress)
    if pending:
        progress[ARCHIVES_RESET_PENDING] = 1
    else:
        progress.pop(ARCHIVES_RESET_PENDING, None)

    return progress


def _changed_results(job):
    progress = job.progress or {}
    return any(progress.get(key, 0) for key in RESULT_CHANGE_KEYS)


def _finalize_results(job):
    """
    Completes a results run: counts are rebuilt from everything the run changed, the polls
    on the flow are marked synced, and the position is mirrored to the cache key the
    unchunked task resumes from.
    """
    from ureport.polls.models import Poll

    poll = get_job_poll(job.org_id, job.scope)
    if not poll:
        return

    if _changed_results(job):
        # rebuilding refreshes the question caches of every poll on the flow itself
        poll.rebuild_poll_results_counts()

    Poll.objects.filter(org_id=job.org_id, flow_uuid=job.scope).update(has_synced=True)

    after = (job.cursor or {}).get("after")
    if after:
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (job.org_id, job.scope), after, None)


def _finalize_archives(job):
    from ureport.polls.models import Poll

    poll = get_job_poll(job.org_id, job.scope)
    if not poll:
        return

    if _changed_results(job):
        poll.rebuild_poll_results_counts()

    Poll.objects.filter(org_id=job.org_id, flow_uuid=job.scope).update(has_synced=True)


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
        job.checkpoint(cursor={}, lease_seconds=RESULTS_LEASE_SECONDS)
        cursor = {}

        _delete_flow_results(job, poll)

        # everything synced so far is discarded, so the archives have to be walked again too
        reset_pending = not _queue_archives_rewalk(poll)
        job.checkpoint(progress=_set_reset_pending(job.progress, reset_pending), lease_seconds=RESULTS_LEASE_SECONDS)
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

    progress = _set_reset_pending(job.add_progress(chunks=1, **result.counts), reset_pending)
    job.checkpoint(cursor=result.cursor, progress=progress, lease_seconds=RESULTS_LEASE_SECONDS)

    if result.done:
        return True

    if progress.get("chunks", 0) % REBUILD_COUNTS_EVERY == 0:
        poll.rebuild_poll_results_counts()

        # a rebuild of a big flow can outlast the lease, so renew before the next chunk -
        # if it's gone this raises and the chunk is dropped rather than writing on
        job.checkpoint(lease_seconds=RESULTS_LEASE_SECONDS)

    return RATE_LIMITED_BACKOFF if result.rate_limited else False


@chunked_task(
    ARCHIVES_JOB_TYPE,
    queue=SYNC_QUEUE,
    lease_seconds=ARCHIVES_LEASE_SECONDS,
    finalize=_finalize_archives,
    name="polls.sync_poll_archives",
)
def sync_poll_archives(job):
    poll = get_job_poll(job.org_id, job.scope)
    if not poll:
        return True

    result = _get_backend(poll).pull_results_from_archives_chunk(poll, dict(job.cursor or {}))

    job.checkpoint(
        cursor=result.cursor,
        progress=job.add_progress(chunks=1, **result.counts),
        lease_seconds=ARCHIVES_LEASE_SECONDS,
    )

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
        if _is_due(job, None, now):
            _enqueue(sync_poll_archives, job)
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
        if _is_due(job, interval, now):
            _queue(sync_poll_results, job)
            queued.append(flow_uuid)

    return queued


def _is_due(job, interval, now):
    """
    A job is due unless it is paused, a run is still moving, or its last run ended recently
    enough - for the cadence asked for, an interval of None meaning any finished run is
    stale, or for the backoff its failure streak has earned. The failure backoff matters
    because a job that fails deterministically would otherwise be retried on every pass.
    """
    if job.status == SyncJob.STATUS_PAUSED or _in_flight(job, now):
        return False

    wait = interval
    if job.consecutive_failures:
        doublings = min(job.consecutive_failures - 1, MAX_BACKOFF_DOUBLINGS)
        backoff = min(FAILURE_BACKOFF * 2**doublings, MAX_FAILURE_BACKOFF)
        wait = max(wait, backoff) if wait else backoff

    if not wait:
        return True

    return not (job.ended_on and job.ended_on > now - wait)


def _in_flight(job, now):
    """
    Whether a run is still moving: a live lease, or a running job that checkpointed
    recently - chunks release the lease between continuations, so a healthy run looks idle
    from here while its next message waits in the queue. A running job that stopped
    checkpointing is deliberately not in flight: nudging it is how a chain that died
    without recording a failure gets picked back up.
    """
    if job.lease_expires_on and job.lease_expires_on > now:
        return True

    lease_seconds = ARCHIVES_LEASE_SECONDS if job.job_type == ARCHIVES_JOB_TYPE else RESULTS_LEASE_SECONDS
    stale_after = now - timedelta(seconds=2 * lease_seconds)

    return job.status == SyncJob.STATUS_RUNNING and bool(job.modified_on) and job.modified_on > stale_after
