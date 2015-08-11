import time
from dash.orgs.models import Org
from django_redis import get_redis_connection
from djcelery.app import app
from ureport.polls.models import Poll
from ureport.utils import fetch_contact_field_results, fetch_org_polls_results, fetch_reporter_group, fetch_flows
from ureport.utils import fetch_old_sites_count


@app.task(name='admins.refresh_main_poll')
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
                main_poll = Poll.get_main_poll(org)
                if main_poll:
                    fetch_org_polls_results(org, [main_poll], r)

            print "Task: Update_main_poll took %ss" % (time.time() - start)


@app.task(name='admins.refresh_brick_polls')
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
                brick_polls = Poll.get_brick_polls(org)[:5]
                fetch_org_polls_results(org, brick_polls, r)

            print "Task: Update_brick_polls took %ss" % (time.time() - start)


@app.task(name='admins.refresh_other_polls')
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
                other_polls = Poll.get_other_polls(org)
                fetch_org_polls_results(org, other_polls, r)

            print "Task: Update_other_polls took %ss" % (time.time() - start)


@app.task(name='admins.refresh_org_flows')
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


@app.task(name='admins.refresh_org_reporters')
def refresh_org_reporters(org_id=None):
    start = time.time()
    r = get_redis_connection()

    key = 'refresh_reporters'
    lock_timeout = 900

    if org_id:
        key = 'refresh_reporters:%d' % org_id
        lock_timeout = 30

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            active_orgs = Org.objects.filter(is_active=True)
            if org_id:
                active_orgs = Org.objects.filter(pk=org_id)

            for org in active_orgs:
                fetch_reporter_group(org)

            fetch_old_sites_count()
            print "Task: refresh_org_reporters took %ss" % (time.time() - start)


@app.task(name='admins.refresh_org_graphs_data')
def refresh_org_graphs_data(org_id=None):
    start = time.time()
    r = get_redis_connection()

    key = 'refresh_graphs_data'
    lock_timeout = 900

    if org_id:
        key = 'refresh_graphs_data:%d' % org_id

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            active_orgs = Org.objects.filter(is_active=True)
            if org_id:
                active_orgs = Org.objects.filter(pk=org_id)

            for org in active_orgs:
                for data_label in ['born_label', 'registration_label', 'occupation_label', 'gender_label']:
                    c_field = org.get_config(data_label)
                    if c_field:
                        fetch_contact_field_results(org, c_field, None)
                        if data_label == 'gender_label':
                            fetch_contact_field_results(org, c_field, dict(location='State'))

            print "Task: Update_org_graph_data took %ss" % (time.time() - start)
