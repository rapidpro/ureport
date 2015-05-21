
from dash.orgs.models import Org
from django_redis import get_redis_connection
from ureport.polls.models import Poll


def update_main_poll_data_cache():
    r = get_redis_connection()
    for org in Org.objects.filter(is_active=True):
        main_poll = Poll.get_main_poll(org)
        org.fetch_org_polls_results([main_poll], r)

def update_brick_polls_data_cache():
    r = get_redis_connection()
    for org in Org.objects.filter(is_active=True):
        brick_polls = Poll.get_brick_polls(org)

        org.fetch_org_polls_results(brick_polls, r)

def update_poll_flows():
    r = get_redis_connection()
    for org in Org.objects.filter(is_active=True):
        org.fetch_flows()



