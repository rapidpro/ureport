# -*- coding: utf-8 -*-

import logging
from collections import defaultdict, namedtuple

from django.core.cache import cache
from django.utils import timezone

from dash.orgs.models import Org
from ureport.contacts.models import Contact
from ureport.contacts.sync import (
    JOB_TYPE as PULL_JOB_TYPE,
    LOCK_BACKOFF,
    contact_pull_lock,
    enqueue_org_syncs,
    force_full_repull,
    is_in_flight,
    is_pull_disabled,
)
from ureport.stats.models import ContactActivity
from ureport.syncjobs.models import SyncJob
from ureport.syncjobs.tasks import chunked_task
from ureport.utils import chunk_list, datetime_to_json_date, json_date_to_datetime

logger = logging.getLogger(__name__)

REBUILD_JOB_TYPE = "reporters-rebuild"
ACTIVITIES_JOB_TYPE = "schemes-activities"
RESULTS_JOB_TYPE = "schemes-results"

QUEUE = "slow"

# these chunks read or replace every contact of an org, so like the contact sync they need a
# lease that comfortably exceeds the slowest of them
LEASE_SECONDS = 60 * 30

# the rebuild's lock has to outlive its lease: they would otherwise expire together, freeing
# a second worker to claim the job at the moment the lock stops keeping it out - and two
# concurrent rebuilds of the same counters leave them permanently wrong
REBUILD_LOCK_TIMEOUT = LEASE_SECONDS * 2

# the batch the pre-chunking backfills walked contacts in, and how many of them one chunk
# takes on before handing back to the queue
BATCH_SIZE = 1000
BATCHES_PER_CHUNK = 5

# set by the schemes backfill trigger while it waits for the full re-pull it asked for, and
# read by the contact sync's finalization - the value is when the wait started. Given a TTL
# so that a wait nothing can ever satisfy, e.g. an org whose last backend is deactivated
# while it waits, expires instead of blocking the backfill forever. Scaffolding for the one
# off backfill - remove it with the shims
PENDING_KEY = "schemes_backfill_pending:%d"
PENDING_TTL = 60 * 60 * 24 * 2

# how long the trigger waits before trying again to reset a backend that was busy
TRIGGER_RETRY = 60

# the pre-chunking flag recording that an org's contacts have had their schemes pulled
POPULATED_KEY = "schemes_populated:%d"


def _update_contact_activities(org_id, by_scheme):
    for scheme, uuids in by_scheme.items():
        ContactActivity.objects.filter(org_id=org_id, contact__in=uuids).update(scheme=scheme)


def _update_poll_results(org_id, by_scheme):
    from ureport.polls.models import PollResult

    for scheme, uuids in by_scheme.items():
        # as the pre-chunking task did, this isn't scoped to the org - a contact uuid that two
        # orgs' backends both know would have both orgs' results updated
        PollResult.objects.filter(contact__in=uuids).update(scheme=scheme)


# one of the one-off backfills that copy Contact.scheme onto the rows keyed by contact uuid.
# both keep the pre-chunking task's cache keys - the done flag as a skip condition and dual
# written on completion, the max id as a seed - so that neither redoes the other's work
SchemesBackfill = namedtuple("SchemesBackfill", ("done_key", "cursor_key", "update_rows"))

ACTIVITIES_BACKFILL = SchemesBackfill(
    done_key="contact_activities_schemes_populated:%d",
    cursor_key="contact_activities_schemes_max_id:%d",
    update_rows=_update_contact_activities,
)

RESULTS_BACKFILL = SchemesBackfill(
    done_key="poll_results_schemes_populated:%d",
    cursor_key="poll_results_schemes_max_id:%d",
    update_rows=_update_poll_results,
)


@chunked_task(REBUILD_JOB_TYPE, queue=QUEUE, lease_seconds=LEASE_SECONDS, name="contacts.rebuild_reporters_counts")
def rebuild_reporters_counts(job):
    """
    Rebuilds one org's reporter counters. The recalculation replaces every counter the org has
    in one go, so there is nothing finer to resume from - the job is a single chunk with a
    lease long enough to cover it. It takes the contact pull lock for the same reason the
    pre-chunking task did: the counters it replaces are the ones a running sync increments.
    """
    org = job.org
    if not org:
        return True

    with contact_pull_lock(org, timeout=REBUILD_LOCK_TIMEOUT) as acquired:
        if not acquired:
            logger.info("Contact pull lock held for org #%d, backing off rebuild", org.pk)
            job.checkpoint(progress=job.add_progress(lock_backoffs=1), lease_seconds=LEASE_SECONDS)
            return LOCK_BACKOFF

        Contact.recalculate_reporters_stats(org)
        job.checkpoint(progress=job.add_progress(chunks=1), lease_seconds=LEASE_SECONDS)

    return True


def _run_schemes_chunk(job, backfill):
    """
    Runs one chunk of a schemes backfill: a bounded number of batches of the org's contacts,
    in id order, with the id reached checkpointed after each batch. The row updates autocommit,
    so a chunk that dies part way through replays from its last checkpoint - which costs
    nothing, every update is last value wins.
    """
    org_id = job.org_id
    if not org_id:
        return True

    if cache.get(backfill.done_key % org_id):
        logger.info("Backfill %s already done for org #%d, skipping", job.job_type, org_id)
        job.checkpoint(progress=job.add_progress(skipped=1), lease_seconds=LEASE_SECONDS)
        return True

    max_id = job.cursor.get("max_id")
    if max_id is None:
        # nothing resumed yet, so carry on from where the pre-chunking task got to - a batch
        # behind it, as it wrote that position per contact rather than per completed batch
        max_id = max(0, cache.get(backfill.cursor_key % org_id, 0) - BATCH_SIZE)

    chunk_size = BATCH_SIZE * BATCHES_PER_CHUNK
    contact_ids = list(
        Contact.objects.filter(org_id=org_id, is_active=True, id__gt=max_id)
        .exclude(scheme=None)
        .exclude(scheme="")
        .order_by("id")
        .values_list("id", flat=True)[:chunk_size]
    )

    for batch in chunk_list(contact_ids, BATCH_SIZE):
        batch_ids = list(batch)

        # a batch is a handful of schemes over a thousand contacts, so it's one update per
        # distinct scheme rather than one per contact
        by_scheme = defaultdict(list)
        for uuid, scheme in Contact.objects.filter(id__in=batch_ids).values_list("uuid", "scheme"):
            by_scheme[scheme].append(uuid)

        backfill.update_rows(org_id, by_scheme)

        job.checkpoint(
            cursor={"max_id": batch_ids[-1]},
            progress=job.add_progress(chunks=1, contacts=len(batch_ids)),
            lease_seconds=LEASE_SECONDS,
        )
        # dual written so that rolling back to the pre-chunking task resumes here too
        cache.set(backfill.cursor_key % org_id, batch_ids[-1], None)

    # a short chunk means there was nothing left behind it
    return len(contact_ids) < chunk_size


def _mark_backfill_done(job, backfill):
    """
    Dual writes the pre-chunking task's done flag, which is what both it and the trigger below
    read to know an org is finished. Idempotent, and only written when absent so that a re-run
    doesn't move the completion time it records.
    """
    if not job.org_id:
        return

    key = backfill.done_key % job.org_id
    if not cache.get(key):
        cache.set(key, datetime_to_json_date(timezone.now()), None)


def finalize_schemes_activities(job):
    _mark_backfill_done(job, ACTIVITIES_BACKFILL)

    # the pre-chunking task chained the poll results backfill after this one, and this is
    # where that chain now lives
    if job.org:
        enqueue_schemes_results(job.org)


def finalize_schemes_results(job):
    _mark_backfill_done(job, RESULTS_BACKFILL)


@chunked_task(
    ACTIVITIES_JOB_TYPE,
    queue=QUEUE,
    lease_seconds=LEASE_SECONDS,
    finalize=finalize_schemes_activities,
    name="contacts.backfill_activities_schemes",
)
def backfill_activities_schemes(job):
    return _run_schemes_chunk(job, ACTIVITIES_BACKFILL)


@chunked_task(
    RESULTS_JOB_TYPE,
    queue=QUEUE,
    lease_seconds=LEASE_SECONDS,
    finalize=finalize_schemes_results,
    name="contacts.backfill_results_schemes",
)
def backfill_results_schemes(job):
    return _run_schemes_chunk(job, RESULTS_BACKFILL)


def _enqueue_org_job(org, job_type, task):
    """
    Ensures this org has the given job and nudges it unless a run is already being driven.
    Returns the job and whether it was nudged.
    """
    job = SyncJob.get_or_create_job(org, job_type)

    if job.status == SyncJob.STATUS_PAUSED or is_in_flight(job, timezone.now()):
        logger.info("Job #%d (%s) not nudged, %s", job.id, job_type, job.get_status_display())
        return job, False

    task.apply_async((job.id,), queue=QUEUE)
    return job, True


def enqueue_reporters_rebuilds(org_id=None):
    """
    Ensures a counter rebuild job exists and is enqueued for every active org, or for just the
    one given. Returns the enqueued and skipped job ids by org id.
    """
    orgs = Org.objects.filter(is_active=True)
    if org_id is not None:
        orgs = orgs.filter(id=org_id)

    enqueued = {}
    skipped = {}

    for org in orgs:
        job, nudged = _enqueue_org_job(org, REBUILD_JOB_TYPE, rebuild_reporters_counts)
        (enqueued if nudged else skipped)[org.id] = job.id

    return {"enqueued": enqueued, "skipped": skipped}


def enqueue_schemes_activities(org):
    job, _ = _enqueue_org_job(org, ACTIVITIES_JOB_TYPE, backfill_activities_schemes)
    return job.id


def enqueue_schemes_results(org):
    job, _ = _enqueue_org_job(org, RESULTS_JOB_TYPE, backfill_results_schemes)
    return job.id


def start_schemes_backfill(org):
    """
    Triggers the one-off schemes backfill for an org. The half of the pre-chunking task that
    re-pulled every contact so that they had schemes is superseded by the chunked contact
    sync, so this asks that sync for a full re-pull instead and leaves a marker the sync's
    finalization picks up.

    The wait is deliberate. The backfill only visits contacts that already have a scheme and
    never looks back at the ids it has passed, so running it alongside the re-pull that fills
    those schemes in would silently leave gaps - and the done flag it sets on completion would
    stop it ever revisiting them. Ordering the two, as the pre-chunking task did, is what
    makes the flag safe to trust.

    The marker is only left once every active backend has actually had its resume position
    dropped. A backend still busy with an ordinary incremental run would otherwise finish it,
    satisfy the wait, and have the backfill read contacts that were never re-pulled - so a
    trigger that couldn't reset one comes back for it instead. With all the resets ahead of
    the marker, a run completing after it either pulled the widened window or is a run that
    started before it, which the wait ignores.
    """
    if is_pull_disabled(org):
        # the per org kill switch the pre-chunking org task honored - without a pull there is
        # nothing to re-pull with, and a marker left here would wait forever
        logger.info("Contact pull disabled for org #%d, not starting schemes backfill", org.id)
        return {"repulled": [], "skipped": [], "backfill": None, "disabled": True}

    if cache.get(POPULATED_KEY % org.id):
        logger.info("Contact schemes already pulled for org #%d, backfilling only", org.id)
        return {"repulled": [], "skipped": [], "backfill": enqueue_schemes_activities(org)}

    repulled, skipped = force_full_repull(org)

    if skipped:
        # resetting is idempotent, so the retry just picks up the ones left behind
        logger.info("Backends %s busy for org #%d, retrying the schemes backfill trigger", skipped, org.id)
        _retry_trigger(org)
        return {"repulled": repulled, "skipped": skipped, "backfill": None, "retry_in": TRIGGER_RETRY}

    if not repulled:
        # nothing to re-pull from, so there is nothing for the backfill to wait on
        return {"repulled": [], "skipped": [], "backfill": enqueue_schemes_activities(org)}

    # marked after every re-pull is set up and before any is triggered, so that only a run
    # whose window this trigger widened can satisfy the wait
    cache.set(PENDING_KEY % org.id, datetime_to_json_date(timezone.now()), PENDING_TTL)
    enqueue_org_syncs(org)

    return {"repulled": repulled, "skipped": [], "backfill": None}


def _retry_trigger(org):
    # imported here as the shim it re-enqueues is the caller of this module
    from ureport.contacts.tasks import populate_contact_schemes

    populate_contact_schemes.apply_async((org.id,), queue=QUEUE, countdown=TRIGGER_RETRY)


def resume_schemes_backfill(org):
    """
    Starts the schemes backfill an earlier trigger left pending, once every active backend of
    the org has pulled its contacts afresh. Called from the contact sync's finalization, so it
    runs on the completion of each backend's run until they have all had one.

    Two finalizations racing here both start the backfill, which costs nothing - they nudge
    the same job and the framework's claim lets only one run of it proceed.

    Only used by the one-off schemes backfill trigger - remove it with the shims.
    """
    pending = cache.get(PENDING_KEY % org.id)
    if not pending or not _pulled_since(org, json_date_to_datetime(pending)):
        return

    cache.delete(PENDING_KEY % org.id)

    # the re-pull this waited for is what the flag records, and it's what stops a later
    # trigger re-pulling the whole org again
    cache.set(POPULATED_KEY % org.id, datetime_to_json_date(timezone.now()), None)

    enqueue_schemes_activities(org)


def _pulled_since(org, since):
    """
    Whether every active backend of the org has completed a contact sync run that started
    after the given time - i.e. one that pulled with the widened window.
    """
    jobs = {job.scope: job for job in SyncJob.objects.filter(org=org, job_type=PULL_JOB_TYPE)}

    for backend_obj in org.backends.filter(is_active=True):
        job = jobs.get(backend_obj.slug)
        if not job or job.status != SyncJob.STATUS_COMPLETE or not job.started_on or job.started_on < since:
            return False

    return True
