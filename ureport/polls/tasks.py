from dash.orgs.models import Org
from django_redis import get_redis_connection
from djcelery.app import app
from ureport.polls.models import Poll

@app.task(name='polls.update_main_poll')
def update_main_poll():
    r = get_redis_connection()

    key = 'update_main_poll'
    if not r.get(key):
        with r.lock(key, timeout=900):
            for org in Org.objects.filter(is_active=True):
                main_poll = Poll.get_main_poll(org)
                if main_poll:
                    org.fetch_org_polls_results([main_poll], r)

@app.task(name='polls.update_brick_polls')
def update_brick_polls():
    r = get_redis_connection()

    key = 'update_brick_polls'
    if not r.get(key):
        with r.lock(key, timeout=900):
            for org in Org.objects.filter(is_active=True):
                brick_polls = Poll.get_brick_polls(org)
                org.fetch_org_polls_results(brick_polls, r)


@app.task(name='polls.update_other_polls')
def update_other_polls():
    r = get_redis_connection()

    key = 'update_other_polls'
    if not r.get(key):
        with r.lock(key, timeout=900):
            for org in Org.objects.filter(is_active=True):
                other_polls = Poll.get_other_polls(org)
                org.fetch_org_polls_results(other_polls, r)

@app.task(name='polls.update_org_flows_and_reporters')
def update_org_flows_and_reporters():
    r = get_redis_connection()

    key = 'update_flows_and_reporters'
    if not r.get(key):
        with r.lock(key, timeout=900):
            for org in Org.objects.filter(is_active=True):
                org.fetch_flows()
                org.fetch_reporter_group()


@app.task(name='poll.update_org_graphs_data')
def update_org_graphs_data():
    r = get_redis_connection()

    key = 'update_graphs_data'
    if not r.get(key):
        with r.lock(key, timeout=900):
            for org in Org.objects.filter(is_active=True):
                for data_label in ['born_label', 'registration_label', 'occupation_label', 'gender_label']:
                    c_field = org.get_config(data_label)
                    if c_field:
                        org.fetch_contact_field_results(c_field, None)

                states_boundaries_id = org.get_top_level_geojson_ids()
                c_field = org.get_config('gender_label')
                if c_field:
                    if org.get_config('state_label'):
                        org.fetch_contact_field_results(c_field, dict(location='State'))
                    if org.get_config('district_label'):
                        for state_id in states_boundaries_id:
                            org.fetch_contact_field_results(c_field, dict(location='District', parent=state_id))
