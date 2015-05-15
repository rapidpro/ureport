import math
from datetime import timedelta, datetime
from dash.orgs.models import Org
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
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

    linked_sites_sorted = sorted(linked_sites, key=lambda k: k['name'])

    return linked_sites_sorted

def get_contact_field_results(org, contact_field, segment):
    if segment and org.get_config('is_global'):
        if "location" in segment:
            del segment["location"]
            segment["contact_field"] = org.get_config('state_label')
            segment["values"] = [elt.alpha2 for elt in pycountry.countries.objects]

    return org.get_api().get_contact_field_results(contact_field, segment)

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

Org.get_contact_field_results = get_contact_field_results
Org.get_most_active_regions = get_most_active_regions
Org.organize_categories_data = organize_categories_data