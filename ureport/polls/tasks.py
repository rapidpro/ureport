# -*- coding: utf-8 -*-

import logging
import time
from datetime import timedelta

from django_valkey import get_valkey_connection

from django.utils import timezone

from dash.orgs.models import Org
from dash.orgs.tasks import org_task
from ureport.celery import app
from ureport.polls.sync import (  # noqa: F401 - imported here so the worker registers the chunked tasks
    MAIN_POLL_INTERVAL,
    OTHER_POLLS_INTERVAL,
    OTHER_POLLS_NEW_WINDOW,
    RECENT_POLLS_INTERVAL,
    dispatch_flows,
    is_flow_syncing,
    queue_archives_sync,
    queue_results_sync,
    sync_poll_archives,
    sync_poll_results,
    sync_polls_dispatch,
)
from ureport.utils import (
    fetch_flows,
    fetch_old_sites_count as do_fetch_old_sites_count,
    fetch_shared_sites_count,
    populate_age_and_gender_poll_results,
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


@org_task("clear-old-poll-results", 60 * 60 * 5)
def clear_old_poll_results(org, since, until):
    from .models import Poll

    now = timezone.now()
    r = get_valkey_connection()
    syncing_window = now - timedelta(days=365)
    new_window = now - timedelta(days=14)

    dupes_flow_uuid = set()

    old_polls = (
        Poll.objects.filter(org=org)
        .exclude(poll_date__gte=syncing_window)
        .exclude(created_on__gte=new_window)
        .exclude(stopped_syncing=True)
        .order_by("pk")
    )
    for poll in old_polls:
        key = Poll.POLL_PULL_RESULTS_TASK_LOCK % (org.pk, poll.flow_uuid)
        # the valkey lock is only taken by the unchunked pulls, kept here for the release
        # they still exist in - a chunked sync announces itself with its job lease instead
        if r.get(key) or is_flow_syncing(org.pk, poll.flow_uuid):
            logger.info(
                "Skipping clearing old results for poll #%d on org #%d as it is still syncing" % (poll.pk, org.pk)
            )
        elif poll.flow_uuid in dupes_flow_uuid:
            logger.info(
                "Skipping clearing old results for poll #%d on org #%d as it appear to be duplicated"
                % (poll.pk, org.pk)
            )
        else:
            dupes_flow_uuid.add(poll.flow_uuid)
            with r.lock(key, timeout=Poll.POLL_SYNC_LOCK_TIMEOUT):
                # refresh the object from the DB
                poll.refresh_from_db()
                try:
                    # one last stats rebuild for the poll
                    poll.rebuild_poll_results_counts()

                    if not poll.stopped_syncing:
                        poll.delete_poll_results()
                        Poll.objects.filter(org=org, flow_uuid=poll.flow_uuid).update(stopped_syncing=True)
                        logger.info(
                            "Cleared poll results and stopped syncing for poll #%s on org #%s" % (poll.id, poll.org_id)
                        )
                except Exception:
                    logger.error(
                        "Error clearing old poll results for poll #%s on org #%s" % (poll.id, poll.org_id),
                        exc_info=True,
                        extra={"stack": True},
                    )


# acks late so an admin-triggered action interrupted by a worker stop is redelivered
# rather than silently lost - there is no periodic trigger to retry it
@app.task(acks_late=True, reject_on_worker_lost=True)
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


# acks late so an admin-triggered action interrupted by a worker stop is redelivered
# rather than silently lost - there is no periodic trigger to retry it
@app.task(name="polls.update_questions_results_cache", acks_late=True, reject_on_worker_lost=True)
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
    from .models import Poll

    r = get_valkey_connection()

    key = "polls_rebuild_counts_task_running"
    lock_timeout = 60 * 60 * 24 * 4  # 4 days

    if r.get(key):
        logger.info("Task: polls.rebuild_counts skipped")
    else:
        with r.lock(key, timeout=lock_timeout):
            start_time = time.time()

            logger.info("Task: polls.rebuild_counts started")
            polls = Poll.objects.filter(is_active=True)

            for poll in polls:
                poll.rebuild_poll_results_counts()

            elapsed = time.time() - start_time

            logger.info(f"Task: polls.rebuild_counts finished in {elapsed:.1f} seconds")


@app.task(name="update_results_age_gender")
def update_results_age_gender(org_id=None):
    from .models import Poll

    org = None
    if org_id:
        org = Org.objects.filter(pk=org_id).first()

    populate_age_and_gender_poll_results(org)

    polls = Poll.objects.all()
    if org:
        polls = polls.filter(org=org)
    for poll in polls:
        poll.rebuild_poll_results_counts()


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
