# -*- coding: utf-8 -*-

import logging
import time

from django_valkey import get_valkey_connection

from django.utils import timezone

from dash.orgs.models import Org
from ureport.celery import app
from ureport.polls.sync import (  # noqa: F401 - imported here so the worker registers the chunked tasks
    MAIN_POLL_INTERVAL,
    OTHER_POLLS_INTERVAL,
    OTHER_POLLS_NEW_WINDOW,
    RECENT_POLLS_INTERVAL,
    backfill_age_gender,
    dispatch_flows,
    prune_poll_results,
    prune_results_dispatch,
    queue_age_gender_backfill,
    queue_archives_sync,
    queue_counts_rebuild,
    queue_results_prune,
    queue_results_sync,
    rebuild_counts_dispatch,
    rebuild_poll_counts,
    sync_poll_archives,
    sync_poll_results,
    sync_polls_dispatch,
)
from ureport.utils import (
    fetch_flows,
    fetch_old_sites_count as do_fetch_old_sites_count,
    fetch_shared_sites_count,
    update_poll_flow_data,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Shims for the tasks the poll syncs used to run under. They keep their registered
# names for one release so queued messages and existing triggers resolve, but only
# hand the work to the sync jobs - they hold no lock and record no task state.
# ------------------------------------------------------------------------------


def _queue_polls(org, polls, interval=None):
    queued = dispatch_flows(org, [poll.flow_uuid for poll in polls], interval=interval)

    logger.info("Queued poll results syncs for org #%d: %s" % (org.pk, ", ".join(queued) or "none"))


@app.task(name="ureport.polls.tasks.backfill_poll_results")
def backfill_poll_results(org_id):
    from .models import Poll

    org = Org.objects.get(pk=org_id)
    polls = Poll.objects.filter(org=org, has_synced=False).exclude(is_active=False).exclude(flow_uuid="")

    _queue_polls(org, polls)


@app.task(name="ureport.polls.tasks.pull_results_main_poll")
def pull_results_main_poll(org_id):
    from .models import Poll

    org = Org.objects.get(pk=org_id)
    main_poll = Poll.get_main_poll(org)

    _queue_polls(org, [main_poll] if main_poll else [], interval=MAIN_POLL_INTERVAL)


@app.task(name="ureport.polls.tasks.pull_results_other_polls")
def pull_results_other_polls(org_id):
    from .models import Poll

    org = Org.objects.get(pk=org_id)
    other_polls = Poll.get_other_polls(org).exclude(created_on__gt=timezone.now() - OTHER_POLLS_NEW_WINDOW)

    _queue_polls(org, other_polls, interval=OTHER_POLLS_INTERVAL)


@app.task(name="ureport.polls.tasks.pull_results_recent_polls")
def pull_results_recent_polls(org_id):
    from .models import Poll

    org = Org.objects.get(pk=org_id)

    _queue_polls(org, Poll.get_recent_polls(org), interval=RECENT_POLLS_INTERVAL)


@app.task(name="ureport.polls.tasks.clear_old_poll_results")
def clear_old_poll_results(org_id):
    org = Org.objects.get(pk=org_id)

    queue_results_prune(org)


@app.task()
def update_or_create_questions(poll_ids):
    from .models import Poll

    for poll in Poll.objects.filter(id__in=poll_ids):
        poll.update_or_create_questions()


@app.task(name="polls.pull_refresh")
def pull_refresh(poll_id):
    from .models import Poll

    poll = Poll.objects.filter(id=poll_id).first()
    if poll:
        queue_results_sync(poll.org, poll.flow_uuid)


@app.task(name="polls.update_questions_results_cache")
def update_questions_results_cache(poll_id):
    from .models import Poll

    poll = Poll.objects.filter(id=poll_id).prefetch_related("questions").first()
    if poll:
        poll.update_questions_results_cache()


@app.task(name="polls.pull_refresh_from_archives")
def pull_refresh_from_archives(poll_id):
    from .models import Poll

    poll = Poll.objects.filter(id=poll_id).first()
    if poll:
        # the only caller left is the unchunked pull's re-pull after a results delete, so
        # the traversal has to start over rather than resume below its last position
        queue_archives_sync(poll.org, poll.flow_uuid, reset_cursor=True)


@app.task(name="polls.rebuild_counts")
def rebuild_counts():
    queue_counts_rebuild()


@app.task(name="update_results_age_gender")
def update_results_age_gender(org_id=None):
    orgs = Org.objects.filter(pk=org_id) if org_id else Org.objects.filter(is_active=True)

    for org in orgs:
        queue_age_gender_backfill(org)


@app.task(name="polls.refresh_org_flows")
def refresh_org_flows(org_id=None):
    start = time.time()
    r = get_valkey_connection()

    key = "refresh_flows"
    lock_timeout = 900

    if org_id:
        key = "refresh_flows:%d" % org_id
        lock_timeout = 30

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            active_orgs = Org.objects.filter(is_active=True)
            if org_id:
                active_orgs = Org.objects.filter(pk=org_id)

            for org in active_orgs:
                fetch_flows(org)

        logger.info("Task: refresh_flows took %ss" % (time.time() - start))


@app.task(name="polls.fetch_old_sites_count")
def fetch_old_sites_count():
    start = time.time()
    r = get_valkey_connection()

    key = "fetch_old_sites_count_lock"
    lock_timeout = 60 * 5

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            do_fetch_old_sites_count()
            fetch_shared_sites_count()
            logger.info("Task: fetch_old_sites_count took %ss" % (time.time() - start))


@app.task(track_started=True, name="polls.recheck_poll_flow_data")
def recheck_poll_flow_data(org_id=None):
    active_orgs = Org.objects.filter(is_active=True)
    if org_id:
        active_orgs = Org.objects.filter(pk=org_id)

    for org in active_orgs:
        update_poll_flow_data(org)

    logger.info("Task: recheck_poll_flow_data done")


@app.task(name="polls.polls_stats_squash")
def polls_stats_squash():
    from ureport.stats.models import PollStats

    r = get_valkey_connection()
    key = "squash_polls_stats_lock"

    lock_timeout = 60 * 60 * 2

    if r.get(key):
        logger.info("Skipping polls app squashing stats as it is still running")
    else:
        with r.lock(key, timeout=lock_timeout):
            PollStats.squash()
