import logging
import time
from dash.orgs.models import Org
from django_redis import get_redis_connection
from djcelery.app import app
from ureport.utils import fetch_flows, fetch_old_sites_count
from ureport.utils import fetch_main_poll_results, fetch_brick_polls_results, fetch_other_polls_results


logger = logging.getLogger(__name__)


@app.task(name='polls.refresh_main_poll')
def refresh_main_poll(org_id=None):

    start = time.time()
    r = get_redis_connection()

    key = 'refresh_main_poll'
    lock_timeout = 900

    if org_id:
        key = 'refresh_main_poll:%d' % org_id
        lock_timeout = 120

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            active_orgs = Org.objects.filter(is_active=True)
            if org_id:
                active_orgs = Org.objects.filter(pk=org_id)

            for org in active_orgs:
                fetch_main_poll_results(org)

            print "Task: Update_main_poll took %ss" % (time.time() - start)


@app.task(name='polls.refresh_brick_polls')
def refresh_brick_polls(org_id=None):
    start = time.time()
    r = get_redis_connection()

    key = 'refresh_brick_polls'
    lock_timeout = 3600

    if org_id:
        key = 'refresh_brick_polls:%d' % org_id
        lock_timeout = 600

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            active_orgs = Org.objects.filter(is_active=True)
            if org_id:
                active_orgs = Org.objects.filter(pk=org_id)

            for org in active_orgs:
                fetch_brick_polls_results(org)


            print "Task: Update_brick_polls took %ss" % (time.time() - start)


@app.task(name='polls.refresh_other_polls')
def refresh_other_polls(org_id=None):
    start = time.time()
    r = get_redis_connection()

    key = 'refresh_other_polls'
    lock_timeout = 10800

    if org_id:
        key = 'refresh_other_polls:%d' % org_id

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            active_orgs = Org.objects.filter(is_active=True)
            if org_id:
                active_orgs = Org.objects.filter(pk=org_id)

            for org in active_orgs:
                fetch_other_polls_results(org)

            print "Task: Update_other_polls took %ss" % (time.time() - start)


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


@app.task(track_started=True, name='fetch_poll')
def fetch_poll(poll_id):
    try:
        # get our poll
        from .models import Poll
        poll = Poll.objects.get(pk=poll_id)
        poll.fetch_poll_results()
    except Exception as e:
        logger.exception("Error fetching poll results: %s" % str(e))
