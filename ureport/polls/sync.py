# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from dash.orgs.models import Org
from ureport.celery import app
from ureport.syncjobs.dispatch import Backoff, enqueue, is_due
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

# progress marker for an archives cursor reset that couldn't be applied yet
ARCHIVES_RESET_PENDING = "archives_reset_pending"

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

# how many polls a maintenance chunk walks - pruning is the heaviest, it deletes results
COUNTS_CHUNK_SIZE = 5
PRUNE_CHUNK_SIZE = 3
AGE_GENDER_CHUNK_SIZE = 5

# the age and gender backfill walks contacts a batch at a time, checkpointing each batch,
# and does a few of them per chunk so a big org doesn't need a message per thousand contacts
POPULATE_BATCH_SIZE = 1000
POPULATE_BATCHES_PER_CHUNK = 5

# results of polls whose date is older than this are dropped, unless the poll itself was
# only created recently, i.e. it's an old poll someone is still setting up
RESULTS_RETENTION = timedelta(days=365)
NEW_POLL_WINDOW = timedelta(days=14)

# an age and gender backfill populates the results, then rebuilds what they feed
STAGE_POPULATE = "populate"
STAGE_REBUILD = "rebuild"

# what a prune did with a poll, kept apart in the job's counters so that a poll failing
# every run is distinguishable from one that was merely busy
PRUNE_CLEARED = "cleared"
PRUNE_SKIPPED_SYNCING = "skipped_syncing"
PRUNE_SKIPPED_RETIRED = "skipped_retired"
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

    reset = job.reset_cursor()
    if not reset:
        logger.warning("Archives job #%d is still running, deferring its cursor reset" % job.id)

    enqueue(job)
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

    progress = _set_reset_pending(job.add_progress(chunks=1, **result.counts), reset_pending)
    job.checkpoint(cursor=result.cursor, progress=progress)

    if result.done:
        return True

    if progress.get("chunks", 0) % REBUILD_COUNTS_EVERY == 0:
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
    poll = get_job_poll(job.org_id, job.scope)
    if not poll:
        return True

    result = _get_backend(poll).pull_results_from_archives_chunk(poll, dict(job.cursor or {}))

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
    task held for the whole pass. Each run walks every syncing poll once, in pk order, and
    the next run starts over from the first of them.
    """
    from ureport.polls.models import Poll

    if job.new_run:
        # a run has to cover every poll, so the position the last one left behind is dropped
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
        Poll.objects.filter(is_active=True, stopped_syncing=False, pk__gt=after_pk).order_by("pk")[:COUNTS_CHUNK_SIZE]
    )
    if not polls:
        return True

    for poll in polls:
        poll.rebuild_poll_results_counts()

        # checkpointed per poll rather than per chunk: rebuilding a big flow can take
        # minutes, and a chunk that ran out of lease must not write on
        job.checkpoint(cursor={"after_pk": poll.pk}, progress=job.add_progress(rebuilt=1))

    return False


@chunked_task(
    PRUNE_JOB_TYPE, queue=SLOW_QUEUE, lease_seconds=MAINTENANCE_LEASE_SECONDS, name="polls.prune_poll_results"
)
def prune_poll_results(job):
    """
    Retires a bounded number of an org's polls that are too old to keep syncing: their
    counts are rebuilt one last time, their results deleted, and every poll on the flow
    marked as no longer syncing. Polls whose flow is still being synced are stepped over
    rather than waited for, and reconsidered by a later run.
    """
    from ureport.polls.models import Poll

    org = job.org
    now = timezone.now()

    if job.new_run:
        # a run reconsiders every old poll, so it starts from the first of them - see
        # rebuild_poll_counts for why that reset is checkpointed before any work
        job.checkpoint(cursor={})

    after_pk = (job.cursor or {}).get("after_pk") or 0

    polls = list(
        Poll.objects.filter(org=org, pk__gt=after_pk)
        .exclude(poll_date__gte=now - RESULTS_RETENTION)
        .exclude(created_on__gte=now - NEW_POLL_WINDOW)
        .exclude(stopped_syncing=True)
        .order_by("pk")[:PRUNE_CHUNK_SIZE]
    )
    if not polls:
        return True

    for poll in polls:
        outcome = _clear_poll_results(org, poll)

        # the position advances past a poll that was skipped or errored too, so that one
        # unhappy poll can't stall everything behind it - the next run reconsiders it
        job.checkpoint(cursor={"after_pk": poll.pk}, progress=job.add_progress(**{outcome: 1}))

    return False


def _clear_poll_results(org, poll):
    """
    Retires one poll, returning what became of it. A flow still being synced is left alone
    - its results must not be deleted mid traversal - and so is a poll whose flow another
    poll already retired, which is how the duplicated polls of a flow are recognised now
    that a chunk can't carry a set of them forward in memory.
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

        if poll.stopped_syncing:
            logger.info(
                "Skipping clearing old results for poll #%d on org #%d as it appear to be duplicated"
                % (poll.pk, org.pk)
            )
            return PRUNE_SKIPPED_RETIRED

        try:
            # one last stats rebuild for the poll, while its results are still there
            poll.rebuild_poll_results_counts()

            # retiring the flow before deleting its results, so that a delete interrupted
            # part way leaves a flow that is durably retired on the counts just rebuilt,
            # rather than one still syncing on results that are half gone
            Poll.objects.filter(org=org, flow_uuid=poll.flow_uuid).update(stopped_syncing=True)
            poll.delete_poll_results()

            logger.info("Cleared poll results and stopped syncing for poll #%s on org #%s" % (poll.id, poll.org_id))
        except Exception:
            # one poll that fails every time would otherwise stall every poll after it, as
            # the traversal can only move past polls it has finished with
            logger.error(
                "Error clearing old poll results for poll #%s on org #%s" % (poll.id, poll.org_id),
                exc_info=True,
                extra={"stack": True},
            )
            return PRUNE_ERRORED

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
