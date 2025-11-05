# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import time

from celery.utils.log import get_task_logger
from django_valkey import get_valkey_connection

from django.core.cache import cache
from django.utils import timezone

from dash.orgs.models import Org, TaskState
from dash.orgs.tasks import org_task
from dash.utils.sync import SyncOutcome
from ureport.celery import app
from ureport.contacts.models import Contact, ReportersCounter
from ureport.stats.models import ContactActivity
from ureport.utils import chunk_list, datetime_to_json_date, update_cache_org_contact_counts

logger = get_task_logger(__name__)


@app.task(name="contacts.rebuild_contacts_counts")
def rebuild_contacts_counts():
    r = get_valkey_connection()
    orgs = Org.objects.filter(is_active=True)
    for org in orgs:
        key = TaskState.get_lock_key(org, "contact-pull")
        with r.lock(key):
            Contact.recalculate_reporters_stats(org)


@app.task(name="contacts.check_contacts_count_mismatch")
def check_contacts_count_mismatch():
    r = get_valkey_connection()
    orgs = Org.objects.filter(is_active=True).order_by("pk")

    error_counts = dict()
    mismatch_counts = dict()

    for org in orgs:
        key = TaskState.get_lock_key(org, "contact-pull")
        db_contacts_counts = Contact.objects.filter(org=org, is_active=True).count()
        counter_counts = ReportersCounter.get_counts(org).get("total-reporters", 0)

        count_diff = abs(db_contacts_counts - counter_counts)
        pct_diff = 0
        if db_contacts_counts:
            pct_diff = count_diff / db_contacts_counts

        if r.get(key):
            if count_diff:
                mismatch_counts[f"{org.id}"] = dict(
                    db=db_contacts_counts,
                    count=counter_counts,
                    count_diff=count_diff,
                    pct_diff=pct_diff,
                    message="contact task running",
                )
        else:
            if count_diff:
                mismatch_counts[f"{org.id}"] = dict(
                    db=db_contacts_counts, count=counter_counts, count_diff=count_diff, pct_diff=pct_diff
                )
            if count_diff > 50 or pct_diff > 0.025:
                error_counts[f"{org.id}"] = dict(
                    db=db_contacts_counts, count=counter_counts, count_diff=count_diff, pct_diff=pct_diff
                )

    output = dict(mismatch_counts=mismatch_counts, error_counts=error_counts)
    cache.set("contact_counts_status", output, None)


@org_task("update-org-contact-counts", 60 * 20)
def update_org_contact_count(org, ignored_since, ignored_until):
    update_cache_org_contact_counts(org)


@org_task("contact-pull", 60 * 60 * 12)
def pull_contacts(org, ignored_since, ignored_until):
    """
    Fetches updated contacts from RapidPro and updates local contacts accordingly
    """
    # from ureport.contacts.models import ReportersCounter

    results = dict()

    backends = org.backends.filter(is_active=True)
    for backend_obj in backends:
        backend = org.get_backend(backend_slug=backend_obj.slug)

        last_fetch_date_key = Contact.CONTACT_LAST_FETCHED_CACHE_KEY % (org.pk, backend_obj.slug)

        until = datetime_to_json_date(timezone.now())
        since = cache.get(last_fetch_date_key, None)

        if not since:
            logger.info("First time run for org #%d. Will sync all contacts" % org.pk)

        start = time.time()

        backend_fields_results = backend.pull_fields(org)

        fields_created = backend_fields_results[SyncOutcome.created]
        fields_updated = backend_fields_results[SyncOutcome.updated]
        fields_deleted = backend_fields_results[SyncOutcome.deleted]
        ignored = backend_fields_results[SyncOutcome.ignored]

        logger.info(
            "Fetched contact fields for org #%d. "
            "Created %s, Updated %s, Deleted %d, Ignored %d"
            % (org.pk, fields_created, fields_updated, fields_deleted, ignored)
        )
        logger.info("Fetch fields for org #%d took %ss" % (org.pk, time.time() - start))

        start_boundaries = time.time()

        backend_boundaries_results = backend.pull_boundaries(org)

        boundaries_created = backend_boundaries_results[SyncOutcome.created]
        boundaries_updated = backend_boundaries_results[SyncOutcome.updated]
        boundaries_deleted = backend_boundaries_results[SyncOutcome.deleted]
        ignored = backend_boundaries_results[SyncOutcome.ignored]

        logger.info(
            "Fetched boundaries for org #%d. "
            "Created %s, Updated %s, Deleted %d, Ignored %d"
            % (org.pk, boundaries_created, boundaries_updated, boundaries_deleted, ignored)
        )

        logger.info("Fetch boundaries for org #%d took %ss" % (org.pk, time.time() - start_boundaries))
        start_contacts = time.time()

        backend_contact_results, resume_cursor = backend.pull_contacts(org, since, until)

        contacts_created = backend_contact_results[SyncOutcome.created]
        contacts_updated = backend_contact_results[SyncOutcome.updated]
        contacts_deleted = backend_contact_results[SyncOutcome.deleted]
        ignored = backend_contact_results[SyncOutcome.ignored]

        cache.set(last_fetch_date_key, until, None)

        logger.info(
            "Fetched contacts for org #%d. "
            "Created %s, Updated %s, Deleted %d, Ignored %d"
            % (org.pk, contacts_created, contacts_updated, contacts_deleted, ignored)
        )

        logger.info("Fetch contacts for org #%d took %ss" % (org.pk, time.time() - start_contacts))

        # Squash reporters counts
        # ReportersCounter.squash_counts()

        results[backend_obj.slug] = {
            "fields": {"created": fields_created, "updated": fields_updated, "deleted": fields_deleted},
            "boundaries": {
                "created": boundaries_created,
                "updated": boundaries_updated,
                "deleted": boundaries_deleted,
            },
            "contacts": {"created": contacts_created, "updated": contacts_updated, "deleted": contacts_deleted},
        }

    return results


@org_task("contact-pull", 60 * 60 * 24)
def populate_contact_schemes(org, since, until):
    r = get_valkey_connection()
    start_time = time.time()

    schemes_populated_key = f"schemes_populated:{org.id}"

    if cache.get(schemes_populated_key):
        logger.info(f"Skipping populating schemes for org #{org.id}")
        populate_contact_activities_schemes.apply_async((org.id,), queue="slow")
        return

    logger.info(f"Starting populating schemes for org #{org.id}")

    contact_pull_key = TaskState.get_lock_key(org, "contact-pull")

    if Contact.objects.filter(org_id=org.id, scheme=None, is_active=True).exists():
        # for ourself to make sure our task below will be run
        r.delete(contact_pull_key)

    with r.lock(contact_pull_key):
        last_fetch_date_key = Contact.CONTACT_LAST_FETCHED_CACHE_KEY % (org.id, "rapidpro")
        cache.delete(last_fetch_date_key)

        backends = org.backends.filter(is_active=True)
        for backend_obj in backends:
            backend = org.get_backend(backend_slug=backend_obj.slug)

            last_fetch_date_key = Contact.CONTACT_LAST_FETCHED_CACHE_KEY % (org.pk, backend_obj.slug)

            until = datetime_to_json_date(timezone.now())
            since = cache.get(last_fetch_date_key, None)

            if not since:
                logger.info("First time run for org #%d. Will sync all contacts" % org.pk)

            start = time.time()

            backend_fields_results = backend.pull_fields(org)

            fields_created = backend_fields_results[SyncOutcome.created]
            fields_updated = backend_fields_results[SyncOutcome.updated]
            fields_deleted = backend_fields_results[SyncOutcome.deleted]
            ignored = backend_fields_results[SyncOutcome.ignored]

            logger.info(
                "Fetched contact fields for org #%d. "
                "Created %s, Updated %s, Deleted %d, Ignored %d"
                % (org.pk, fields_created, fields_updated, fields_deleted, ignored)
            )
            logger.info("Fetch fields for org #%d took %ss" % (org.pk, time.time() - start))

            start_boundaries = time.time()

            backend_boundaries_results = backend.pull_boundaries(org)

            boundaries_created = backend_boundaries_results[SyncOutcome.created]
            boundaries_updated = backend_boundaries_results[SyncOutcome.updated]
            boundaries_deleted = backend_boundaries_results[SyncOutcome.deleted]
            ignored = backend_boundaries_results[SyncOutcome.ignored]

            logger.info(
                "Fetched boundaries for org #%d. "
                "Created %s, Updated %s, Deleted %d, Ignored %d"
                % (org.pk, boundaries_created, boundaries_updated, boundaries_deleted, ignored)
            )

            logger.info("Fetch boundaries for org #%d took %ss" % (org.pk, time.time() - start_boundaries))
            start_contacts = time.time()

            backend_contact_results, resume_cursor = backend.pull_contacts(org, since, until)

            contacts_created = backend_contact_results[SyncOutcome.created]
            contacts_updated = backend_contact_results[SyncOutcome.updated]
            contacts_deleted = backend_contact_results[SyncOutcome.deleted]
            ignored = backend_contact_results[SyncOutcome.ignored]

            cache.set(last_fetch_date_key, until, None)

            logger.info(
                "Fetched contacts for org #%d. "
                "Created %s, Updated %s, Deleted %d, Ignored %d"
                % (org.pk, contacts_created, contacts_updated, contacts_deleted, ignored)
            )

            logger.info("Fetch contacts for org #%d took %ss" % (org.pk, time.time() - start_contacts))

        Contact.recalculate_reporters_stats(org)

    elapsed = time.time() - start_time
    logger.info(f"Finished populating schemes on contacts for org #{org.id} in {elapsed:.1f} seconds")

    contact_count_cache_updates_key = TaskState.get_lock_key(org, "update-org-contact-counts")
    with r.lock(contact_count_cache_updates_key):
        update_cache_org_contact_counts(org)

    elapsed = time.time() - start_time
    logger.info(f"Finished updating schemes counts on contacts for org #{org.id} in {elapsed:.1f} seconds")
    cache.set(schemes_populated_key, datetime_to_json_date(timezone.now()), None)
    populate_contact_activities_schemes.apply_async((org.id,), queue="slow")


@app.task(name="contacts.populate_contact_activities_schemes")
def populate_contact_activities_schemes(org_id):
    contact_activities_schemes_populated_key = f"contact_activities_schemes_populated:{org_id}"

    if cache.get(contact_activities_schemes_populated_key):
        logger.info(f"Skipping populating schemes for org #{org_id}")
        populate_poll_results_schemes.apply_async((org_id,), queue="slow")
        return

    contact_activities_schemes_max_id_key = f"contact_activities_schemes_max_id:{org_id}"
    max_id = cache.get(contact_activities_schemes_max_id_key, 0)

    start_time = time.time()
    logger.info(f"started populating schemes on contacts activities for org #{org_id}")
    contact_ids = (
        Contact.objects.filter(org_id=org_id, is_active=True, id__gt=max_id)
        .exclude(scheme=None)
        .exclude(scheme="")
        .order_by("id")
        .values_list("id", flat=True)
    )

    contacts_count = 0

    for batch in chunk_list(contact_ids, 1000):
        batch_ids = list(batch)
        contacts = Contact.objects.filter(id__in=batch_ids)
        for contact in contacts:
            ContactActivity.objects.filter(org_id=contact.org_id, contact=contact.uuid).update(scheme=contact.scheme)
            cache.set(contact_activities_schemes_max_id_key, contact.id, None)

        contacts_count += len(batch_ids)

        elapsed = time.time() - start_time
        logger.info(
            f"Populating schemes on contacts activities batch {contacts_count} for org #{org_id} in {elapsed:.1f} seconds"
        )

    elapsed = time.time() - start_time
    logger.info(f"Finished populating schemes on contacts activities for org #{org_id} in {elapsed:.1f} seconds")
    cache.set(contact_activities_schemes_populated_key, datetime_to_json_date(timezone.now()), None)
    populate_poll_results_schemes.apply_async((org_id,), queue="slow")


@app.task(name="contacts.populate_poll_results_schemes")
def populate_poll_results_schemes(org_id):
    from ureport.polls.models import PollResult

    poll_results_schemes_populated_key = f"poll_results_schemes_populated:{org_id}"

    if cache.get(poll_results_schemes_populated_key):
        logger.info(f"Skipping populating schemes for org #{org_id}")
        return

    poll_results_schemes_max_id_key = f"poll_results_schemes_max_id:{org_id}"
    max_id = cache.get(poll_results_schemes_max_id_key, 0)

    start_time = time.time()
    logger.info(f"started populating schemes on poll results for org #{org_id}")
    contact_ids = (
        Contact.objects.filter(org_id=org_id, is_active=True, id__gt=max_id)
        .exclude(scheme=None)
        .exclude(scheme="")
        .order_by("id")
        .values_list("id", flat=True)
    )

    contacts_count = 0

    for batch in chunk_list(contact_ids, 1000):
        batch_ids = list(batch)
        contacts = Contact.objects.filter(id__in=batch_ids)
        for contact in contacts:
            PollResult.objects.filter(contact=contact.uuid).update(scheme=contact.scheme)
            cache.set(poll_results_schemes_max_id_key, contact.id, None)

        contacts_count += len(batch_ids)

        elapsed = time.time() - start_time
        logger.info(
            f"Populating schemes on poll results batch {contacts_count} for org #{org_id} in {elapsed:.1f} seconds"
        )

    elapsed = time.time() - start_time
    logger.info(f"Finished populating schemes on poll results for org #{org_id} in {elapsed:.1f} seconds")
    cache.set(poll_results_schemes_populated_key, datetime_to_json_date(timezone.now()), None)
