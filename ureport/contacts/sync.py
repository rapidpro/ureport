# -*- coding: utf-8 -*-

import json
import logging
from contextlib import contextmanager
from datetime import timedelta

from django_valkey import get_valkey_connection
from valkey.exceptions import LockError

from django.core.cache import cache
from django.utils import timezone

from dash.orgs.models import Org, TaskState
from ureport.backend import BaseBackend
from ureport.celery import app
from ureport.contacts.models import Contact
from ureport.syncjobs.models import LeaseLost, SyncJob
from ureport.syncjobs.tasks import chunked_task
from ureport.utils import datetime_to_json_date, update_cache_org_contact_counts

logger = logging.getLogger(__name__)

JOB_TYPE = "contact-pull"
QUEUE = "celery"

# a run is fields, then boundaries, then however many chunks of contacts it takes
STAGE_FIELDS = "fields"
STAGE_BOUNDARIES = "boundaries"
STAGE_CONTACTS = "contacts"

# how long to wait before the next chunk when the backend exhausted its API rate limit
RATE_LIMIT_BACKOFF = 60

# how long to wait when another contact task holds this org's contact-pull lock
LOCK_BACKOFF = 300

# must comfortably exceed the slowest single chunk - the fields and boundaries stages are
# each one unbounded pull, and a lease that expires mid chunk loses that chunk's work
LEASE_SECONDS = 60 * 30

# a running job is driven by its own continuations, so beat only nudges one again if it has
# gone this long without checkpointing - i.e. its continuation was lost, not just slow
STALE_RUN_AFTER = timedelta(seconds=LEASE_SECONDS * 2)


def _last_fetched_key(org, backend_slug):
    return Contact.CONTACT_LAST_FETCHED_CACHE_KEY % (org.pk, backend_slug)


def _counts(prefix, counts):
    return {f"{prefix}_{key}": value for key, value in counts.items()}


def is_pull_disabled(org):
    return TaskState.objects.filter(org=org, task_key=JOB_TYPE, is_disabled=True).exists()


@contextmanager
def contact_pull_lock(org, timeout=LEASE_SECONDS):
    """
    Takes this org's contact-pull lock for the duration of one chunk, yielding whether it was
    taken. It is the lock all of the contact tasks coordinate through: the ones that rebuild
    counters need exclusive access while they do, and the mismatch check reads it to tell a
    sync in progress from real drift. Never blocks - a chunk that can't have it should back
    off and try again rather than tie up a worker.

    The timeout must outlive the caller's lease, or a chunk that overruns its lease loses the
    lock at the same moment another worker becomes free to claim the job, and the two run
    concurrently - which is exactly what the lock is there to prevent.
    """
    lock = get_valkey_connection().lock(TaskState.get_lock_key(org, JOB_TYPE), timeout=timeout)
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
                logger.warning("Unable to release contact pull lock for org #%d as it is no longer owned", org.pk)


def _mark_state_failing(org):
    """
    Best effort - the failure that brought us here is what matters, not this bookkeeping.
    """
    try:
        state = TaskState.get_or_create(org, JOB_TYPE)
        state.ended_on = timezone.now()
        state.is_failing = True
        state.save(update_fields=("ended_on", "is_failing"))
    except Exception:
        logger.exception("Unable to record contact pull failure for org #%d", org.pk)


def finalize_contacts_sync(job):
    """
    Runs once per completed run: refreshes the org's cached contact counts and dual-writes
    the state the pre-chunking task kept - the cache key it resumed from, so that rolling
    back to it doesn't re-pull everything, and the org's task state, which is what the task
    status endpoint and the org admin screens report contact syncing from. Idempotent - all
    of these writes are last-value-wins.
    """
    org = job.org
    if not org:
        return

    # an aborted run stopped without covering its window, so none of the below is true of it
    if job.progress.get("aborted"):
        logger.info("Job #%d (%s:%s) aborted, skipping finalization", job.id, JOB_TYPE, job.scope)
        return

    update_cache_org_contact_counts(org)

    last_until = job.cursor.get("last_until")
    if last_until:
        cache.set(_last_fetched_key(org, job.scope), last_until, None)

    state = TaskState.get_or_create(org, JOB_TYPE)
    results = state.get_last_results() or {}
    results[job.scope] = job.progress

    state.started_on = job.started_on
    state.ended_on = job.ended_on
    # the freshness this feeds is "are contacts up to date", so it's when the run finished
    # that matters - a resumed run's started_on can be hours before it caught up
    state.last_successfully_started_on = job.ended_on or timezone.now()
    state.last_results = json.dumps(results)
    state.is_failing = False
    state.save(update_fields=("started_on", "ended_on", "last_successfully_started_on", "last_results", "is_failing"))

    # the one-off schemes backfill waits here because it reads what a pull writes - imported
    # locally as the maintenance tasks build on this module
    from ureport.contacts.maintenance import resume_schemes_backfill

    resume_schemes_backfill(org)


@chunked_task(
    JOB_TYPE, queue=QUEUE, lease_seconds=LEASE_SECONDS, finalize=finalize_contacts_sync, name="contacts.sync_contacts"
)
def sync_contacts(job):
    """
    Pulls one chunk of a contact sync for one org backend. The cursor carries the stage the
    run has reached and the (since, until) window it is pulling, frozen when the run starts
    and rolled forward only when the run completes - the backend's own resume position is
    only valid against the window it was created for.
    """
    org = job.org
    cursor = dict(job.cursor)

    backend_obj = org.backends.filter(is_active=True, slug=job.scope).first() if org else None
    if not backend_obj:
        logger.info("Backend %s no longer active for org #%s, nothing to sync", job.scope, org.pk if org else None)
        return _abort_run(job, cursor)

    if is_pull_disabled(org):
        logger.info("Contact pull disabled for org #%d, stopping", org.pk)
        return _abort_run(job, cursor)

    with contact_pull_lock(org) as acquired:
        if not acquired:
            logger.info("Contact pull lock held for org #%d, backing off", org.pk)
            return LOCK_BACKOFF

        try:
            return _run_chunk(job, org, backend_obj, cursor)
        except LeaseLost:
            # not our run to report on anymore - the worker that took it over owns its outcome
            raise
        except Exception:
            _mark_state_failing(org)
            raise


def _run_chunk(job, org, backend_obj, cursor):
    backend = org.get_backend(backend_slug=backend_obj.slug)
    stage = cursor.get("stage")

    if not stage:
        # no run in flight - roll the window forward from where the last run ended, seeding
        # from the pre-chunking cache key the first time this job runs
        since = cursor.get("last_until") or cache.get(_last_fetched_key(org, job.scope), None)
        if not since:
            logger.info("First time run for org #%d. Will sync all contacts", org.pk)

        stage = STAGE_FIELDS
        cursor = {"stage": stage, "since": since, "until": datetime_to_json_date(timezone.now())}

    if stage == STAGE_FIELDS:
        counts = BaseBackend._outcome_counts_dict(backend.pull_fields(org))
        cursor["stage"] = STAGE_BOUNDARIES
        _checkpoint(job, cursor, job.add_progress(chunks=1, **_counts("fields", counts)))
        return False

    if stage == STAGE_BOUNDARIES:
        counts = BaseBackend._outcome_counts_dict(backend.pull_boundaries(org))
        cursor["stage"] = STAGE_CONTACTS
        _checkpoint(job, cursor, job.add_progress(chunks=1, **_counts("boundaries", counts)))
        return False

    result = backend.pull_contacts_chunk(org, cursor.get("since"), cursor.get("until"), cursor.get("resume") or {})
    progress = job.add_progress(chunks=1, **_counts("contacts", result.counts))

    if result.done:
        # window end becomes the next run's start, and what finalization dual-writes
        _checkpoint(job, {"last_until": cursor.get("until")}, progress)
        return True

    cursor["resume"] = result.cursor
    _checkpoint(job, cursor, progress)

    return RATE_LIMIT_BACKOFF if result.rate_limited else False


def _abort_run(job, cursor):
    """
    Ends a run that can't finish its window - the backend went away or the pull was disabled
    - without rolling the window forward, so the next run re-pulls it rather than skipping
    contacts. Re-pulling is free of consequence, every write is an upsert. Any in-flight
    page cursor is dropped with the window it belongs to, and the run is marked aborted so
    finalization knows not to report it as a completed sync.
    """
    if cursor.get("stage"):
        since = cursor.get("since")
        cursor = {"last_until": since} if since else {}

    _checkpoint(job, cursor, job.add_progress(aborted=1))
    return True


def _checkpoint(job, cursor, progress):
    job.checkpoint(cursor=cursor, progress=progress, lease_seconds=LEASE_SECONDS)


def enqueue_org_syncs(org):
    """
    Ensures this org has a contact sync job per active backend and nudges each one that
    isn't already being worked on. Returns the enqueued and skipped job ids by backend slug.
    """
    enqueued = {}
    skipped = {}
    now = timezone.now()

    for backend_obj in org.backends.filter(is_active=True):
        job = SyncJob.get_or_create_job(org, JOB_TYPE, scope=backend_obj.slug)

        if job.status == SyncJob.STATUS_PAUSED or is_in_flight(job, now):
            logger.info("Job #%d (%s:%s) not nudged, %s", job.id, JOB_TYPE, job.scope, job.get_status_display())
            skipped[backend_obj.slug] = job.id
            continue

        enqueued[backend_obj.slug] = job.id
        sync_contacts.apply_async((job.id,), queue=QUEUE)

    return {"enqueued": enqueued, "skipped": skipped}


def is_in_flight(job, now):
    """
    Whether a run is already being driven, so that nudging it would only start a duplicate
    chain of chunks. The lease is released between chunks, so a running job counts as in
    flight until its continuation stops arriving - after which beat is what recovers it.
    """
    if job.lease_expires_on and job.lease_expires_on > now:
        return True

    return job.status == SyncJob.STATUS_RUNNING and job.modified_on > now - STALE_RUN_AFTER


def force_full_repull(org):
    """
    Makes this org's next contact sync run pull its whole history again, by dropping both
    resume positions a run can start from - the job cursor and the pre-chunking cache key it
    seeds from. A job with a run being driven is left alone rather than having the window
    pulled out from under it. Idempotent, so a caller that needs every backend reset can keep
    trying until none are left alone. Returns the backend slugs reset and those left alone.

    Only used by the one-off schemes backfill trigger - remove it with the shims.
    """
    now = timezone.now()
    reset = []
    skipped = []

    for backend_obj in org.backends.filter(is_active=True):
        job = SyncJob.get_or_create_job(org, JOB_TYPE, scope=backend_obj.slug)

        # gated on the lease as well as on being in flight, so that a claim landing between
        # the two wins rather than having the cursor pulled out from under it
        if not is_in_flight(job, now) and SyncJob.objects.filter(id=job.id, lease_owner=None).update(cursor={}):
            # only once the cursor is actually gone, or a refused reset would still drop the
            # seed the next run would have resumed from
            cache.delete(_last_fetched_key(org, backend_obj.slug))
            reset.append(backend_obj.slug)
            continue

        logger.warning("Job #%d (%s:%s) is in flight, resume position left alone", job.id, JOB_TYPE, job.scope)
        skipped.append(backend_obj.slug)

    return reset, skipped


@app.task(name="contacts.sync_contacts_dispatch")
def sync_contacts_dispatch():
    disabled = set(TaskState.objects.filter(task_key=JOB_TYPE, is_disabled=True).values_list("org_id", flat=True))

    for org in Org.objects.filter(is_active=True):
        # the per org kill switch the pre-chunking task honored
        if org.id in disabled:
            logger.info("Contact pull disabled for org #%d, skipping", org.id)
            continue

        enqueue_org_syncs(org)
