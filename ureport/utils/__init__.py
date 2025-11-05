# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import logging
import time
import zoneinfo
from collections import defaultdict
from datetime import datetime, timedelta, timezone as tzone
from itertools import chain, islice

import iso8601
import six
from sentry_sdk import capture_exception

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from dash.orgs.models import Org
from dash.utils import datetime_to_ms
from ureport.assets.models import LOGO, Image
from ureport.locations.models import Boundary
from ureport.polls.models import Poll, PollResult

GLOBAL_COUNT_CACHE_KEY = "global_count"

ORG_CONTACT_COUNT_KEY = "org:%d:contacts-counts"
ORG_CONTACT_COUNT_TIMEOUT = 3600

logger = logging.getLogger(__name__)


UNICEF_REGIONS = [
    dict(name="All", label=_("All locations")),
    dict(name="EAPRO", label=_("East Asia and Pacific")),
    dict(name="ESARO", label=_("Eastern and Southern Africa")),
    dict(name="ECARO", label=_("Europe and Central Asia")),
    dict(name="LACRO", label=_("Latin America and the Caribbean")),
    dict(name="MENA", label=_("Middle East and North Africa")),
    dict(name="ROSA", label=_("South Asia")),
    dict(name="NATCOM", label=_("UNICEF’s National Committee countries")),
    dict(name="WCARO", label=_("West and Central Africa")),
]


def offline_context():
    for org in list(Org.objects.filter(is_active=True)):
        yield dict(STATIC_URL=settings.STATIC_URL, base_template="frame.html", org=org, debug=False, testing=False)


def datetime_to_json_date(dt):
    """
    Formats a datetime as a string for inclusion in JSON
    """
    # always output as UTC / Z and always include milliseconds
    as_utc = dt.astimezone(tzone.utc)
    return as_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def json_date_to_datetime(date_str):
    """
    Parses a datetime from a JSON string value
    """
    return iso8601.parse_date(date_str)


def get_last_months(months_num=12, start_time=None):
    if start_time is None:
        start_time = datetime.now()

    start = start_time.date().replace(day=1)

    months = [str(start)]
    i = 1
    while i < months_num:
        start = (start - timedelta(days=1)).replace(day=1)
        months.insert(0, str(start))
        i += 1

    return months


def get_time_filter_dates_map(time_filter=12):
    start_time = datetime.now()
    end_time = start_time - timedelta(days=time_filter * 30)

    if time_filter != 3:
        end_time = end_time.replace(day=1)

    keys_map = dict()
    while start_time >= end_time:
        val = start_time.date()
        if time_filter == 12:
            val = start_time.date().replace(day=1)
        if time_filter == 6:
            if val.day < 16:
                val = start_time.date().replace(day=1)
            else:
                val = start_time.date().replace(day=16)
        if time_filter == 3:
            if val.day < 11:
                val = start_time.date().replace(day=1)
            elif val.day < 21:
                val = start_time.date().replace(day=11)
            else:
                val = start_time.date().replace(day=21)

        keys_map[str(start_time.date())] = str(val)
        start_time = start_time - timedelta(days=1)

    return keys_map


def get_dict_from_cursor(cursor):
    """
    Returns all rows from a cursor as a dict
    """
    desc = cursor.description
    return [dict(zip([col[0] for col in desc], row)) for row in cursor.fetchall()]


def chunk_list(iterable, size):
    """
    Splits a very large list into evenly sized chunks.
    Returns an iterator of lists that are no more than the size passed in.
    """
    source_iter = iter(iterable)
    while True:
        chunk_iter = islice(source_iter, size)
        try:
            yield chain([next(chunk_iter)], chunk_iter)
        except StopIteration:
            return


def get_logo(org):
    if hasattr(org, "_logo_field"):
        return org._logo_field

    logo_field = org.logo
    logo = Image.objects.filter(org=org, is_active=True, image_type=LOGO).first()
    if logo:
        logo_field = logo.image
    org._logo_field = logo_field
    return logo_field


def fetch_flows(org, backend=None):
    from ureport.polls.models import CACHE_ORG_FLOWS_KEY, UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME

    start = time.time()
    logger.info("Fetching flows for %s" % org.name)

    if backend:
        backends = [backend]
    else:
        backends = org.backends.filter(is_active=True)

    this_time = datetime.now()
    org_flows = dict(time=datetime_to_ms(this_time), results=dict())

    for backend_obj in backends:
        backend = org.get_backend(backend_slug=backend_obj.slug)
        try:
            all_flows = backend.fetch_flows(org)
            org_flows["results"] = all_flows

            cache_key = CACHE_ORG_FLOWS_KEY % (org.pk, backend_obj.slug)
            cache.set(cache_key, org_flows, UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME)

        except Exception as e:
            capture_exception(e)
            import traceback

            traceback.print_exc()

    logger.info("Fetch %s flows took %ss" % (org.name, time.time() - start))

    if len(backends):
        return org_flows.get("results", dict())


def get_flows(org, backend):
    from ureport.polls.models import CACHE_ORG_FLOWS_KEY

    cache_value = cache.get(CACHE_ORG_FLOWS_KEY % (org.pk, backend.slug), None)
    if cache_value:
        return cache_value["results"]

    return fetch_flows(org, backend)


def update_poll_flow_data(org):
    backends = org.backends.filter(is_active=True)
    for backend_obj in backends:
        flows = get_flows(org, backend_obj)

        if flows:
            org_polls = Poll.objects.filter(org=org, backend=backend_obj)
            for poll in org_polls:
                flow = flows.get(poll.flow_uuid, dict())

                if flow:
                    archived = flow.get("archived", False)
                    runs_count = flow.get("runs", 0)
                    if not runs_count:
                        runs_count = 0

                    updated_fields = dict()

                    if archived != poll.flow_archived:
                        updated_fields["flow_archived"] = archived

                    if runs_count > 0 and runs_count != poll.runs_count:
                        updated_fields["runs_count"] = runs_count

                    if updated_fields:
                        Poll.objects.filter(pk=poll.pk).update(**updated_fields)


def fetch_shared_sites_count():
    import requests

    this_time = datetime.now()
    try:
        response = requests.get("https://ureport.in/shared_sites_count/")
        response.raise_for_status()

        value = {"time": datetime_to_ms(this_time), "results": response.json()}
        cache.set("shared_sites", value, None)
        return value["results"]
    except Exception:
        import traceback

        traceback.print_exc()


def get_shared_sites_count():
    cache_value = cache.get("shared_sites", None)
    if cache_value:
        return cache_value["results"]
    if getattr(settings, "IS_PROD", False):
        return fetch_shared_sites_count()
    return {}


def get_shared_global_count():
    return get_shared_sites_count().get("global_count", 0)


def get_shared_countries_number():
    return get_shared_sites_count().get("countries_count", 0)


def get_shared_linked_sites():
    return get_shared_sites_count().get("linked_sites", [])


def get_linked_orgs(authenticated=False):
    shared_linked_sites = get_shared_linked_sites()
    linked_sites = [elt for elt in shared_linked_sites if elt.get("show_icon", True)]

    linked_sites_sorted = sorted(linked_sites, key=lambda k: k["name"].lower())

    return linked_sites_sorted


def fetch_old_sites_count():
    import re

    import requests

    start = time.time()
    this_time = datetime.now()
    linked_sites = list(getattr(settings, "COUNTRY_FLAGS_SITES", []))

    old_site_values = []

    for site in linked_sites:
        count_link = site.get("count_link", "")
        if count_link:
            try:
                response = requests.get(count_link)
                response.raise_for_status()

                count = int(re.search(r"\d+", response.content.decode("utf-8")).group())
                key = "org:%s:reporters:%s" % (site.get("name").lower(), "old-site")
                value = {"time": datetime_to_ms(this_time), "results": dict(size=count)}
                old_site_values.append(value)
                cache.set(key, value, None)
            except Exception:
                import traceback

                traceback.print_exc()

    # delete the global count cache to force a recalculate at the end
    cache.delete(GLOBAL_COUNT_CACHE_KEY)

    logger.info("Fetch old sites counts took %ss" % (time.time() - start))
    return old_site_values


def get_global_count():
    count_cached_value = cache.get(GLOBAL_COUNT_CACHE_KEY, None)
    if count_cached_value:
        return count_cached_value

    try:
        linked_sites = list(getattr(settings, "COUNTRY_FLAGS_SITES", []))

        cached_values = []
        for site in linked_sites:
            count_link = site.get("count_link", "")
            if count_link:
                key = "org:%s:reporters:%s" % (site.get("name").lower(), "old-site")
                value = cache.get(key)
                if value:
                    cached_values.append(value)

        # no old sites cache values, double check with a fetch
        if not cached_values:
            cached_values = fetch_old_sites_count()

        count = sum([elt["results"].get("size", 0) for elt in cached_values if elt.get("results", None)])

        # cached for 10 min
        cache.set(GLOBAL_COUNT_CACHE_KEY, count, None)
    except AttributeError:
        import traceback

        traceback.print_exc()
        count = "__"

    return count


def get_org_contacts_counts(org):
    key = ORG_CONTACT_COUNT_KEY % org.pk
    org_contacts_counts = cache.get(key, None)
    if org_contacts_counts:
        cache.set(f"{key}-total-reporters", org_contacts_counts.get("total-reporters", 0), None)
        return org_contacts_counts

    return update_cache_org_contact_counts(org)


def update_cache_org_contact_counts(org):
    from ureport.contacts.models import ReportersCounter

    key = ORG_CONTACT_COUNT_KEY % org.pk
    org_contacts_counts = ReportersCounter.get_counts(org)
    cache.set(key, org_contacts_counts, None)
    return org_contacts_counts


def get_gender_labels(org):
    from ureport.stats.models import GenderSegment

    translation.activate(org.language)
    return {k: str(v) for k, v in GenderSegment.GENDERS.items()}


def get_gender_stats(org):
    org_contacts_counts = get_org_contacts_counts(org)

    has_extra_gender = org.get_config("common.has_extra_gender")

    female_count = org_contacts_counts.get("gender:f", 0)
    male_count = org_contacts_counts.get("gender:m", 0)
    other_count = org_contacts_counts.get("gender:o", 0)

    if not female_count and not male_count:
        output = dict(female_count=female_count, female_percentage="---", male_count=male_count, male_percentage="---")
        if has_extra_gender:
            output["other_count"] = 0
            output["other_percentage"] = "---"

        return output

    total = female_count + male_count
    if has_extra_gender:
        total += other_count

    female_percentage = female_count * 100 // total

    other_percentage = 0
    if has_extra_gender:
        other_percentage = other_count * 100 // total

    male_percentage = 100 - female_percentage - other_percentage

    output = dict(
        female_count=female_count,
        female_percentage=six.text_type(female_percentage) + "%",
        male_count=male_count,
        male_percentage=six.text_type(male_percentage) + "%",
    )
    if has_extra_gender:
        output["other_count"] = other_count
        output["other_percentage"] = six.text_type(other_percentage) + "%"

    return output


def get_age_stats(org):
    now = timezone.now()
    current_year = now.year

    org_contacts_counts = get_org_contacts_counts(org)

    year_counts = {k[-4:]: v for k, v in org_contacts_counts.items() if k.startswith("born:") and len(k) == 9}

    age_counts_interval = dict()
    age_counts_interval["0-14"] = 0
    age_counts_interval["15-19"] = 0
    age_counts_interval["20-24"] = 0
    age_counts_interval["25-30"] = 0
    age_counts_interval["31-34"] = 0
    age_counts_interval["35+"] = 0

    total = 0
    for year_key, age_count in year_counts.items():
        total += age_count
        age = current_year - int(year_key)
        if age > 34:
            age_counts_interval["35+"] += age_count
        elif age > 30:
            age_counts_interval["31-34"] += age_count
        elif age > 24:
            age_counts_interval["25-30"] += age_count
        elif age > 19:
            age_counts_interval["20-24"] += age_count
        elif age > 14:
            age_counts_interval["15-19"] += age_count
        else:
            age_counts_interval["0-14"] += age_count

    age_stats = age_counts_interval
    if total > 0:
        age_stats = {k: int(round(v * 100 / float(total))) for k, v in age_counts_interval.items()}

    return json.dumps(
        sorted(
            [dict(name=k, y=v, absolute_count=age_counts_interval.get(k, 0)) for k, v in age_stats.items()],
            key=lambda i: i["name"],
        )
    )


def get_schemes_stats(org):
    from ureport.stats.models import SchemeSegment

    org_contacts_counts = get_org_contacts_counts(org)
    schemes_counts = {
        k[7:]: v for k, v in org_contacts_counts.items() if k.startswith("scheme:") if k[7:] and k[7:] != "ext"
    }

    total = 0
    schemes_stats_data = defaultdict(int)
    for scheme, count in schemes_counts.items():
        total += count

        name = SchemeSegment.SCHEME_DISPLAY.get(scheme, scheme.upper())
        if not name:
            continue
        schemes_stats_data[name] += count

    scheme_stats = schemes_stats_data
    if total > 0:
        scheme_stats = {k: int(round(v * 100 / float(total))) for k, v in schemes_stats_data.items()}

    other_stat = 0
    other_absolute_count = 0
    output_dict = dict()
    for name, v in scheme_stats.items():
        if v <= 5:
            other_stat += v
            other_absolute_count += schemes_stats_data.get(name, 0)
        else:
            output_dict[name] = v

    output = sorted(
        [dict(name=k, y=v, absolute_count=schemes_stats_data.get(k, 0)) for k, v in output_dict.items()],
        key=lambda i: -i["y"],
    )

    if other_stat:
        output.append(dict(name="OTHERS", y=other_stat, absolute_count=other_absolute_count))
    return output


def get_sign_up_rate(org, time_filter):
    now = timezone.now()
    year_ago = now - timedelta(days=365)
    start = year_ago.replace(day=1)
    tz = zoneinfo.ZoneInfo("UTC")

    org_contacts_counts = get_org_contacts_counts(org)

    registered_on_counts = {k[14:]: v for k, v in org_contacts_counts.items() if k.startswith("registered_on")}

    interval_dict = defaultdict(int)

    dates_map = get_time_filter_dates_map(time_filter=time_filter)
    keys = list(set(dates_map.values()))

    for date_key, date_count in registered_on_counts.items():
        parsed_time = datetime.strptime(date_key, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
        )

        if parsed_time > start:
            key = dates_map.get(str(parsed_time.date()))

            interval_dict[key] += date_count

    data = dict()
    for key in keys:
        data[key] = interval_dict[key]

    return [dict(name="Sign-Up Rate", data=data)]


def get_sign_up_rate_location(org, time_filter):
    now = timezone.now()
    year_ago = now - timedelta(days=365)
    start = year_ago.replace(day=1)
    tz = zoneinfo.ZoneInfo("UTC")

    org_contacts_counts = get_org_contacts_counts(org)

    registered_on_counts = {k[17:]: v for k, v in org_contacts_counts.items() if k.startswith("registered_state")}

    top_boundaries = Boundary.get_org_top_level_boundaries_name(org)

    dates_map = get_time_filter_dates_map(time_filter=time_filter)
    keys = list(set(dates_map.values()))

    output_data = []

    for osm_id, name in top_boundaries.items():
        interval_dict = defaultdict(int)
        for date_key, date_count in registered_on_counts.items():
            if date_key.endswith(f":{osm_id.upper()}"):
                date_key = date_key[:10]
            else:
                continue

            parsed_time = datetime.strptime(date_key, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
            )

            if parsed_time > start:
                key = dates_map.get(str(parsed_time.date()))
                interval_dict[key] += date_count

        data = dict()
        for key in keys:
            data[key] = interval_dict[key]
        output_data.append(dict(name=name, osm_id=osm_id, data=data))
    return output_data


def get_sign_up_rate_gender(org, time_filter):
    from ureport.stats.models import GenderSegment

    now = timezone.now()
    year_ago = now - timedelta(days=365)
    start = year_ago.replace(day=1)
    tz = zoneinfo.ZoneInfo("UTC")

    org_gender_labels = org.get_gender_labels()

    org_contacts_counts = get_org_contacts_counts(org)

    registered_on_counts = {k[18:]: v for k, v in org_contacts_counts.items() if k.startswith("registered_gender")}

    genders = GenderSegment.objects.all()
    if not org.get_config("common.has_extra_gender"):
        genders = genders.exclude(gender="O")

    genders = genders.values("gender", "id")

    dates_map = get_time_filter_dates_map(time_filter=time_filter)
    keys = list(set(dates_map.values()))
    output_data = []

    for gender in genders:
        interval_dict = defaultdict(int)
        for date_key, date_count in registered_on_counts.items():
            if date_key.endswith(f":{gender['gender'].lower()}"):
                date_key = date_key[:-2]
            else:
                continue

            parsed_time = datetime.strptime(date_key, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
            )

            if parsed_time > start:
                key = dates_map.get(str(parsed_time.date()))
                interval_dict[key] += date_count

        data = dict()
        for key in keys:
            data[key] = interval_dict[key]
        output_data.append(dict(name=org_gender_labels.get(gender["gender"]), data=data))
    return output_data


def get_sign_up_rate_age(org, time_filter):
    from ureport.stats.models import AgeSegment

    now = timezone.now()
    current_year = now.year
    year_ago = now - timedelta(days=365)
    start = year_ago.replace(day=1)
    tz = zoneinfo.ZoneInfo("UTC")

    org_contacts_counts = get_org_contacts_counts(org)

    registered_on_counts = {k[16:]: v for k, v in org_contacts_counts.items() if k.startswith("registered_born")}
    registered_on_counts_by_age = {
        "0-14": defaultdict(int),
        "15-19": defaultdict(int),
        "20-24": defaultdict(int),
        "25-30": defaultdict(int),
        "31-34": defaultdict(int),
        "35+": defaultdict(int),
    }

    dates_map = get_time_filter_dates_map(time_filter=time_filter)
    keys = list(set(dates_map.values()))

    for date_key, date_count in registered_on_counts.items():
        date_key_date, date_key_year = date_key.split(":")
        parsed_time = datetime.strptime(date_key_date, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
        )
        if parsed_time < start:
            continue

        date_key_date = dates_map.get(str(parsed_time.date()))

        age = current_year - int(date_key_year)
        if age > 34:
            registered_on_counts_by_age["35+"][date_key_date] += date_count
        elif age > 30:
            registered_on_counts_by_age["31-34"][date_key_date] += date_count
        elif age > 24:
            registered_on_counts_by_age["25-30"][date_key_date] += date_count
        elif age > 19:
            registered_on_counts_by_age["20-24"][date_key_date] += date_count
        elif age > 14:
            registered_on_counts_by_age["15-19"][date_key_date] += date_count
        else:
            registered_on_counts_by_age["0-14"][date_key_date] += date_count

    ages = AgeSegment.objects.all().values("id", "min_age", "max_age")
    output_data = []
    for age in ages:
        if age["min_age"] == 0:
            data_key = "0-14"
        elif age["min_age"] == 15:
            data_key = "15-19"
        elif age["min_age"] == 20:
            data_key = "20-24"
        elif age["min_age"] == 25:
            data_key = "25-30"
        elif age["min_age"] == 31:
            data_key = "31-34"
        elif age["min_age"] == 35:
            data_key = "35+"

        age_data = registered_on_counts_by_age[data_key]
        data = dict()
        for key in keys:
            data[key] = age_data[key]

        output_data.append(dict(name=data_key, data=data))

    return output_data


def get_sign_up_rate_scheme(org, time_filter):
    from ureport.stats.models import SchemeSegment

    now = timezone.now()
    year_ago = now - timedelta(days=365)
    start = year_ago.replace(day=1)
    tz = zoneinfo.ZoneInfo("UTC")

    org_contacts_counts = get_org_contacts_counts(org)

    registered_on_counts = {k[18:]: v for k, v in org_contacts_counts.items() if k.startswith("registered_scheme")}

    schemes = [k[7:] for k, v in org_contacts_counts.items() if k.startswith("scheme:") if k[7:] and k[7:] != "ext"]
    registered_on_counts_by_scheme = {}

    for scheme in schemes:
        registered_on_counts_by_scheme[scheme] = defaultdict(int)

    dates_map = get_time_filter_dates_map(time_filter=time_filter)
    keys = list(set(dates_map.values()))

    for date_key, date_count in registered_on_counts.items():
        date_key_date, scheme = date_key.split(":")
        parsed_time = datetime.strptime(date_key_date, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tz
        )
        if parsed_time < start:
            continue

        date_key_date = dates_map.get(str(parsed_time.date()))

        if scheme not in registered_on_counts_by_scheme:
            registered_on_counts_by_scheme[scheme] = defaultdict(int)
        registered_on_counts_by_scheme[scheme][date_key_date] += date_count

    output_data = []
    for scheme in registered_on_counts_by_scheme.keys():
        scheme_data = registered_on_counts_by_scheme[scheme]
        data = dict()
        for key in keys:
            data[key] = scheme_data[key]

        name = SchemeSegment.SCHEME_DISPLAY.get(scheme, scheme.upper())
        if not name:
            continue
        output_data.append(dict(name=name, data=data))

    return output_data


def get_registration_stats(org):
    now = timezone.now()
    six_months_ago = now - timedelta(days=180)
    six_months_ago = six_months_ago - timedelta(six_months_ago.weekday())
    tz = zoneinfo.ZoneInfo("UTC")

    org_contacts_counts = get_org_contacts_counts(org)

    registered_on_counts = {k[14:]: v for k, v in org_contacts_counts.items() if k.startswith("registered_on")}

    interval_dict = dict()

    for date_key, date_count in registered_on_counts.items():
        parsed_time = datetime.strptime(date_key, "%Y-%m-%d").replace(tzinfo=tz)

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


def get_reporter_registration_dates(org):
    now = timezone.now()
    one_year_ago = now - timedelta(days=365)
    one_year_ago = one_year_ago - timedelta(one_year_ago.weekday())
    tz = zoneinfo.ZoneInfo("UTC")

    org_contacts_counts = get_org_contacts_counts(org)

    registered_on_counts = {k[14:]: v for k, v in org_contacts_counts.items() if k.startswith("registered_on")}

    interval_dict = dict()

    for date_key, date_count in registered_on_counts.items():
        parsed_time = datetime.strptime(date_key, "%Y-%m-%d").replace(tzinfo=tz)

        # this is in the range we care about
        if parsed_time > one_year_ago:
            # get the week of the year
            dict_key = parsed_time.strftime("%W")

            if interval_dict.get(dict_key, None):
                interval_dict[dict_key] += date_count
            else:
                interval_dict[dict_key] = date_count

    # build our final dict using week numbers
    categories = []
    start = one_year_ago + timedelta(days=7)
    while start < timezone.now():
        week_dict = start.strftime("%W")
        count = interval_dict.get(week_dict, 0)
        categories.append(dict(label=start.strftime("%m/%d/%y"), count=count))

        start = start + timedelta(days=7)
    return categories


def get_signups(org):
    registrations = get_reporter_registration_dates(org)
    return sum([elt.get("count", 0) for elt in registrations])


def get_signup_rate(org):
    new_signups = get_signups(org)
    total = get_reporters_count(org)
    if not total:
        return 0
    return new_signups * 100 / total


def get_ureporters_locations_stats(org, segment):
    parent = segment.get("parent", None)
    field_type = segment.get("location", None)

    location_stats = []

    if not field_type or field_type.lower() not in ["state", "district", "ward"]:
        return location_stats

    field_type = field_type.lower()

    org_contacts_counts = get_org_contacts_counts(org)

    if field_type == "state":
        boundary_top_level = Boundary.COUNTRY_LEVEL if org.get_config("common.is_global") else Boundary.STATE_LEVEL
        boundaries = (
            Boundary.objects.filter(org=org, level=boundary_top_level, is_active=True)
            .values("osm_id", "name")
            .order_by("osm_id")
        )
        location_counts = {k[6:]: v for k, v in org_contacts_counts.items() if k.startswith("state")}

    elif field_type == "ward":
        boundaries = (
            Boundary.objects.filter(org=org, level=Boundary.WARD_LEVEL, parent__osm_id__iexact=parent)
            .values("osm_id", "name")
            .order_by("osm_id")
        )
        location_counts = {k[5:]: v for k, v in org_contacts_counts.items() if k.startswith("ward")}
    else:
        boundaries = (
            Boundary.objects.filter(
                org=org, level=Boundary.DISTRICT_LEVEL, is_active=True, parent__osm_id__iexact=parent
            )
            .values("osm_id", "name")
            .order_by("osm_id")
        )
        location_counts = {k[9:]: v for k, v in org_contacts_counts.items() if k.startswith("district")}

    return [
        dict(boundary=elt["osm_id"], label=elt["name"], set=location_counts.get(elt["osm_id"], 0))
        for elt in boundaries
    ]


def get_ureporters_locations_response_rates(org, segment):
    from ureport.stats.models import PollStats

    parent = segment.get("parent", None)
    field_type = segment.get("location", None)

    location_stats = []

    if not field_type or field_type.lower() not in ["state", "district", "ward"]:
        return location_stats

    field_type = field_type.lower()
    now = timezone.now()
    year_ago = now - timedelta(days=365)

    if field_type == "state":
        boundary_top_level = Boundary.COUNTRY_LEVEL if org.get_config("common.is_global") else Boundary.STATE_LEVEL
        boundaries = (
            Boundary.objects.filter(org=org, level=boundary_top_level, is_active=True)
            .values("osm_id", "name", "id")
            .order_by("osm_id")
        )

    elif field_type == "ward":
        boundaries = (
            Boundary.objects.filter(org=org, level=Boundary.WARD_LEVEL, parent__osm_id__iexact=parent)
            .values("osm_id", "name", "id")
            .order_by("osm_id")
        )
    else:
        boundaries = (
            Boundary.objects.filter(
                org=org, level=Boundary.DISTRICT_LEVEL, is_active=True, parent__osm_id__iexact=parent
            )
            .values("osm_id", "name", "id")
            .order_by("osm_id")
        )

    boundaries_ids = [elt["id"] for elt in boundaries]
    polled_stats = (
        PollStats.objects.filter(org=org, date__gte=year_ago, location_id__in=boundaries_ids)
        .values("location__osm_id")
        .annotate(Sum("count"))
    )
    polled_stats_dict = {elt["location__osm_id"]: elt["count__sum"] for elt in polled_stats}
    responded_stats = (
        PollStats.objects.filter(org=org, date__gte=year_ago, location_id__in=boundaries_ids)
        .exclude(flow_result_category=None)
        .values("location__osm_id")
        .annotate(Sum("count"))
    )
    responded_stats_dict = {elt["location__osm_id"]: elt["count__sum"] for elt in responded_stats}

    response_rates = {
        key: round(responded_stats_dict.get(key, 0) * 100 / val, 1) for key, val in polled_stats_dict.items()
    }

    return [
        dict(boundary=elt["osm_id"], label=elt["name"], set=response_rates.get(elt["osm_id"], 0)) for elt in boundaries
    ]


def get_reporters_count(org):
    key = ORG_CONTACT_COUNT_KEY % org.pk
    cached_value = cache.get(f"{key}-total-reporters", None)
    if cached_value:
        return cached_value

    org_contacts_counts = get_org_contacts_counts(org)
    return org_contacts_counts.get("total-reporters", 0)


def get_occupation_stats(org):
    org_contacts_counts = get_org_contacts_counts(org)

    occupation_counts = {k[11:]: v for k, v in org_contacts_counts.items() if k.startswith("occupation")}

    return json.dumps(
        sorted(
            [
                dict(label=k, count=v)
                for k, v in occupation_counts.items()
                if k and k.lower() != "All Responses".lower()
            ],
            key=lambda i: i["count"],
            reverse=True,
        )[:9]
    )


def get_regions_stats(org):
    org_contacts_counts = get_org_contacts_counts(org)
    boundaries_name = Boundary.get_org_top_level_boundaries_name(org)

    boundaries_stats = {k[6:]: v for k, v in org_contacts_counts.items() if len(k) > 7 and k.startswith("state")}

    regions_stats = sorted(
        [dict(name=boundaries_name[k], count=v) for k, v in boundaries_stats.items() if k and k in boundaries_name],
        key=lambda i: i["count"],
        reverse=True,
    )

    return regions_stats


def get_segment_org_boundaries(org, segment):
    location_boundaries = []
    if not segment:
        return location_boundaries

    if segment.get("location").lower() == "district":
        state_id = segment.get("parent", None)
        if state_id:
            location_boundaries = (
                org.boundaries.filter(level=Boundary.DISTRICT_LEVEL, is_active=True, parent__osm_id=state_id)
                .values("id", "osm_id", "name")
                .order_by("osm_id")
            )

    elif segment.get("location").lower() == "ward":
        district_id = segment.get("parent", None)
        if district_id:
            location_boundaries = (
                org.boundaries.filter(level=Boundary.WARD_LEVEL, is_active=True, parent__osm_id=district_id)
                .values("id", "osm_id", "name")
                .order_by("osm_id")
            )

    else:
        if org.get_config("common.is_global"):
            location_boundaries = (
                org.boundaries.filter(level=Boundary.COUNTRY_LEVEL, is_active=True)
                .values("id", "osm_id", "name")
                .order_by("osm_id")
            )
        else:
            location_boundaries = (
                org.boundaries.filter(level=Boundary.STATE_LEVEL, is_active=True)
                .values("id", "osm_id", "name")
                .order_by("osm_id")
            )

    return location_boundaries


def populate_age_and_gender_poll_results(org=None):
    from ureport.contacts.models import Contact

    LAST_POPULATED_CONTACT = "last-contact-id-populated"

    last_contact_id_populated = cache.get(LAST_POPULATED_CONTACT, 0)

    all_contacts = Contact.objects.filter(id__gt=last_contact_id_populated).values_list("id", flat=True).order_by("id")

    if org is not None:
        all_contacts = Contact.objects.filter(org=org).values_list("id", flat=True).order_by("id")

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
                update_fields["born"] = contact.born

            if contact.gender != "":
                update_fields["gender"] = contact.gender

            if update_fields:
                results_ids = list(PollResult.objects.filter(contact=contact.uuid).values_list("id", flat=True))
                PollResult.objects.filter(id__in=results_ids).update(**update_fields)

            if org is None:
                cache.set(LAST_POPULATED_CONTACT, contact.pk, None)

        logger.info(
            "Processed poll results update %d / %d contacts in %ds" % (i, len(all_contacts), time.time() - start)
        )


def populate_contact_activity(org):
    from ureport.contacts.models import Contact

    now = timezone.now()
    now_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_date = now - timedelta(days=365)

    flows = list(
        Poll.objects.filter(org_id=org.id, published=True, poll_date__gte=start_date)
        .only("flow_uuid")
        .values_list("flow_uuid", flat=True)
    )

    all_contacts = Contact.objects.filter(org=org).values_list("id", flat=True).order_by("id")

    start = time.time()
    i = 0

    all_contacts = list(all_contacts)

    for contact_id_batch in chunk_list(all_contacts, 1000):
        contact_batch = list(contact_id_batch)
        contacts = Contact.objects.filter(id__in=contact_batch)
        for contact in contacts:
            i += 1
            results = PollResult.objects.filter(contact=contact.uuid, org_id=org.id, flow__in=flows).exclude(date=None)

            oldest_id = None
            newest_id = None
            oldest_seen = now
            newest_seen = start_date
            for result in results:
                if result.date > newest_seen:
                    newest_seen = result.date
                    newest_id = result.id
                if result.date < oldest_seen:
                    oldest_seen = result.date
                    oldest_id = result.id

                if oldest_seen <= start_date and newest_seen >= now_month:
                    break

            ids_to_update = []
            if oldest_id:
                ids_to_update.append(oldest_id)
            if newest_id:
                ids_to_update.append(newest_id)

            PollResult.objects.filter(id__in=ids_to_update).update(contact=contact.uuid)

        logger.info(
            "Processed poll results update %d / %d contacts in %ds" % (i, len(all_contacts), time.time() - start)
        )


Org.get_gender_labels = get_gender_labels
Org.get_org_contacts_counts = get_org_contacts_counts
Org.get_occupation_stats = get_occupation_stats
Org.get_reporters_count = get_reporters_count
Org.get_ureporters_locations_stats = get_ureporters_locations_stats
Org.get_registration_stats = get_registration_stats
Org.get_age_stats = get_age_stats
Org.get_gender_stats = get_gender_stats
Org.get_regions_stats = get_regions_stats
Org.get_flows = get_flows
Org.get_segment_org_boundaries = get_segment_org_boundaries
Org.get_signups = get_signups
Org.get_signup_rate = get_signup_rate
Org.get_ureporters_locations_response_rates = get_ureporters_locations_response_rates
Org.get_sign_up_rate = get_sign_up_rate
Org.get_sign_up_rate_gender = get_sign_up_rate_gender
Org.get_sign_up_rate_age = get_sign_up_rate_age
Org.get_sign_up_rate_scheme = get_sign_up_rate_scheme
Org.get_schemes_stats = get_schemes_stats
Org.get_logo = get_logo
Org.get_sign_up_rate_location = get_sign_up_rate_location
