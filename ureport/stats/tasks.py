import logging

from django_valkey import get_valkey_connection

from dash.orgs.models import Org
from ureport.celery import app

# the chunked stats tasks live in sync.py - imported here so celery, which only
# autodiscovers tasks modules, registers them
from ureport.stats.sync import ENGAGEMENT_JOB_TYPE, enqueue_org_job, refresh_engagement, stats_dispatch  # noqa: F401

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
