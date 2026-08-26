# -*- coding: utf-8 -*-

import json
import logging

from django.core.cache import cache
from django.utils import timezone

from dash.orgs.models import Org, TaskState
from ureport.backend import BaseBackend
from ureport.celery import app
from ureport.contacts.models import Contact
from ureport.syncjobs.dispatch import enqueue, in_flight
from ureport.syncjobs.locks import chunk_lock
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
# each one unbounded pull, and a lease that expires mid chunk loses that chunk's work. It is
# also what tells beat a running job has stopped moving, see syncjobs.dispatch.in_flight
LEASE_SECONDS = 60 * 30


def _last_fetched_key(org, backend_slug):
    return Contact.CONTACT_LAST_FETCHED_CACHE_KEY % (org.pk, backend_slug)


def _counts(prefix, counts):
    return {f"{prefix}_{key}": value for key, value in counts.items()}


def _is_disabled(org):
    return TaskState.objects.filter(org=org, task_key=JOB_TYPE, is_disabled=True).exists()


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

    if _is_disabled(org):
        logger.info("Contact pull disabled for org #%d, stopping", org.pk)
        return _abort_run(job, cursor)

    with _contact_pull_lock(org) as acquired:
        if not acquired:
            logger.info("Contact pull lock held for org #%d, backing off", org.pk)
            return job.back_off(LOCK_BACKOFF)

        try:
            return _run_chunk(job, org, backend_obj, cursor)
        except LeaseLost:
            # not our run to report on anymore - the worker that took it over owns its outcome
            raise
        except Exception:
            _mark_state_failing(org)
            raise


def _contact_pull_lock(org):
    """
    The lock the ad-hoc contact tasks still coordinate through: two of them rebuild counters
    and need exclusive access, and the mismatch check reads it to tell a sync in progress
    from real drift.
    """
    return chunk_lock(TaskState.get_lock_key(org, JOB_TYPE), LEASE_SECONDS)


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
        job.checkpoint(cursor=cursor, progress=job.add_progress(chunks=1, **_counts("fields", counts)))
        return False

    if stage == STAGE_BOUNDARIES:
        counts = BaseBackend._outcome_counts_dict(backend.pull_boundaries(org))
        cursor["stage"] = STAGE_CONTACTS
        job.checkpoint(cursor=cursor, progress=job.add_progress(chunks=1, **_counts("boundaries", counts)))
        return False

    result = backend.pull_contacts_chunk(org, cursor.get("since"), cursor.get("until"), cursor.get("resume") or {})
    progress = job.add_progress(chunks=1, **_counts("contacts", result.counts))

    if result.done:
        # window end becomes the next run's start, and what finalization dual-writes
        job.checkpoint(cursor={"last_until": cursor.get("until")}, progress=progress)
        return True

    cursor["resume"] = result.cursor
    job.checkpoint(cursor=cursor, progress=progress)

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

    return job.abort(cursor=cursor)


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

        if job.status == SyncJob.STATUS_PAUSED or in_flight(job, now):
            logger.info("Job #%d (%s:%s) not nudged, %s", job.id, JOB_TYPE, job.scope, job.get_status_display())
            skipped[backend_obj.slug] = job.id
            continue

        enqueued[backend_obj.slug] = job.id
        enqueue(job)

    return {"enqueued": enqueued, "skipped": skipped}


@app.task(name="contacts.sync_contacts_dispatch")
def sync_contacts_dispatch():
    disabled = set(TaskState.objects.filter(task_key=JOB_TYPE, is_disabled=True).values_list("org_id", flat=True))

    for org in Org.objects.filter(is_active=True):
        # the per org kill switch the pre-chunking task honored
        if org.id in disabled:
            logger.info("Contact pull disabled for org #%d, skipping", org.id)
            continue

        enqueue_org_syncs(org)
