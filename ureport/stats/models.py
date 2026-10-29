import logging
import time
from collections import defaultdict
from datetime import timedelta

from django.core.cache import cache
from django.db import models
from django.db.models import IntegerField, JSONField, Q, Sum
from django.db.models.functions import Cast
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from dash.orgs.models import Org
from ureport.flows.models import FlowResult, FlowResultCategory
from ureport.locations.models import Boundary
from ureport.polls.models import Poll, PollQuestion
from ureport.utils.counts import BaseDailyCount, BaseScopedCount
from ureport.utils.models import SquashableModel

from . import active_users

logger = logging.getLogger(__name__)

# held while squashing poll stats counters, and while a poll rebuild replaces them
STATS_COUNTS_SQUASH_LOCK = "squash_stats_counts_lock"


class GenderSegment(models.Model):
    GENDERS = {"M": _("Male"), "F": _("Female"), "O": _("Other")}

    gender = models.CharField(max_length=1)


class AgeSegment(models.Model):
    min_age = models.IntegerField(null=True)
    max_age = models.IntegerField(null=True)

    @classmethod
    def get_age_segment_min_age(cls, age):
        min_ages = [0, 15, 20, 25, 31, 35]
        return [elt for elt in min_ages if age >= elt][-1]


class SchemeSegment(models.Model):
    SCHEME_DISPLAY = {"tel": "SMS", "twitterid": "TWITTER", "ext": None, "fcm": "U-REPORT APP"}

    scheme = models.CharField(max_length=16, unique=True)


class PollStatsCounter(BaseScopedCount):
    squash_max_distinct = 100000
    squash_over = ("org_id", "flow_result_id", "flow_result_category_id", "scope")

    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="poll_stats_segments")

    flow_result = models.ForeignKey(FlowResult, on_delete=models.PROTECT)

    flow_result_category = models.ForeignKey(FlowResultCategory, null=True, on_delete=models.SET_NULL)

    @classmethod
    def get_average_response_rate(cls, org):
        key = f"org:{org.id}:average_response_rate"
        output_data = cache.get(key, None)
        if output_data:
            return output_data["results"]

        return PollStatsCounter.calculate_average_response_rate(org)

    @classmethod
    def calculate_average_response_rate(cls, org):
        key = f"org:{org.id}:average_response_rate"

        poll_ids = list(
            Poll.objects.filter(org_id=org.id, published=True, is_active=True).only("id").values_list("id", flat=True)
        )

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll_id__in=poll_ids).values_list("flow_result_id", flat=True)
        )

        polled_stats = PollStatsCounter.objects.filter(
            org=org, flow_result_id__in=flow_result_ids, scope="all"
        ).aggregate(Sum("count"))

        responded_stats = (
            PollStatsCounter.objects.filter(org=org, flow_result_id__in=flow_result_ids, scope="all")
            .exclude(flow_result_category=None)
            .aggregate(Sum("count"))
        )

        responded = responded_stats.get("count__sum", 0)
        if responded is None:
            responded = 0
        polled = polled_stats.get("count__sum")
        if polled is None or polled == 0:
            return 0

        percentage = responded * 100 / polled
        cache.set(key, {"results": percentage}, None)

        return percentage

    class Meta:
        indexes = [
            models.Index(fields=["org", "flow_result"], name="stats_psc_org_flowresult_idx"),
            # for squashing task
            models.Index(
                name="stats_psc_unsquashed",
                fields=("org", "flow_result", "flow_result_category", "scope"),
                condition=Q(is_squashed=False),
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                name="stats_psc_squashed",
                fields=("org", "flow_result", "flow_result_category", "scope"),
                condition=Q(is_squashed=True),
                nulls_distinct=False,
            )
        ]


class PollEngagementDailyCount(BaseDailyCount):
    DATA_TIME_FILTERS = {3: _("90 Days"), 6: _("6 Months"), 12: _("12 Months")}

    DATA_SEGMENTS = {
        "all": _("All"),
        "gender": _("Gender"),
        "age": _("Age"),
        "scheme": _("Channels"),
        "location": _("Location"),
    }

    DATA_METRICS = {
        "opinion-responses": _("Opinion Responses"),
        "sign-up-rate": _("Sign Up Rate"),
        "response-rate": _("Response Rate"),
        "active-users": _("Active Users"),
    }

    squash_max_distinct = 100000
    squash_over = ("org_id", "flow_result_id", "is_responded", "scope", "day")

    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="poll_engagement_stats")

    flow_result = models.ForeignKey(FlowResult, on_delete=models.PROTECT)

    is_responded = models.BooleanField(null=True)

    @classmethod
    def get_engagement_data(cls, org, metric, segment_slug, time_filter):
        key = f"org:{org.id}:metric:{metric}:segment:{segment_slug}:filter:{time_filter}"
        output_data = cache.get(key, None)
        if output_data:
            return output_data["results"]

        # the other usual time filters come from the same rows, so a miss on one of them refreshes them all
        time_filters = None if time_filter in PollEngagementDailyCount.DATA_TIME_FILTERS else [time_filter]
        return PollEngagementDailyCount.refresh_engagement_data(org, metric, segment_slug, time_filters)[time_filter]

    @classmethod
    def refresh_engagement_data(cls, org, metric, segment_slug, time_filters=None):
        """
        Calculates and caches the data of one metric and segment for each of the given time filters, all of them by
        default. Every time filter's data is bucketed from the same last year of counts, so those are fetched once and
        each time filter's buckets derived from them. Returns the data by time filter.
        """
        time_filters = sorted(time_filters or PollEngagementDailyCount.DATA_TIME_FILTERS)

        output_data = {}
        if metric == "opinion-responses":
            if segment_slug == "all":
                output_data = PollEngagementDailyCount.get_all_opinion_responses(org, time_filters)
            if segment_slug == "age":
                output_data = PollEngagementDailyCount.get_age_opinion_responses(org, time_filters)
            if segment_slug == "gender":
                output_data = PollEngagementDailyCount.get_gender_opinion_responses(org, time_filters)
            if segment_slug == "location":
                output_data = PollEngagementDailyCount.get_location_opinion_responses(org, time_filters)
            if segment_slug == "scheme":
                output_data = PollEngagementDailyCount.get_scheme_opinion_responses(org, time_filters)

        if metric == "sign-up-rate":
            if segment_slug == "all":
                output_data = org.get_sign_up_rate(time_filters)
            if segment_slug == "age":
                output_data = org.get_sign_up_rate_age(time_filters)
            if segment_slug == "gender":
                output_data = org.get_sign_up_rate_gender(time_filters)
            if segment_slug == "location":
                output_data = org.get_sign_up_rate_location(time_filters)
            if segment_slug == "scheme":
                output_data = org.get_sign_up_rate_scheme(time_filters)

        if metric == "response-rate":
            if segment_slug == "all":
                output_data = PollEngagementDailyCount.get_all_response_rate_series(org, time_filters)
            if segment_slug == "age":
                output_data = PollEngagementDailyCount.get_age_response_rate_series(org, time_filters)
            if segment_slug == "gender":
                output_data = PollEngagementDailyCount.get_gender_response_rate_series(org, time_filters)
            if segment_slug == "location":
                output_data = PollEngagementDailyCount.get_location_response_rate_series(org, time_filters)
            if segment_slug == "scheme":
                output_data = PollEngagementDailyCount.get_scheme_response_rate_series(org, time_filters)

        if metric == "active-users" and active_users.is_read_enabled(org):
            output_data = active_users.get_activity(org, segment_slug, time_filters)
        elif metric == "active-users":
            if segment_slug == "all":
                output_data = ContactActivity.get_activity(org, time_filters)
            if segment_slug == "age":
                output_data = ContactActivity.get_activity_age(org, time_filters)
            if segment_slug == "gender":
                output_data = ContactActivity.get_activity_gender(org, time_filters)
            if segment_slug == "location":
                output_data = ContactActivity.get_contact_activity_location(org, time_filters)
            if segment_slug == "scheme":
                output_data = ContactActivity.get_contact_activity_scheme(org, time_filters)

        results = {}
        for time_filter in time_filters:
            results[time_filter] = output_data.get(time_filter, [])
            if results[time_filter]:
                key = f"org:{org.id}:metric:{metric}:segment:{segment_slug}:filter:{time_filter}"
                cache.set(key, {"results": results[time_filter]}, None)
        return results

    @classmethod
    def get_all_opinion_responses(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        translation.activate(org.language)

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        responses = list(
            PollEngagementDailyCount.objects.filter(
                org=org, day__gte=start, scope="all", flow_result_id__in=flow_result_ids, is_responded=True
            )
            .values(date=Cast("day", output_field=models.DateTimeField()))
            .annotate(Sum("count"))
        )
        return {
            time_filter: [
                dict(
                    name=str(_("Opinion Responses")),
                    data=PollEngagementDailyCount.get_counts_data(responses, time_filter),
                )
            ]
            for time_filter in time_filters
        }

    @classmethod
    def get_gender_opinion_responses(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        org_gender_labels = org.get_gender_labels()

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        genders = GenderSegment.objects.all()
        if not org.get_config("common.has_extra_gender"):
            genders = genders.exclude(gender="O")

        genders = genders.values("gender", "id")

        output_data = {time_filter: [] for time_filter in time_filters}
        for gender in genders:
            responses = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"gender:{gender['gender'].lower()}",
                    flow_result_id__in=flow_result_ids,
                    is_responded=True,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            for time_filter in time_filters:
                series = PollEngagementDailyCount.get_counts_data(responses, time_filter)
                output_data[time_filter].append(dict(name=org_gender_labels.get(gender["gender"]), data=series))
        return output_data

    @classmethod
    def get_scheme_opinion_responses(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        translation.activate(org.language)

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        schemes = SchemeSegment.objects.all().values("scheme", "id")
        org_contacts_counts = org.get_org_contacts_counts()
        org_schemes = [k[7:] for k, v in org_contacts_counts.items() if k.startswith("scheme:") if k[7:]]

        output_data = {time_filter: [] for time_filter in time_filters}
        for scheme in schemes:
            if scheme["scheme"] not in org_schemes:
                continue

            name = SchemeSegment.SCHEME_DISPLAY.get(scheme["scheme"], scheme["scheme"].upper())
            if not name:
                continue

            responses = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"scheme:{scheme['scheme'].lower()}",
                    flow_result_id__in=flow_result_ids,
                    is_responded=True,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            for time_filter in time_filters:
                series = PollEngagementDailyCount.get_counts_data(responses, time_filter)
                output_data[time_filter].append(dict(name=name, data=series))
        return output_data

    @classmethod
    def get_location_opinion_responses(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        top_boundaries = Boundary.get_org_top_level_boundaries_name(org)
        output_data = {time_filter: [] for time_filter in time_filters}
        for osm_id, name in top_boundaries.items():
            responses = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"state:{osm_id.upper()}",
                    flow_result_id__in=flow_result_ids,
                    is_responded=True,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            for time_filter in time_filters:
                series = PollEngagementDailyCount.get_counts_data(responses, time_filter)
                output_data[time_filter].append(dict(name=name, osm_id=osm_id, data=series))
        return output_data

    @classmethod
    def get_age_opinion_responses(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        ages = AgeSegment.objects.all().values("id", "min_age", "max_age")
        output_data = {time_filter: [] for time_filter in time_filters}
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

            responses = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"age:{age['min_age']}",
                    flow_result_id__in=flow_result_ids,
                    is_responded=True,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            for time_filter in time_filters:
                series = PollEngagementDailyCount.get_counts_data(responses, time_filter)
                output_data[time_filter].append(dict(name=data_key, data=series))
        return output_data

    @classmethod
    def get_counts_data(cls, stats_qs, time_filter):
        from ureport.utils import get_time_filter_dates_map

        dates_map = get_time_filter_dates_map(time_filter=time_filter)
        keys = list(set(dates_map.values()))

        responses_data_dict = defaultdict(int)
        for elt in stats_qs:
            key = dates_map.get(str(elt["date"].date()))
            responses_data_dict[key] += elt["count__sum"]

        data = dict()
        for key in keys:
            data[key] = responses_data_dict[key]

        return data

    @classmethod
    def get_all_response_rate_series(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        translation.activate(org.language)

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        polled_stats = list(
            PollEngagementDailyCount.objects.filter(
                org=org, day__gte=start, scope="all", flow_result_id__in=flow_result_ids
            )
            .values(date=Cast("day", output_field=models.DateTimeField()))
            .annotate(Sum("count"))
        )

        responded_stats = list(
            PollEngagementDailyCount.objects.filter(
                org=org, day__gte=start, scope="all", flow_result_id__in=flow_result_ids, is_responded=True
            )
            .values(date=Cast("day", output_field=models.DateTimeField()))
            .annotate(Sum("count"))
        )

        return {
            time_filter: [
                dict(
                    name=str(_("Response Rate")),
                    data=PollEngagementDailyCount.get_response_rate_data(polled_stats, responded_stats, time_filter),
                )
            ]
            for time_filter in time_filters
        }

    @classmethod
    def get_location_response_rate_series(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        top_boundaries = Boundary.get_org_top_level_boundaries_name(org)
        output_data = {time_filter: [] for time_filter in time_filters}
        for osm_id, name in top_boundaries.items():
            polled_stats = list(
                PollEngagementDailyCount.objects.filter(
                    org=org, day__gte=start, scope=f"state:{osm_id.upper()}", flow_result_id__in=flow_result_ids
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            responded_stats = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"state:{osm_id.upper()}",
                    flow_result_id__in=flow_result_ids,
                    is_responded=True,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            for time_filter in time_filters:
                series = PollEngagementDailyCount.get_response_rate_data(polled_stats, responded_stats, time_filter)
                output_data[time_filter].append(dict(name=name, osm_id=osm_id, data=series))
        return output_data

    @classmethod
    def get_scheme_response_rate_series(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        schemes = SchemeSegment.objects.all().values("scheme", "id")
        org_contacts_counts = org.get_org_contacts_counts()
        org_schemes = [k[7:] for k, v in org_contacts_counts.items() if k.startswith("scheme:") if k[7:]]

        output_data = {time_filter: [] for time_filter in time_filters}
        for scheme in schemes:
            if scheme["scheme"] not in org_schemes:
                continue

            name = SchemeSegment.SCHEME_DISPLAY.get(scheme["scheme"], scheme["scheme"].upper())
            if not name:
                continue

            polled_stats = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"scheme:{scheme['scheme'].lower()}",
                    flow_result_id__in=flow_result_ids,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            responded_stats = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"scheme:{scheme['scheme'].lower()}",
                    flow_result_id__in=flow_result_ids,
                    is_responded=True,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            for time_filter in time_filters:
                scheme_rate_series = PollEngagementDailyCount.get_response_rate_data(
                    polled_stats, responded_stats, time_filter
                )
                output_data[time_filter].append(dict(name=name, data=scheme_rate_series))

        return output_data

    @classmethod
    def get_gender_response_rate_series(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )
        org_gender_labels = org.get_gender_labels()

        genders = GenderSegment.objects.all()
        if not org.get_config("common.has_extra_gender"):
            genders = genders.exclude(gender="O")

        genders = genders.values("gender", "id")

        output_data = {time_filter: [] for time_filter in time_filters}
        for gender in genders:
            polled_stats = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"gender:{gender['gender'].lower()}",
                    flow_result_id__in=flow_result_ids,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            responded_stats = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"gender:{gender['gender'].lower()}",
                    flow_result_id__in=flow_result_ids,
                    is_responded=True,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            for time_filter in time_filters:
                gender_rate_series = PollEngagementDailyCount.get_response_rate_data(
                    polled_stats, responded_stats, time_filter
                )
                output_data[time_filter].append(
                    dict(name=org_gender_labels.get(gender["gender"]), data=gender_rate_series)
                )

        return output_data

    @classmethod
    def get_age_response_rate_series(cls, org, time_filters):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        ages = AgeSegment.objects.all().values("id", "min_age", "max_age")
        output_data = {time_filter: [] for time_filter in time_filters}
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

            polled_stats = list(
                PollEngagementDailyCount.objects.filter(
                    org=org, day__gte=start, scope=f"age:{age['min_age']}", flow_result_id__in=flow_result_ids
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            responded_stats = list(
                PollEngagementDailyCount.objects.filter(
                    org=org,
                    day__gte=start,
                    scope=f"age:{age['min_age']}",
                    flow_result_id__in=flow_result_ids,
                    is_responded=True,
                )
                .values(date=Cast("day", output_field=models.DateTimeField()))
                .annotate(Sum("count"))
            )

            for time_filter in time_filters:
                age_rate_series = PollEngagementDailyCount.get_response_rate_data(
                    polled_stats, responded_stats, time_filter
                )
                output_data[time_filter].append(dict(name=data_key, data=age_rate_series))
        return output_data

    @classmethod
    def get_response_rate_data(cls, polled_qs, responded_qs, time_filter):
        from ureport.utils import get_time_filter_dates_map

        dates_map = get_time_filter_dates_map(time_filter=time_filter)
        keys = list(set(dates_map.values()))

        polled_data_dict = defaultdict(int)
        for elt in polled_qs:
            key = dates_map.get(str(elt["date"].date()))
            polled_data_dict[key] += elt["count__sum"]

        responded_data_dict = defaultdict(int)
        for elt in responded_qs:
            key = dates_map.get(str(elt["date"].date()))
            responded_data_dict[key] += elt["count__sum"]

        data = dict()
        for key in keys:
            responded = responded_data_dict.get(key)
            polled = polled_data_dict.get(key)
            if responded is None or polled is None or polled == 0:
                rate = 0
            else:
                rate = round(responded * 100 / polled, 2)
            data[key] = rate

        return data

    class Meta:
        indexes = [
            models.Index(fields=["org", "flow_result"], name="stats_pedc_org_flowresult_idx"),
            models.Index(fields=["org", "day"], name="stats_pedc_org_date_idx"),
            # for squashing task
            models.Index(
                name="stats_pedc_unsquashed",
                fields=("org", "flow_result", "is_responded", "scope", "day"),
                condition=Q(is_squashed=False),
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                name="stats_pedc_squashed",
                fields=("org", "flow_result", "is_responded", "scope", "day"),
                condition=Q(is_squashed=True),
                nulls_distinct=False,
            )
        ]


class ContactActivity(models.Model):
    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="contact_activities")

    contact = models.CharField(max_length=36)

    born = models.IntegerField(null=True)

    gender = models.CharField(max_length=1, null=True)

    state = models.CharField(max_length=255, null=True)

    district = models.CharField(max_length=255, null=True)

    ward = models.CharField(max_length=255, null=True)

    scheme = models.CharField(max_length=16, null=True)

    date = models.DateField(help_text="The starting date for for the month")

    used = models.BooleanField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "contact", "date"], name="stats_contactactivity_org_id_contact_date_348227aa_uniq"
            )
        ]
        indexes = [
            models.Index(fields=["org", "contact"], name="stats_ct_actvt_org_contact_idx"),
            models.Index(fields=["org", "date"], name="stats_ct_actvt_org_date_idx"),
        ]

    def generate_counters(self):
        generated_counters = dict()
        if not self.org_id:
            return generated_counters

        generated_counters[(self.org_id, self.date, "A", "")] = 1

        if self.born:
            generated_counters[(self.org_id, self.date, "B", self.date.year - self.born)] = 1

        if self.gender:
            generated_counters[(self.org_id, self.date, "G", self.gender)] = 1

        if self.state:
            generated_counters[(self.org_id, self.date, "L", self.state)] = 1

        if self.scheme:
            generated_counters[(self.org_id, self.date, "S", self.scheme)] = 1

        return generated_counters

    @classmethod
    def recalculate_contact_activity_counts(cls, org):
        from ureport.utils import chunk_list

        ContactActivityCounter.objects.filter(org_id=org.id).delete()

        all_contacts_activities = ContactActivity.objects.filter(org=org).values_list("id", flat=True).order_by("id")
        start = time.time()
        i = 0

        all_contacts_activities = list(all_contacts_activities)
        all_contacts_activities_count = len(all_contacts_activities)

        counters_dict = defaultdict(int)

        for activity_id_batch in chunk_list(all_contacts_activities, 1000):
            activity_batch = list(activity_id_batch)
            activities = ContactActivity.objects.filter(id__in=activity_batch)
            for activity in activities:
                i += 1
                gen_counters = activity.generate_counters()
                for dict_tuple_key in gen_counters.keys():
                    counters_dict[dict_tuple_key] += gen_counters[dict_tuple_key]

        counters_to_insert = []
        for counter_tuple in counters_dict.keys():
            count = counters_dict[counter_tuple]
            counters_to_insert.append(
                ContactActivityCounter(
                    org_id=counter_tuple[0],
                    date=counter_tuple[1],
                    type=counter_tuple[2],
                    value=counter_tuple[3],
                    count=count,
                )
            )
        ContactActivityCounter.objects.bulk_create(counters_to_insert, batch_size=1000)

        logger.info(
            "Finished Rebuilding the contacts activitiies counters for org #%d in %ds, inserted %d counters objects for %s activities"
            % (org.id, time.time() - start, len(counters_to_insert), all_contacts_activities_count)
        )

        return counters_dict

    @classmethod
    def get_activity_data(cls, activities_qs, time_filter):
        from ureport.utils import get_time_filter_dates_map

        dates_map = get_time_filter_dates_map(time_filter=time_filter)
        keys = list(set(dates_map.values()))

        activity_data = defaultdict(int)
        for elt in activities_qs:
            key = dates_map.get(str(elt["date"]))
            activity_data[key] += elt["count__sum"]

        data = dict()
        for key in keys:
            data_key = key[:-2] + "01"
            data[key] = activity_data[data_key]

        return dict(data)

    @classmethod
    def get_activity(cls, org, time_filters):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()
        translation.activate(org.language)

        activities = list(
            ContactActivityCounter.objects.filter(
                org=org, type=ContactActivityCounter.TYPE_ALL, date__lte=today, date__gte=start
            )
            .values("date")
            .annotate(Sum("count"))
        )
        return {
            time_filter: [
                dict(name=str(_("Active Users")), data=ContactActivity.get_activity_data(activities, time_filter))
            ]
            for time_filter in time_filters
        }

    @classmethod
    def get_activity_age(cls, org, time_filters):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()

        ages = AgeSegment.objects.all().values("id", "min_age", "max_age")
        output_data = {time_filter: [] for time_filter in time_filters}
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

            activities = list(
                ContactActivityCounter.objects.filter(
                    org=org, type=ContactActivityCounter.TYPE_AGE, date__lte=today, date__gte=start
                )
                .annotate(age=Cast("value", output_field=IntegerField()))
                .filter(age__gte=age["min_age"], age__lte=age["max_age"])
                .values("date")
                .annotate(Sum("count"))
            )
            for time_filter in time_filters:
                series = ContactActivity.get_activity_data(activities, time_filter)
                output_data[time_filter].append(dict(name=data_key, data=series))
        return output_data

    @classmethod
    def get_activity_gender(cls, org, time_filters):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()
        org_gender_labels = org.get_gender_labels()

        genders = GenderSegment.objects.all()
        if not org.get_config("common.has_extra_gender"):
            genders = genders.exclude(gender="O")

        genders = genders.values("gender", "id")

        output_data = {time_filter: [] for time_filter in time_filters}
        for gender in genders:
            activities = list(
                ContactActivityCounter.objects.filter(
                    org=org,
                    type=ContactActivityCounter.TYPE_GENDER,
                    date__lte=today,
                    date__gte=start,
                    value__iexact=gender["gender"],
                )
                .values("date")
                .annotate(Sum("count"))
            )
            for time_filter in time_filters:
                series = ContactActivity.get_activity_data(activities, time_filter)
                output_data[time_filter].append(dict(name=org_gender_labels.get(gender["gender"]), data=series))

        return output_data

    @classmethod
    def get_contact_activity_location(cls, org, time_filters):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()

        top_boundaries = Boundary.get_org_top_level_boundaries_name(org)
        output_data = {time_filter: [] for time_filter in time_filters}
        for osm_id, name in top_boundaries.items():
            activities = list(
                ContactActivityCounter.objects.filter(
                    org=org,
                    type=ContactActivityCounter.TYPE_LOCATION,
                    date__lte=today,
                    date__gte=start,
                    value__iexact=osm_id,
                )
                .values("date")
                .annotate(Sum("count"))
            )
            for time_filter in time_filters:
                series = ContactActivity.get_activity_data(activities, time_filter)
                output_data[time_filter].append(dict(name=name, osm_id=osm_id, data=series))
        return output_data

    @classmethod
    def get_contact_activity_scheme(cls, org, time_filters):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()

        org_contacts_counts = org.get_org_contacts_counts()
        schemes = [k[7:] for k, v in org_contacts_counts.items() if k.startswith("scheme:") if k[7:]]

        output_data = {time_filter: [] for time_filter in time_filters}
        for scheme in schemes:
            name = SchemeSegment.SCHEME_DISPLAY.get(scheme, scheme.upper())
            if not name:
                continue

            activities = list(
                ContactActivityCounter.objects.filter(
                    org=org,
                    type=ContactActivityCounter.TYPE_SCHEME,
                    date__lte=today,
                    date__gte=start,
                    value__iexact=scheme,
                )
                .values("date")
                .annotate(Sum("count"))
            )
            for time_filter in time_filters:
                series = ContactActivity.get_activity_data(activities, time_filter)
                output_data[time_filter].append(dict(name=name, data=series))

        return output_data


class ContactActivityCounter(SquashableModel):
    TYPE_ALL = "A"
    TYPE_AGE = "B"
    TYPE_GENDER = "G"
    TYPE_LOCATION = "L"
    TYPE_SCHEME = "S"

    TYPE_CHOICES = (
        (TYPE_ALL, "All"),
        (TYPE_AGE, "Age"),
        (TYPE_GENDER, "Gender"),
        (TYPE_LOCATION, "Location"),
        (TYPE_SCHEME, "Scheme"),
    )

    squash_over = ("org_id", "date", "type", "value")

    org = models.ForeignKey(Org, on_delete=models.PROTECT)

    date = models.DateField(help_text="The starting date for for the month")

    type = models.CharField(
        max_length=1,
        choices=TYPE_CHOICES,
        help_text="The type of alert the counter segment",
    )

    value = models.CharField(max_length=255)

    count = models.IntegerField(default=0, help_text="Number of items with this counter")

    @classmethod
    def get_squash_query(cls, distinct_set):
        """
        Adds the set's unsquashed rows onto its single squashed row, updated in place, which never goes below zero and
        is deleted when it reaches zero. A set without a squashed row only gets one if its deltas sum above zero.
        Whether it has one is read from the statement's snapshot, so if a recalculation of the org's counters deletes
        it after that, a negative total can be inserted in its place - that recalculation is already lossy when it
        overlaps the triggers writing deltas, and is corrected by the next one
        """
        sql = """
        WITH removed AS (
            DELETE FROM %(table)s WHERE NOT "is_squashed" AND %(cond)s RETURNING "count"
        ), zeroed AS (
            DELETE FROM %(table)s WHERE "is_squashed" AND %(cond)s
            AND "count" + (SELECT SUM(r."count") FROM removed r) <= 0 RETURNING "id"
        )
        INSERT INTO %(table)s AS t ("org_id", "date", "type", "value", "count", "is_squashed")
        SELECT %%s, %%s, %%s, %%s, s.total, TRUE FROM (SELECT SUM("count") AS "total" FROM removed) s
        WHERE s.total != 0 AND NOT EXISTS (SELECT 1 FROM zeroed)
        AND (s.total > 0 OR EXISTS (SELECT 1 FROM %(table)s WHERE "is_squashed" AND %(cond)s))
        ON CONFLICT ("org_id", "date", "type", "value") WHERE "is_squashed"
        DO UPDATE SET "count" = t."count" + EXCLUDED."count";
        """ % {
            "table": cls._meta.db_table,
            "cond": '"org_id" = %s AND "date" = %s AND "type" = %s AND "value" = %s',
        }

        return sql, (distinct_set.org_id, distinct_set.date, distinct_set.type, distinct_set.value) * 4

    class Meta:
        indexes = [
            models.Index(name="contact_activitycntr_org_count", fields=["org", "date", "type", "value", "count"]),
        ]
        constraints = [
            models.UniqueConstraint(
                name="stats_cac_squashed", fields=("org", "date", "type", "value"), condition=Q(is_squashed=True)
            )
        ]


class ActiveUsersCheckpoint(models.Model):
    """
    The raw bytes of an active users sketch as of a nightly checkpoint, from which it can be restored - see
    ureport.stats.active_users
    """

    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="active_users_checkpoints")

    key = models.CharField(max_length=255, unique=True)

    month = models.DateField(help_text="The month the sketch counts")

    value = models.BinaryField()

    taken_on = models.DateTimeField()

    watermark = models.BigIntegerField(help_text="The latest poll result id when the checkpoint was taken")

    class Meta:
        indexes = [models.Index(fields=["org", "month"], name="stats_actuserscp_org_month")]


class PollWordCloud(models.Model):
    org = models.ForeignKey(Org, on_delete=models.PROTECT)

    question = models.ForeignKey(PollQuestion, null=True, on_delete=models.SET_NULL)

    flow_result = models.ForeignKey(FlowResult, null=True, on_delete=models.SET_NULL)

    words = JSONField(default=dict)

    @classmethod
    def get_question_poll_cloud(cls, org, question):
        matching_question = PollWordCloud.objects.filter(
            org=org, flow_result_id=question.flow_result_id, question=question
        ).exists()
        if matching_question:
            return PollWordCloud.objects.filter(
                org=org, flow_result_id=question.flow_result_id, question=question
            ).first()
        return PollWordCloud.objects.filter(org=org, flow_result_id=question.flow_result_id).first()
