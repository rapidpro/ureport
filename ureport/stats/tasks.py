import logging

from django_valkey import get_valkey_connection

from dash.orgs.models import Org
from ureport.celery import app

# the chunked stats tasks live in sync.py - imported here so celery, which only
# autodiscovers tasks modules, registers them
from ureport.stats.sync import (  # noqa: F401
    ENGAGEMENT_JOB_TYPE,
    PRUNE_JOB_TYPE,
    REBUILD_JOB_TYPE,
    enqueue_org_job,
    prune_contact_activities,
    rebuild_contact_activity_counts,
    refresh_engagement,
    stats_dispatch,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Shims for the tasks the stats refreshes used to run under. They keep their
# registered names for one release so queued messages and existing triggers
# resolve, but only hand the work to the sync jobs - they hold no lock and record
# no task state.
# ------------------------------------------------------------------------------


@app.task(name="ureport.stats.tasks.refresh_engagement_data")
def refresh_engagement_data(org_id):
    org = Org.objects.get(pk=org_id)

    return enqueue_org_job(org, ENGAGEMENT_JOB_TYPE)


@app.task(name="ureport.stats.tasks.delete_old_contact_activities")
def delete_old_contact_activities(org_id):
    org = Org.objects.get(pk=org_id)

    return enqueue_org_job(org, PRUNE_JOB_TYPE)


@app.task(name="stats.squash_contact_activities_counts")
def squash_contact_activities_counts():
    from .models import ContactActivityCounter

    r = get_valkey_connection()
    key = "squash_contact_activity_counts_lock"

    lock_timeout = 60 * 60

    if r.get(key):
        logger.info("Skipping squashing contact activity counts as it is still running")
    else:
        with r.lock(key, timeout=lock_timeout):
            ContactActivityCounter.squash()


@app.task(name="stats.rebuild_contacts_activities_counts")
def rebuild_contacts_activities_counts(org_id=None):
    """
    Queues a counter rebuild for every active org, or just the given one. The rebuild itself
    is now done in resumable chunks by stats.rebuild_contact_activity_counts.
    """
    orgs = Org.objects.filter(is_active=True)
    if org_id:
        orgs = orgs.filter(id=org_id)

    for org in orgs:
        enqueue_org_job(org, REBUILD_JOB_TYPE)


@app.task(name="stats.stats_counts_squash")
def stats_counts_squash():
    from ureport.stats.models import STATS_COUNTS_SQUASH_LOCK, PollEngagementDailyCount, PollStatsCounter

    r = get_valkey_connection()
    key = STATS_COUNTS_SQUASH_LOCK

    lock_timeout = 60 * 60 * 2

    if r.get(key):
        logger.info("Skipping stats app squashing stats as it is still running")
    else:
        with r.lock(key, timeout=lock_timeout):
            PollStatsCounter.squash()
            PollEngagementDailyCount.squash()


@app.task(name="stats.checkpoint_active_users")
def checkpoint_active_users():
    from . import active_users

    r = get_valkey_connection()
    key = "checkpoint_active_users_lock"

    if r.get(key):
        logger.info("Skipping checkpointing active users as it is still running")
    else:
        with r.lock(key, timeout=60 * 60):
            active_users.checkpoint()


@app.task(name="stats.compare_active_users")
def compare_active_users():
    """
    Logs how far the active users counted by the sketches are from the contact activity counters, for each org
    """
    from django.conf import settings

    from . import active_users

    if not getattr(settings, "ACTIVE_USERS_HLL_COMPARE", False):
        return

    for org in Org.objects.filter(is_active=True).order_by("id"):
        try:
            summary = active_users.summarize(active_users.compare_org(org))
            logger.info("Active users comparison for org #%d: %s", org.id, summary)
        except Exception:
            logger.error("Error comparing active users for org #%d", org.id, exc_info=True)
