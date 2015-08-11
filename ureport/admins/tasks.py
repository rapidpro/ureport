from dash.orgs.models import Org
from django_redis import get_redis_connection
from djcelery.app import app
from ureport.polls.models import Poll
from ureport.utils import fetch_contact_field_results, fetch_org_polls_results, fetch_reporter_group, fetch_flows


@app.task(name='org_ext.refresh_main_poll')
def refresh_main_poll(org_id):
    r = get_redis_connection()

    key = 'refresh_main_poll:%d' % org_id
    if not r.get(key):
        with r.lock(key, timeout=120):
            org = Org.objects.filter(pk=org_id).first()
            if org:
                main_poll = Poll.get_main_poll(org)
                if main_poll:
                    fetch_org_polls_results(org, [main_poll], r)


@app.task(name='org_ext.refresh_brick_polls')
def refresh_brick_polls(org_id):
    r = get_redis_connection()

    key = 'refresh_brick_polls:%d' % org_id
    if not r.get(key):
        with r.lock(key, timeout=600):
            org = Org.objects.filter(pk=org_id).first()
            if org:
                brick_polls = Poll.get_brick_polls(org)[:5]
                fetch_org_polls_results(org, brick_polls, r)


@app.task(name='org_ext.refresh_other_polls')
def refresh_other_polls(org_id):
    r = get_redis_connection()

    key = 'refresh_other_polls:%d' % org_id
    if not r.get(key):
        with r.lock(key, timeout=10800):
            org = Org.objects.filter(pk=org_id).first()
            if org:
                other_polls = Poll.get_other_polls(org)
                fetch_org_polls_results(org, other_polls, r)


@app.task(name='org_ext.refresh_org_flows')
def refresh_org_flows(org_id):
    r = get_redis_connection()

    key = 'refresh_flows:%d' % org_id
    if not r.get(key):
        with r.lock(key, timeout=30):
            org = Org.objects.filter(pk=org_id).first()
            if org:
                fetch_flows(org)


@app.task(name='org_ext.refresh_reporters')
def refresh_org_reporters(org_id):
    r = get_redis_connection()

    key = 'refresh_reporters:%d' % org_id
    if not r.get(key):
        with r.lock(key, timeout=30):
            org = Org.objects.filter(pk=org_id).first()
            if org:
                fetch_reporter_group(org)


@app.task(name='org_ext.refresh_org_graphs_data')
def refresh_org_graphs_data(org_id):
    r = get_redis_connection()

    key = 'refresh_graphs_data:%d' % org_id
    if not r.get(key):
        with r.lock(key, timeout=900):
            org = Org.objects.filter(pk=org_id).first()
            if org:
                for data_label in ['born_label', 'registration_label', 'occupation_label', 'gender_label']:
                    c_field = org.get_config(data_label)
                    if c_field:
                        fetch_contact_field_results(org, c_field, None)
                        if data_label == 'gender_label':
                            fetch_contact_field_results(org, c_field, dict(location='State'))