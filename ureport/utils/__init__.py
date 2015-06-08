import json
import math
from datetime import timedelta, datetime
from dash.orgs.models import Org
from dash.utils import temba_client_flow_results_serializer
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.text import slugify
from django_redis import get_redis_connection
import pycountry
import pytz
from ureport.assets.models import Image, FLAG


def get_linked_orgs():
    all_orgs = Org.objects.filter(is_active=True).order_by('name')

    linked_sites = list(getattr(settings, 'PREVIOUS_ORG_SITES', []))

    # populate a ureport site for each org so we can link off to them
    for org in all_orgs:
        host = settings.SITE_HOST_PATTERN % org.subdomain
        org.host = host
        if org.get_config('is_on_landing_page'):
            flag = Image.objects.filter(org=org, is_active=True, image_type=FLAG).first()
            if flag:
                linked_sites.append(dict(name=org.name, host=host, flag=flag.image.url, is_static=False))

    linked_sites_sorted = sorted(linked_sites, key=lambda k: k['name'].lower())

    return linked_sites_sorted


def substitute_segment(org, segment):
    if not segment:
        return segment

    location = segment.get('location', None)
    if location == 'State':
        segment['location'] = org.get_config('state_label')
    elif location == 'District':
        segment['location'] = org.get_config('district_label')

    if org.get_config('is_global'):
        if "location" in segment:
            del segment["location"]
            if 'parent' in segment:
                del segment["parent"]
            segment["contact_field"] = org.get_config('state_label')
            segment["values"] = [elt.alpha2 for elt in pycountry.countries.objects]

    return json.dumps(segment)


def clean_global_results_data(org, results, segment):
    segment_dict = None
    if segment:
        segment_dict = json.loads(segment)

    # for the global page clean the data translating country code to country name
    if org.get_config('is_global') and results and segment_dict and 'values' in segment_dict:
        for elt in results:
            country_code = elt['label']
            elt['boundary'] = country_code
            country_name = ""
            try:
                country = pycountry.countries.get(alpha2=country_code)
                if country:
                    country_name = country.name
            except KeyError:
                country_name = country_code
            elt['label'] = country_name

    return results


def fetch_contact_field_results(org, contact_field, segment):
    from ureport.polls.models import CACHE_ORG_FIELD_DATA_KEY

    segment = substitute_segment(org, segment)

    temba_client = org.get_temba_client()
    client_results = temba_client.get_results(contact_field=contact_field, segment=segment)

    results_data = temba_client_flow_results_serializer(client_results)
    print results_data
    cleaned_results_data = results_data #org.organize_categories_data(contact_field, results_data)

    key = CACHE_ORG_FIELD_DATA_KEY % (org.pk, slugify(unicode(contact_field)), slugify(unicode(segment)))
    cache.set(key, cleaned_results_data)


def get_contact_field_results(org, contact_field, segment):
    from ureport.polls.models import CACHE_ORG_FIELD_DATA_KEY

    segment = substitute_segment(org, segment)

    key = CACHE_ORG_FIELD_DATA_KEY % (org.pk, slugify(unicode(contact_field)), slugify(unicode(segment)))
    return cache.get(key, None)


def get_most_active_regions(org):
    cache_key = 'most_active_regions:%d' % org.id
    active_regions = cache.get(cache_key, None)

    if active_regions is None:
        regions = org.get_contact_field_results(org.get_config('gender_label'), dict(location="State"))
        active_regions = dict()

        if not regions:
            return []

        for region in regions:
            active_regions[region['label']] = region['set'] + region['unset']

        tuples = [(k, v) for k, v in active_regions.iteritems()]
        tuples.sort(key=lambda t: t[1], reverse=True)

        active_regions = [k for k, v in tuples]
        cache.set(cache_key, active_regions, 3600 * 24)

    if org.get_config('is_global'):
        active_regions = [pycountry.countries.get(alpha2=elt).name for elt in active_regions]

    return active_regions


def organize_categories_data(org, contact_field, api_data):

    cleaned_categories = []
    interval_dict = dict()
    now = timezone.now()
    # if we have the age_label; Ignore invalid years and make intervals
    if api_data and contact_field.lower() == org.get_config('born_label').lower():
        current_year = now.year

        for elt in api_data[0]['categories']:
            year_label = elt['label']
            try:
                if len(year_label) == 4 and int(float(year_label)) > 1900:
                    decade = int(math.floor((current_year - int(elt['label'])) / 10)) * 10
                    key = "%s-%s" % (decade, decade+10)
                    if interval_dict.get(key, None):
                        interval_dict[key] += elt['count']
                    else:
                        interval_dict[key] = elt['count']
            except ValueError:
                pass

        for obj_key in interval_dict.keys():
            cleaned_categories.append(dict(label=obj_key, count=interval_dict[obj_key] ))

        api_data[0]['categories'] = sorted(cleaned_categories, key=lambda k: int(k['label'].split('-')[0]))

    elif api_data and contact_field.lower() == org.get_config('registration_label').lower():
        six_months_ago = now - timedelta(days=180)
        six_months_ago = six_months_ago - timedelta(six_months_ago.weekday())
        tz = pytz.timezone('UTC')

        for elt in api_data[0]['categories']:
            time_str =  elt['label']
            parsed_time = tz.localize(datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%SZ'))

            # this is in the range we care about
            if parsed_time > six_months_ago:
                # get the week of the year
                dict_key = parsed_time.strftime("%W")

                if interval_dict.get(dict_key, None):
                    interval_dict[dict_key] += elt['count']
                else:
                    interval_dict[dict_key] = elt['count']

        # build our final dict using week numbers
        categories = []
        start = six_months_ago
        while start < timezone.now():
            week_dict = start.strftime("%W")
            count = interval_dict.get(week_dict, 0)
            categories.append(dict(label=start.strftime("%m/%d/%y"), count=count))

            start = start + timedelta(days=7)

        api_data[0]['categories'] = categories

    elif api_data and contact_field.lower() == org.get_config('occupation_label').lower():

        for elt in api_data[0]['categories']:
            if len(cleaned_categories) < 9 and elt['label'] != "All Responses":
                cleaned_categories.append(elt)

        api_data[0]['categories'] = cleaned_categories

    return api_data

LOCK_POLL_RESULTS_KEY = 'lock:poll:%d:results'
LOCK_POLL_RESULTS_TIMEOUT = 60 * 15


def fetch_org_polls_results(org, polls, r=None):
    if not r:
        r = get_redis_connection()

    states_boundaries_id = org.get_top_level_geojson_ids()

    for poll in polls:
        key = LOCK_POLL_RESULTS_KEY % poll.pk
        if not r.get(key):
            with r.lock(key, timeout=LOCK_POLL_RESULTS_TIMEOUT):
                poll.fetch_poll_results(states_boundaries_id)


def fetch_flows(org):
    from ureport.polls.models import CACHE_ORG_FLOWS_KEY

    temba_client = org.get_temba_client()
    flows = temba_client.get_flows()

    all_flows = dict()
    for flow in flows:
        if flow.rulesets:
            flow_json = dict()
            flow_json['uuid'] = flow.uuid
            flow_json['name'] = flow.name
            flow_json['participants'] = flow.participants
            flow_json['runs'] = flow.runs
            flow_json['completed_runs'] = flow.completed_runs
            flow_json['rulesets'] = [
                dict(uuid=elt.uuid, label=elt.label, response_type=elt.response_type) for elt in flow.rulesets]

            all_flows[flow.uuid] = flow_json

    all_flows_key = CACHE_ORG_FLOWS_KEY % org.pk
    cache.set(all_flows_key, all_flows, 900)


def get_flows(org):
    from ureport.polls.models import CACHE_ORG_FLOWS_KEY
    return cache.get(CACHE_ORG_FLOWS_KEY % org.pk, dict())


def fetch_reporter_group(org):
    from ureport.polls.models import CACHE_ORG_REPORTER_GROUP_KEY

    reporter_group = org.get_config('reporter_group')
    if reporter_group:
        temba_client = org.get_temba_client()
        groups = temba_client.get_groups(name=reporter_group)

        key = CACHE_ORG_REPORTER_GROUP_KEY % (org.pk, slugify(unicode(reporter_group)))
        group_dict = dict()
        if groups:
            group = groups[0]
            group_dict = dict(size=group.size, name=group.name, uuid=group.uuid)
        cache.set(key, group_dict)


def get_reporter_group(org):
    from ureport.polls.models import CACHE_ORG_REPORTER_GROUP_KEY

    reporter_group = org.get_config('reporter_group')

    if reporter_group:
        key = CACHE_ORG_REPORTER_GROUP_KEY % (org.pk, slugify(unicode(reporter_group)))
        group_dict = cache.get(key, None)
        if group_dict:
            return group_dict

    return dict()


Org.fetch_contact_field_results = fetch_contact_field_results
Org.get_contact_field_results = get_contact_field_results
Org.get_most_active_regions = get_most_active_regions
Org.organize_categories_data = organize_categories_data
Org.fetch_org_polls_results = fetch_org_polls_results
Org.fetch_flows = fetch_flows
Org.get_flows = get_flows
Org.fetch_reporter_group = fetch_reporter_group
Org.get_reporter_group = get_reporter_group
Org.substitute_segment = substitute_segment
