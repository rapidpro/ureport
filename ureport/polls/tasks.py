# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import time
from datetime import timedelta

from django_valkey import get_valkey_connection
from temba_client.exceptions import TembaRateExceededError

from django.core.cache import cache
from django.utils import timezone

from dash.orgs.models import Org
from dash.orgs.tasks import org_task
from ureport.celery import app
from ureport.utils import (
    fetch_flows,
    fetch_old_sites_count as do_fetch_old_sites_count,
    fetch_shared_sites_count,
    populate_age_and_gender_poll_results,
    update_poll_flow_data,
)

logger = logging.getLogger(__name__)


@org_task("backfill-poll-results", 60 * 60 * 3)
def backfill_poll_results(org, since, until):
    from .models import Poll

    results_log = dict()

    for poll in (
        Poll.objects.filter(org=org, has_synced=False)
        .exclude(is_active=False)
        .exclude(flow_uuid="")
        .distinct("flow_uuid")
    ):
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = Poll.pull_results(poll.id)
        results_log["flow-%s" % poll.flow_uuid] = {
            "num_val_created": num_val_created,
            "num_val_updated": num_val_updated,
            "num_val_ignored": num_val_ignored,
            "num_path_created": num_path_created,
            "num_path_updated": num_path_updated,
            "num_path_ignored": num_path_ignored,
        }

    return results_log


@org_task("results-pull-main-poll", 60 * 60 * 2)
def pull_results_main_poll(org, since, until):
    from .models import Poll

    results_log = dict()
    main_poll = Poll.get_main_poll(org)
    if main_poll:
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = Poll.pull_results(main_poll.id)
        results_log["flow-%s" % main_poll.flow_uuid] = {
            "num_val_created": num_val_created,
            "num_val_updated": num_val_updated,
            "num_val_ignored": num_val_ignored,
            "num_path_created": num_path_created,
            "num_path_updated": num_path_updated,
            "num_path_ignored": num_path_ignored,
        }

    return results_log


@org_task("results-pull-other-polls", 60 * 60 * 24)
def pull_results_other_polls(org, since, until):
    from .models import Poll

    now = timezone.now()
    recent_window = now - timedelta(days=7)

    results_log = dict()
    other_polls_ids = Poll.get_other_polls(org).exclude(created_on__gt=recent_window)
    other_polls_ids = other_polls_ids.order_by("flow_uuid").distinct("flow_uuid").values_list("id", flat=True)
    other_polls = Poll.objects.filter(id__in=other_polls_ids).order_by("-created_on")
    for poll in other_polls:
        key = Poll.POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_KEY % (org.id, poll.flow_uuid)
        if not cache.get(key):
            try:
                (
                    num_val_created,
                    num_val_updated,
                    num_val_ignored,
                    num_path_created,
                    num_path_updated,
                    num_path_ignored,
                ) = Poll.pull_results(poll.id)

                results_log["flow-%s" % poll.flow_uuid] = {
                    "num_val_created": num_val_created,
                    "num_val_updated": num_val_updated,
                    "num_val_ignored": num_val_ignored,
                    "num_path_created": num_path_created,
                    "num_path_updated": num_path_updated,
                    "num_path_ignored": num_path_ignored,
                }

            except TembaRateExceededError:
                pass

    return results_log


@org_task("results-pull-recent-polls", 60 * 60 * 6)
def pull_results_recent_polls(org, since, until):
    from .models import Poll

    results_log = dict()
    recent_polls_ids = Poll.get_recent_polls(org).order_by("flow_uuid")
    recent_polls_ids = recent_polls_ids.distinct("flow_uuid").values_list("id", flat=True)

    recent_polls = Poll.objects.filter(id__in=recent_polls_ids).order_by("-created_on")
    for poll in recent_polls:
        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = Poll.pull_results(poll.id)
        results_log["flow-%s" % poll.flow_uuid] = {
            "num_val_created": num_val_created,
            "num_val_updated": num_val_updated,
            "num_val_ignored": num_val_ignored,
            "num_path_created": num_path_created,
            "num_path_updated": num_path_updated,
            "num_path_ignored": num_path_ignored,
        }

    return results_log


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
        if r.get(key):
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


@app.task()
def update_or_create_questions(poll_ids):
    from .models import Poll

    for poll in Poll.objects.filter(id__in=poll_ids):
        poll.update_or_create_questions()


@app.task(name="polls.pull_refresh")
def pull_refresh(poll_id):
    from .models import Poll

    Poll.pull_results(poll_id)


@app.task(name="polls.update_questions_results_cache")
def update_questions_results_cache(poll_id):
    from .models import Poll

    poll = Poll.objects.filter(id=poll_id).prefetch_related("questions").first()
    if poll:
        poll.update_questions_results_cache()


@app.task(name="polls.pull_refresh_from_archives")
def pull_refresh_from_archives(poll_id):
    from .models import Poll

    Poll.pull_results_from_archives(poll_id)


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
    key = "squash_stats_lock"

    lock_timeout = 60 * 60 * 2

    if r.get(key):
        logger.info("Skipping squashing stats as it is still running")
    else:
        with r.lock(key, timeout=lock_timeout):
            PollStats.squash()
