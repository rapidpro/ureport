# -*- coding: utf-8 -*-

from celery.utils.log import get_task_logger
from django_valkey import get_valkey_connection

from django.core.cache import cache

from dash.orgs.models import Org, TaskState
from dash.orgs.tasks import org_task
from ureport.celery import app

# the chunked contact tasks live in sync.py and maintenance.py - imported here so celery,
# which only autodiscovers tasks modules, registers them
from ureport.contacts.maintenance import (  # noqa: F401
    backfill_activities_schemes,
    backfill_results_schemes,
    enqueue_reporters_rebuilds,
    enqueue_schemes_activities,
    enqueue_schemes_results,
    rebuild_reporters_counts,
    start_schemes_backfill,
)
from ureport.contacts.models import Contact, ReportersCounter
from ureport.contacts.sync import enqueue_org_syncs, sync_contacts, sync_contacts_dispatch  # noqa: F401
from ureport.utils import update_cache_org_contact_counts

logger = get_task_logger(__name__)


@app.task(name="contacts.rebuild_contacts_counts")
def rebuild_contacts_counts(org_id=None):
    """
    Deprecated - kept for one release so existing triggers keep working. The rebuild itself is
    now done per org by contacts.rebuild_reporters_counts, so this only ensures those jobs
    exist and are enqueued - for one active org if given one, otherwise for all of them.
    """
    return enqueue_reporters_rebuilds(org_id=org_id)


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


@app.task(name="ureport.contacts.tasks.pull_contacts")
def pull_contacts(org_id):
    """
    Deprecated - kept for one release so existing triggers keep working. The pull itself is
    now done in resumable chunks by contacts.sync_contacts, so this only ensures this org's
    sync jobs exist and are enqueued. Deliberately not an org task anymore: it neither pulls
    nor holds the pull's lock, so it must not report itself as a completed pull in the org's
    task state - the chunked task's own completion writes that.
    """
    org = Org.objects.get(pk=org_id)
    return enqueue_org_syncs(org)


@app.task(name="ureport.contacts.tasks.populate_contact_schemes")
def populate_contact_schemes(org_id):
    """
    Deprecated - kept for one release so existing triggers keep working. Its contact re-pull is
    superseded by the chunked contact sync, so this only asks that sync for a full re-pull and
    arranges for the schemes backfill to follow it.
    """
    return start_schemes_backfill(Org.objects.get(pk=org_id))


@app.task(name="contacts.populate_contact_activities_schemes")
def populate_contact_activities_schemes(org_id):
    """
    Deprecated - kept for one release so existing triggers keep working. The backfill itself is
    now done in resumable chunks by contacts.backfill_activities_schemes, so this only ensures
    this org's job exists and is enqueued.
    """
    return enqueue_schemes_activities(Org.objects.get(pk=org_id))


@app.task(name="contacts.populate_poll_results_schemes")
def populate_poll_results_schemes(org_id):
    """
    Deprecated - kept for one release so existing triggers keep working. The backfill itself is
    now done in resumable chunks by contacts.backfill_results_schemes, so this only ensures
    this org's job exists and is enqueued.
    """
    return enqueue_schemes_results(Org.objects.get(pk=org_id))
