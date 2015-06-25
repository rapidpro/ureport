import logging
import time
from dash.orgs.models import Org
from django_redis import get_redis_connection
from djcelery.app import app
from ureport.polls.models import Poll
from ureport.utils import fetch_contact_field_results, fetch_org_polls_results, fetch_reporter_group, fetch_flows, \
    fetch_old_sites_count

logger = logging.getLogger(__name__)

@app.task(name='polls.update_main_poll')
def update_main_poll():

    start = time.time()
    r = get_redis_connection()

    key = 'update_main_poll'
    if not r.get(key):
        with r.lock(key, timeout=900):
            active_orgs = Org.objects.filter(is_active=True)
            for org in active_orgs:
                print "=" * 40
                main_poll = Poll.get_main_poll(org)
                if main_poll:
                    fetch_org_polls_results(org, [main_poll], r)

    print "Task: Update_main_poll took %ss" % (time.time() - start)

@app.task(name='polls.update_brick_polls')
def update_brick_polls():
    start = time.time()
    r = get_redis_connection()

    key = 'update_brick_polls'
    if not r.get(key):
        with r.lock(key, timeout=3600):
            active_orgs = Org.objects.filter(is_active=True)
            for org in active_orgs:
                print "=" * 40
                brick_polls = Poll.get_brick_polls(org)[:5]
                fetch_org_polls_results(org, brick_polls, r)

    print "Task: Update_brick_polls took %ss" % (time.time() - start)

@app.task(name='polls.update_other_polls')
def update_other_polls():
    start = time.time()
    r = get_redis_connection()

    key = 'update_other_polls'
    if not r.get(key):
        with r.lock(key, timeout=10800):
            active_orgs = Org.objects.filter(is_active=True)
            for org in active_orgs:
                print "=" * 40
                other_polls = Poll.get_other_polls(org)
                fetch_org_polls_results(org, other_polls, r)

    print "Task: Update_other_polls took %ss" % (time.time() - start)

@app.task(name='polls.update_org_flows_and_reporters')
def update_org_flows_and_reporters():
    start = time.time()
    r = get_redis_connection()

    key = 'update_flows_and_reporters'
    if not r.get(key):
        with r.lock(key, timeout=900):
            active_orgs = Org.objects.filter(is_active=True)
            for org in active_orgs:
                print "=" * 40
                fetch_flows(org)
                fetch_reporter_group(org)
            fetch_old_sites_count()
    print "Task: Update_org_flows_and_reporters took %ss" % (time.time() - start)

@app.task(name='polls.update_org_graphs_data')
def update_org_graphs_data():
    start = time.time()
    r = get_redis_connection()

    key = 'update_graphs_data'
    if not r.get(key):
        with r.lock(key, timeout=900):
            active_orgs = Org.objects.filter(is_active=True)
            for org in active_orgs:
                print "=" * 40
                for data_label in ['born_label', 'registration_label', 'occupation_label', 'gender_label']:
                    c_field = org.get_config(data_label)
                    if c_field:
                        fetch_contact_field_results(org, c_field, None)
                        if data_label == 'gender_label':
                            fetch_contact_field_results(org, c_field, dict(location='State'))

    print "Task: Update_org_graph_data took %ss" % (time.time() - start)

@app.task(track_started=True, name='fetch_poll')
def fetch_poll(poll_id):
    try:
        # get our poll
        from .models import Poll
        poll = Poll.objects.get(pk=poll_id)
        poll.fetch_poll_results()
    except Exception as e:
        logger.exception("Error fetching poll results: %s" % str(e))
