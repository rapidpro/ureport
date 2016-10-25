import logging
import time
from dash.orgs.models import Org
from django.core.cache import cache
from django_redis import get_redis_connection
from djcelery.app import app

from dash.orgs.tasks import org_task
from ureport.utils import fetch_flows, fetch_old_sites_count, update_poll_flow_data
from ureport.utils import populate_age_and_gender_poll_results


logger = logging.getLogger(__name__)


@org_task('backfill-poll-results')
def backfill_poll_results(org, since, until):
    from .models import Poll, PollResult

    results_log = dict()

    for poll in Poll.objects.filter(org=org, has_synced=False).distinct('flow_uuid'):
        (num_val_created, num_val_updated, num_val_ignored,
         num_path_created, num_path_updated, num_path_ignored) = Poll.pull_results(poll.id)
        results_log['flow-%s' % poll.flow_uuid] = {"num_val_created": num_val_created,
                                                   "num_val_updated": num_val_updated,
                                                   "num_val_ignored": num_val_ignored,
                                                   "num_path_created": num_path_created,
                                                   "num_path_updated": num_path_updated,
                                                   "num_path_ignored": num_path_ignored}

    return results_log


@org_task('results-pull-main-poll')
def pull_results_main_poll(org, since, until):
    from .models import Poll

    results_log = dict()
    main_poll = Poll.get_main_poll(org)
    if main_poll:
        (num_val_created, num_val_updated, num_val_ignored,
         num_path_created, num_path_updated, num_path_ignored) = Poll.pull_results(main_poll.id)
        results_log['flow-%s' % main_poll.flow_uuid] = {"num_val_created": num_val_created,
                                                        "num_val_updated": num_val_updated,
                                                        "num_val_ignored": num_val_ignored,
                                                        "num_path_created": num_path_created,
                                                        "num_path_updated": num_path_updated,
                                                        "num_path_ignored": num_path_ignored}

    return results_log


@org_task('results-pull-brick-polls')
def pull_results_brick_polls(org, since, until):
    from .models import Poll

    results_log = dict()

    brick_polls = Poll.get_brick_polls(org).distinct('flow_uuid')[:5]
    for poll in brick_polls:
        (num_val_created, num_val_updated, num_val_ignored,
         num_path_created, num_path_updated, num_path_ignored) = Poll.pull_results(poll.id)
        results_log['flow-%s' % poll.flow_uuid] = {"num_val_created": num_val_created,
                                                   "num_val_updated": num_val_updated,
                                                   "num_val_ignored": num_val_ignored,
                                                   "num_path_created": num_path_created,
                                                   "num_path_updated": num_path_updated,
                                                   "num_path_ignored": num_path_ignored}

    return results_log


@org_task('results-pull-other-polls')
def pull_results_other_polls(org, since, until):
    from .models import Poll

    results_log = dict()
    other_polls = Poll.get_other_polls(org).distinct('flow_uuid')
    for poll in other_polls:
        (num_val_created, num_val_updated, num_val_ignored,
         num_path_created, num_path_updated, num_path_ignored) = Poll.pull_results(poll.id)
        results_log['flow-%s' % poll.flow_uuid] = {"num_val_created": num_val_created,
                                                   "num_val_updated": num_val_updated,
                                                   "num_val_ignored": num_val_ignored,
                                                   "num_path_created": num_path_created,
                                                   "num_path_updated": num_path_updated,
                                                   "num_path_ignored": num_path_ignored}

    return results_log


@org_task('results-pull-recent-other-polls')
def pull_results_recent_other_polls(org, since, until):
    from .models import Poll

    results_log = dict()
    recent_other_polls = Poll.get_recent_other_polls(org).distinct('flow_uuid')
    for poll in recent_other_polls:
        (num_val_created, num_val_updated, num_val_ignored,
         num_path_created, num_path_updated, num_path_ignored) = Poll.pull_results(poll.id)
        results_log['flow-%s' % poll.flow_uuid] = {"num_val_created": num_val_created,
                                                   "num_val_updated": num_val_updated,
                                                   "num_val_ignored": num_val_ignored,
                                                   "num_path_created": num_path_created,
                                                   "num_path_updated": num_path_updated,
                                                   "num_path_ignored": num_path_ignored}

    return results_log


@app.task()
def update_or_create_questions(poll_ids):
    from .models import Poll
    for poll in Poll.objects.filter(id__in=poll_ids):
        poll.update_or_create_questions()


@app.task(name='polls.pull_refresh')
def pull_refresh(poll_id):
    from .models import Poll
    Poll.pull_results(poll_id)


@app.task(name='polls.rebuild_counts')
def rebuild_counts():
    from .models import Poll
    for poll in Poll.objects.all():
        poll.rebuild_poll_results_counts()


@app.task(name='update_results_age_gender')
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


@app.task(name='polls.refresh_org_flows')
def refresh_org_flows(org_id=None):
    start = time.time()
    r = get_redis_connection()

    key = 'refresh_flows'
    lock_timeout = 900

    if org_id:
        key = 'refresh_flows:%d' % org_id
        lock_timeout = 30

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            active_orgs = Org.objects.filter(is_active=True)
            if org_id:
                active_orgs = Org.objects.filter(pk=org_id)

            for org in active_orgs:
                fetch_flows(org)

        print "Task: refresh_flows took %ss" % (time.time() - start)


@app.task(name='polls.fetch_old_sites_count')
def fetch_old_sites_count():
    start = time.time()
    r = get_redis_connection()

    key = 'fetch_old_sites_count_lock'
    lock_timeout = 60

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            fetch_old_sites_count()
            print "Task: fetch_old_sites_count took %ss" % (time.time() - start)


@app.task(track_started=True, name='polls.recheck_poll_flow_data')
def recheck_poll_flow_data(org_id=None):

    active_orgs = Org.objects.filter(is_active=True)
    if org_id:
        active_orgs = Org.objects.filter(pk=org_id)

    for org in active_orgs:
        update_poll_flow_data(org)

    print "Task: recheck_poll_flow_data done"