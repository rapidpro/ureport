# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import copy
import iso8601
import json
import math
import six
import time
from datetime import timedelta, datetime
from itertools import islice, chain

from dash.orgs.models import Org
from dash.utils import datetime_to_ms
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
import pycountry
import pytz
from ureport.assets.models import Image, FLAG
from raven.contrib.django.raven_compat.models import client

from ureport.locations.models import Boundary
from ureport.polls.models import Poll, PollResult

GLOBAL_COUNT_CACHE_KEY = 'global_count'

ORG_CONTACT_COUNT_KEY = 'org:%d:contacts-counts'
ORG_CONTACT_COUNT_TIMEOUT = 300


def datetime_to_json_date(dt):
    """
    Formats a datetime as a string for inclusion in JSON
    """
    # always output as UTC / Z and always include milliseconds
    as_utc = dt.astimezone(pytz.utc)
    return as_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def json_date_to_datetime(date_str):
    """
    Parses a datetime from a JSON string value
    """
    return iso8601.parse_date(date_str)


def get_dict_from_cursor(cursor):
    """
    Returns all rows from a cursor as a dict
    """
    desc = cursor.description
    return [
        dict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]


def chunk_list(iterable, size):
    """
    Splits a very large list into evenly sized chunks.
    Returns an iterator of lists that are no more than the size passed in.
    """
    source_iter = iter(iterable)
    while True:
        chunk_iter = islice(source_iter, size)
        yield chain([next(chunk_iter)], chunk_iter)


def get_linked_orgs(authenticated=False):
    all_orgs = Org.objects.filter(is_active=True).order_by('name')

    linked_sites = list(getattr(settings, 'PREVIOUS_ORG_SITES', []))

    # populate a ureport site for each org so we can link off to them
    for org in all_orgs:
        host = org.build_host_link(authenticated)
        org.host = host
        if org.get_config('is_on_landing_page'):
            flag = Image.objects.filter(org=org, is_active=True, image_type=FLAG).first()
            if flag:
                linked_sites.append(dict(name=org.subdomain, host=host, flag=flag.image.url, is_static=False))

    linked_sites_sorted = sorted(linked_sites, key=lambda k: k['name'].lower())

    return linked_sites_sorted


def substitute_segment(org, segment_in):
    if not segment_in:
        return segment_in

    segment = copy.deepcopy(segment_in)

    location = segment.get('location', None)
    if location == 'State':
        segment['location'] = org.get_config('state_label')
    elif location == 'District':
        segment['location'] = org.get_config('district_label')
    elif location == 'Ward':
        segment['location'] = org.get_config('ward_label')

    if org.get_config('is_global'):
        if "location" in segment:
            del segment["location"]
            if 'parent' in segment:
                del segment["parent"]
            segment["contact_field"] = org.get_config('state_label')
            segment["values"] = [elt.alpha_2 for elt in list(pycountry.countries)]

    return json.dumps(segment)


def clean_global_results_data(org, results, segment):

    # for the global page clean the data translating country code to country name
    if org.get_config('is_global') and results and segment and 'location' in segment:
        for elt in results:
            country_code = elt['label']
            elt['boundary'] = country_code
            country_name = ""
            try:
                country = pycountry.countries.get(alpha_2=country_code)
                if country:
                    country_name = country.name
            except KeyError:
                country_name = country_code
            elt['label'] = country_name

    return results


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
                    decade = ((current_year - int(elt['label'])) // 10) * 10
                    key = "%s-%s" % (decade, decade + 10)
                    if interval_dict.get(key, None):
                        interval_dict[key] += elt['count']
                    else:
                        interval_dict[key] = elt['count']
            except ValueError:
                pass

        for obj_key in interval_dict.keys():
            cleaned_categories.append(dict(label=obj_key, count=interval_dict[obj_key]))

        api_data[0]['categories'] = sorted(cleaned_categories, key=lambda k: int(k['label'].split('-')[0]))

    elif api_data and contact_field.lower() == org.get_config('registration_label').lower():
        six_months_ago = now - timedelta(days=180)
        six_months_ago = six_months_ago - timedelta(six_months_ago.weekday())
        tz = pytz.timezone('UTC')

        for elt in api_data[0]['categories']:
            time_str = elt['label']

            # ignore anything like None as label
            if not time_str:
                continue

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


def fetch_flows(org, backend_slug=None):
    from ureport.polls.models import CACHE_ORG_FLOWS_KEY, UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME
    start = time.time()
    print("Fetching flows for %s" % org.name)

    this_time = datetime.now()
    org_flows = dict(time=datetime_to_ms(this_time))

    backends = org.backends.filter(is_active=True)
    for backend_obj in backends:
        backend = org.get_backend(backend_slug=backend_obj.slug)
        try:
            all_flows = backend.fetch_flows(org)
            org_flows[backend_obj.slug] = all_flows

            all_flows_key = CACHE_ORG_FLOWS_KEY % org.pk
            cache.set(all_flows_key, org_flows, UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME)

        except Exception:
            client.captureException()
            import traceback
            traceback.print_exc()

    print("Fetch %s flows took %ss" % (org.name, time.time() - start))

    return org_flows.get(backend_slug) if backend_slug else dict()


def get_flows(org, backend_slug='rapidro'):
    from ureport.polls.models import CACHE_ORG_FLOWS_KEY
    cache_value = cache.get(CACHE_ORG_FLOWS_KEY % org.pk, None)
    if cache_value and backend_slug in cache_value:
        return cache_value[backend_slug]

    return fetch_flows(org, backend_slug)


def update_poll_flow_data(org):
    flows = get_flows(org)

    if flows:
        org_polls = Poll.objects.filter(org=org)
        for poll in org_polls:
            flow = flows.get(poll.flow_uuid, dict())

            if flow:
                archived = flow.get('archived', False)
                runs_count = flow.get('runs', 0)
                if not runs_count:
                    runs_count = 0

                updated_fields = dict()

                if archived != poll.flow_archived:
                    updated_fields['flow_archived'] = archived

                if runs_count > 0 and runs_count != poll.runs_count:
                    updated_fields['runs_count'] = runs_count

                if updated_fields:
                    Poll.objects.filter(pk=poll.pk).update(**updated_fields)


def fetch_old_sites_count():
    import requests
    import re
    from ureport.polls.models import UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME

    start = time.time()
    this_time = datetime.now()
    linked_sites = list(getattr(settings, 'PREVIOUS_ORG_SITES', []))

    old_site_values = []

    for site in linked_sites:
        count_link = site.get('count_link', "")
        if count_link:
            try:
                response = requests.get(count_link)
                response.raise_for_status()

                count = int(re.search(r'\d+', response.content).group())
                key = "org:%s:reporters:%s" % (site.get('name').lower(), 'old-site')
                value = {'time': datetime_to_ms(this_time), 'results': dict(size=count)}
                old_site_values.append(value)
                cache.set(key, value, UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME)
            except Exception:
                import traceback
                traceback.print_exc()

    # delete the global count cache to force a recalculate at the end
    cache.delete(GLOBAL_COUNT_CACHE_KEY)

    print("Fetch old sites counts took %ss" % (time.time() - start))
    return old_site_values


def get_global_count():

    count_cached_value = cache.get(GLOBAL_COUNT_CACHE_KEY, None)
    if count_cached_value:
        return count_cached_value

    try:
        old_site_reporter_counter_keys = cache.keys('org:*:reporters:old-site')

        cached_values = [cache.get(key) for key in old_site_reporter_counter_keys]

        # no old sites cache values, double check with a fetch
        if not cached_values:
            cached_values = fetch_old_sites_count()

        count = sum([elt['results'].get('size', 0) for elt in cached_values if elt.get('results', None)])

        for org in Org.objects.filter(is_active=True):
            if org.get_config('is_on_landing_page'):
                count += get_reporters_count(org)

        # cached for 10 min
        cache.set(GLOBAL_COUNT_CACHE_KEY, count, 60 * 10)
    except AttributeError:
        import traceback
        traceback.print_exc()
        count = '__'

    return count


def get_org_contacts_counts(org):

    from ureport.contacts.models import ReportersCounter

    key = ORG_CONTACT_COUNT_KEY % org.pk
    org_contacts_counts = cache.get(key, None)
    if org_contacts_counts:
        return org_contacts_counts

    org_contacts_counts = ReportersCounter.get_counts(org)
    cache.set(key, org_contacts_counts, ORG_CONTACT_COUNT_TIMEOUT)
    return org_contacts_counts


def get_gender_stats(org):
    org_contacts_counts = get_org_contacts_counts(org)

    female_count = org_contacts_counts.get('gender:f', 0)
    male_count = org_contacts_counts.get('gender:m', 0)

    if not female_count and not male_count:
        return dict(female_count=female_count, female_percentage="---",
                    male_count=male_count, male_percentage="---")

    total = female_count + male_count

    female_percentage = int(female_count * 100 / total)
    male_percentage = 100 - female_percentage

    return dict(female_count=female_count, female_percentage=six.text_type(female_percentage) + "%",
                male_count=male_count, male_percentage=six.text_type(male_percentage) + "%")


def get_age_stats(org):
    now = timezone.now()
    current_year = now.year

    org_contacts_counts = get_org_contacts_counts(org)

    year_counts = {k[-4:]: v for k, v in org_contacts_counts.items() if k.startswith("born:") and len(k) == 9}

    age_counts_interval = dict()
    age_counts_interval['0-14'] = 0
    age_counts_interval['15-19'] = 0
    age_counts_interval['20-24'] = 0
    age_counts_interval['25-30'] = 0
    age_counts_interval['31-34'] = 0
    age_counts_interval['35+'] = 0

    total = 0
    for year_key, age_count in year_counts.items():
        total += age_count
        age = current_year - int(year_key)
        if age > 34:
            age_counts_interval['35+'] += age_count
        elif age > 30:
            age_counts_interval['31-34'] += age_count
        elif age > 24:
            age_counts_interval['25-30'] += age_count
        elif age > 19:
            age_counts_interval['20-24'] += age_count
        elif age > 14:
            age_counts_interval['15-19'] += age_count
        else:
            age_counts_interval['0-14'] += age_count

    age_stats = age_counts_interval
    if total > 0:
        age_stats = {k: int(round(v * 100 / float(total))) for k, v in age_counts_interval.items()}

    return json.dumps(sorted([dict(name=k, y=v) for k, v in age_stats.items()], key=lambda i: i['name']))


def get_registration_stats(org):
    now = timezone.now()
    six_months_ago = now - timedelta(days=180)
    six_months_ago = six_months_ago - timedelta(six_months_ago.weekday())
    tz = pytz.timezone('UTC')

    org_contacts_counts = get_org_contacts_counts(org)

    registered_on_counts = {k[14:]: v for k, v in org_contacts_counts.items() if k.startswith("registered_on")}

    interval_dict = dict()

    for date_key, date_count in registered_on_counts.items():
        parsed_time = tz.localize(datetime.strptime(date_key, '%Y-%m-%d'))

        # this is in the range we care about
        if parsed_time > six_months_ago:
            # get the week of the year
            dict_key = parsed_time.strftime("%W")

            if interval_dict.get(dict_key, None):
                interval_dict[dict_key] += date_count
            else:
                interval_dict[dict_key] = date_count

    # build our final dict using week numbers
    categories = []
    start = six_months_ago
    while start < timezone.now():
        week_dict = start.strftime("%W")
        count = interval_dict.get(week_dict, 0)
        categories.append(dict(label=start.strftime("%m/%d/%y"), count=count))

        start = start + timedelta(days=7)

    return json.dumps(categories)


def get_ureporters_locations_stats(org, segment):
    parent = segment.get('parent', None)
    field_type = segment.get('location', None)

    location_stats = []

    if not field_type or field_type.lower() not in ['state', 'district', 'ward']:
        return location_stats

    field_type = field_type.lower()

    org_contacts_counts = get_org_contacts_counts(org)

    if field_type == 'state':
        boundary_top_level = Boundary.COUNTRY_LEVEL if org.get_config('is_global') else Boundary.STATE_LEVEL
        boundaries = Boundary.objects.filter(org=org, level=boundary_top_level, is_active=True).values('osm_id', 'name')\
            .order_by('osm_id')
        location_counts = {k[6:]: v for k, v in org_contacts_counts.items() if k.startswith('state')}

    elif field_type == 'ward':
        boundaries = Boundary.objects.filter(org=org, level=Boundary.WARD_LEVEL, parent__osm_id__iexact=parent).values('osm_id', 'name').order_by('osm_id')
        location_counts = {k[5:]: v for k, v in org_contacts_counts.items() if k.startswith('ward')}
    else:
        boundaries = Boundary.objects.filter(org=org, level=Boundary.DISTRICT_LEVEL, is_active=True,
                                             parent__osm_id__iexact=parent).values('osm_id', 'name').order_by('osm_id')
        location_counts = {k[9:]: v for k, v in org_contacts_counts.items() if k.startswith('district')}

    return [dict(boundary=elt['osm_id'], label=elt['name'], set=location_counts.get(elt['osm_id'], 0))
            for elt in boundaries]


def get_reporters_count(org):
    org_contacts_counts = get_org_contacts_counts(org)

    return org_contacts_counts.get("total-reporters", 0)


def get_occupation_stats(org):

    org_contacts_counts = get_org_contacts_counts(org)

    occupation_counts = {k[11:]: v for k, v in org_contacts_counts.items() if k.startswith("occupation")}

    return json.dumps(sorted([dict(label=k, count=v)
                              for k, v in occupation_counts.items() if k and k.lower() != "All Responses".lower()],
                             key=lambda i: i['count'], reverse=True)[:9])


def get_regions_stats(org):

    org_contacts_counts = get_org_contacts_counts(org)
    boundaries_name = Boundary.get_org_top_level_boundaries_name(org)

    boundaries_stats = {k[6:]: v for k, v in org_contacts_counts.items() if len(k) > 7 and k.startswith('state')}

    regions_stats = sorted([dict(name=boundaries_name[k], count=v) for k, v in boundaries_stats.items()
                            if k and k in boundaries_name], key=lambda i: i['count'], reverse=True)

    return regions_stats


def get_segment_org_boundaries(org, segment):
    location_boundaries = []
    if not segment:
        return location_boundaries

    if segment.get('location') == 'District':
        state_id = segment.get('parent', None)
        if state_id:
            location_boundaries = org.boundaries.filter(level=Boundary.DISTRICT_LEVEL,
                                                        is_active=True,
                                                        parent__osm_id=state_id).values('osm_id', 'name').order_by('osm_id')

    elif segment.get('location') == 'Ward':
        district_id = segment.get('parent', None)
        if district_id:
            location_boundaries = org.boundaries.filter(level=Boundary.WARD_LEVEL,
                                                        is_active=True,
                                                        parent__osm_id=district_id).values('osm_id', 'name').order_by('osm_id')

    else:
        if org.get_config('is_global'):
            location_boundaries = org.boundaries.filter(level=Boundary.COUNTRY_LEVEL, is_active=True).values('osm_id', 'name').order_by('osm_id')
        else:
            location_boundaries = org.boundaries.filter(level=Boundary.STATE_LEVEL, is_active=True).values('osm_id', 'name').order_by('osm_id')

    return location_boundaries


def populate_age_and_gender_poll_results(org=None):
    from ureport.contacts.models import Contact
    LAST_POPULATED_CONTACT = 'last-contact-id-populated'

    last_contact_id_populated = cache.get(LAST_POPULATED_CONTACT, 0)

    all_contacts = Contact.objects.filter(id__gt=last_contact_id_populated).values_list('id', flat=True).order_by('id')

    if org is not None:
        all_contacts = Contact.objects.filter(org=org).values_list('id', flat=True).order_by('id')

    start = time.time()
    i = 0

    all_contacts = list(all_contacts)

    for contact_id_batch in chunk_list(all_contacts, 1000):
        contact_batch = list(contact_id_batch)
        contacts = Contact.objects.filter(id__in=contact_batch)
        for contact in contacts:
            i += 1

            update_fields = dict()
            if contact.born > 0:
                update_fields['born'] = contact.born

            if contact.gender != '':
                update_fields['gender'] = contact.gender

            if update_fields:
                results_ids = list(PollResult.objects.filter(contact=contact.uuid).values_list('id', flat=True))
                PollResult.objects.filter(id__in=results_ids).update(**update_fields)

            if org is None:
                cache.set(LAST_POPULATED_CONTACT, contact.pk, None)

        print("Processed poll results update %d / %d contacts in %ds" % (i, len(all_contacts), time.time() - start))


Org.get_occupation_stats = get_occupation_stats
Org.get_reporters_count = get_reporters_count
Org.get_ureporters_locations_stats = get_ureporters_locations_stats
Org.get_registration_stats = get_registration_stats
Org.get_age_stats = get_age_stats
Org.get_gender_stats = get_gender_stats
Org.get_regions_stats = get_regions_stats
Org.organize_categories_data = organize_categories_data
Org.get_flows = get_flows
Org.substitute_segment = substitute_segment
Org.get_segment_org_boundaries = get_segment_org_boundaries
