import logging
import time
from collections import defaultdict
from datetime import timedelta

from django.core.cache import cache
from django.db import connection, models
from django.db.models import Count, ExpressionWrapper, F, IntegerField, JSONField, Q, Sum
from django.db.models.functions import ExtractYear
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from dash.orgs.models import Org
from ureport.flows.models import FlowResult, FlowResultCategory
from ureport.locations.models import Boundary
from ureport.polls.models import PollQuestion, PollResponseCategory

logger = logging.getLogger(__name__)


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

    SCHEME_DISPLAY = {"tel": "SMS", "twitterid": "TWITTER", "ext": None}

    scheme = models.CharField(max_length=16, unique=True)


class PollStats(models.Model):
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

    id = models.BigAutoField(auto_created=True, primary_key=True, verbose_name="ID")

    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="poll_stats")

    question = models.ForeignKey(PollQuestion, null=True, on_delete=models.SET_NULL)

    flow_result = models.ForeignKey(FlowResult, null=True, on_delete=models.SET_NULL)

    category = models.ForeignKey(PollResponseCategory, null=True, on_delete=models.SET_NULL)

    flow_result_category = models.ForeignKey(FlowResultCategory, null=True, on_delete=models.SET_NULL)

    age_segment = models.ForeignKey(AgeSegment, null=True, on_delete=models.SET_NULL)

    gender_segment = models.ForeignKey(GenderSegment, null=True, on_delete=models.SET_NULL)

    scheme_segment = models.ForeignKey(SchemeSegment, null=True, on_delete=models.SET_NULL)

    location = models.ForeignKey(Boundary, null=True, on_delete=models.SET_NULL)

    date = models.DateTimeField(null=True)

    count = models.IntegerField(default=0, help_text=_("Number of items with this counter"))

    is_squashed = models.BooleanField(null=True, help_text=_("Whether this row was created by squashing"))

    @classmethod
    def squash(cls):
        start = time.time()
        num_sets = 0

        stats_objs = (
            cls.objects.exclude(is_squashed=True)
            .exclude(date=None)
            .order_by(
                "org_id",
                "question_id",
                "flow_result_id",
                "category_id",
                "flow_result_category_id",
                "age_segment_id",
                "gender_segment_id",
                "scheme_segment_id",
                "location_id",
                "date",
            )
            .distinct(
                "org_id",
                "question_id",
                "flow_result_id",
                "category_id",
                "flow_result_category_id",
                "age_segment_id",
                "gender_segment_id",
                "scheme_segment_id",
                "location_id",
                "date",
            )[:50000]
        )

        for distinct_set in stats_objs:
            with connection.cursor() as cursor:

                where_sql = ""
                if distinct_set.org_id is not None:
                    where_sql += '"org_id" = %s AND ' % distinct_set.org_id
                else:
                    where_sql += '"org_id" IS NULL AND'

                if distinct_set.question_id is not None:
                    where_sql += '"question_id" = %s AND' % distinct_set.question_id
                else:
                    where_sql += '"question_id" IS NULL AND'

                if distinct_set.flow_result_id is not None:
                    where_sql += '"flow_result_id" = %s AND' % distinct_set.flow_result_id
                else:
                    where_sql += '"flow_result_id" IS NULL AND'

                if distinct_set.category_id is not None:
                    where_sql += '"category_id" = %s AND' % distinct_set.category_id
                else:
                    where_sql += '"category_id" IS NULL AND'

                if distinct_set.flow_result_category_id is not None:
                    where_sql += '"flow_result_category_id" = %s AND' % distinct_set.flow_result_category_id
                else:
                    where_sql += '"flow_result_category_id" IS NULL AND'

                if distinct_set.age_segment_id is not None:
                    where_sql += '"age_segment_id" = %s AND' % distinct_set.age_segment_id
                else:
                    where_sql += '"age_segment_id" IS NULL AND'

                if distinct_set.gender_segment_id is not None:
                    where_sql += '"gender_segment_id" = %s AND' % distinct_set.gender_segment_id
                else:
                    where_sql += '"gender_segment_id" IS NULL AND'

                if distinct_set.scheme_segment_id is not None:
                    where_sql += '"scheme_segment_id" = %s AND' % distinct_set.scheme_segment_id
                else:
                    where_sql += '"scheme_segment_id" IS NULL AND'

                if distinct_set.location_id is not None:
                    where_sql += '"location_id" = %s AND' % distinct_set.location_id
                else:
                    where_sql += '"location_id" IS NULL AND'

                where_sql += """
                "date" = date_trunc('day', TIMESTAMP '%s')::TIMESTAMP
                """ % str(
                    distinct_set.date
                )

                sql = """
                WITH deleted as (
                  DELETE FROM stats_pollstats WHERE "id" IN (
                    SELECT "id" FROM stats_pollstats
                      WHERE %(where_sql)s
                      LIMIT 10000
                  ) RETURNING "count"
                )
                INSERT INTO stats_pollstats("org_id", "question_id", "flow_result_id", "category_id", "flow_result_category_id", "age_segment_id", "gender_segment_id", "scheme_segment_id", "location_id", "date", "count", "is_squashed")
                VALUES (%%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, %%s, date_trunc('day', TIMESTAMP %%s)::TIMESTAMP, GREATEST(0, (SELECT SUM("count") FROM deleted)), TRUE);
                """ % {
                    "where_sql": where_sql
                }

                params = (
                    distinct_set.org_id,
                    distinct_set.question_id,
                    distinct_set.flow_result_id,
                    distinct_set.category_id,
                    distinct_set.flow_result_category_id,
                    distinct_set.age_segment_id,
                    distinct_set.gender_segment_id,
                    distinct_set.scheme_segment_id,
                    distinct_set.location_id,
                    str(distinct_set.date),
                )

                cursor.execute(sql, params)

            num_sets += 1

        time_taken = time.time() - start

        logger.info("Squashed %d distinct sets of %s in %0.3fs" % (num_sets, cls.__name__, time_taken))

    @classmethod
    def get_question_stats(cls, org_id, question):
        matching_question = PollStats.objects.filter(
            org_id=org_id, flow_result=question.flow_result, question=question
        ).exists()
        if matching_question:
            return PollStats.objects.filter(org_id=org_id, flow_result=question.flow_result, question=question)
        return PollStats.objects.filter(org_id=org_id, flow_result=question.flow_result)

    @classmethod
    def get_engagement_data(cls, org, metric, segment_slug, time_filter):
        key = f"org:{org.id}:metric:{metric}:segment:{segment_slug}:filter:{time_filter}"
        output_data = cache.get(key, None)
        if output_data:
            return output_data["results"]

        return PollStats.refresh_engagement_data(org, metric, segment_slug, time_filter)

    @classmethod
    def refresh_engagement_data(cls, org, metric, segment_slug, time_filter):

        key = f"org:{org.id}:metric:{metric}:segment:{segment_slug}:filter:{time_filter}"

        output_data = []
        if metric == "opinion-responses":
            if segment_slug == "all":
                output_data = PollStats.get_all_opinion_responses(org, time_filter)
            if segment_slug == "age":
                output_data = PollStats.get_age_opinion_responses(org, time_filter)
            if segment_slug == "gender":
                output_data = PollStats.get_gender_opinion_responses(org, time_filter)
            if segment_slug == "location":
                output_data = PollStats.get_location_opinion_responses(org, time_filter)
            if segment_slug == "scheme":
                output_data = PollStats.get_scheme_opinion_responses(org, time_filter)

        if metric == "sign-up-rate":
            if segment_slug == "all":
                output_data = org.get_sign_up_rate(time_filter)
            if segment_slug == "age":
                output_data = org.get_sign_up_rate_age(time_filter)
            if segment_slug == "gender":
                output_data = org.get_sign_up_rate_gender(time_filter)
            if segment_slug == "location":
                output_data = org.get_sign_up_rate_location(time_filter)
            if segment_slug == "scheme":
                output_data = org.get_sign_up_rate_scheme(time_filter)

        if metric == "response-rate":
            if segment_slug == "all":
                output_data = PollStats.get_all_response_rate_series(org, time_filter)
            if segment_slug == "age":
                output_data = PollStats.get_age_response_rate_series(org, time_filter)
            if segment_slug == "gender":
                output_data = PollStats.get_gender_response_rate_series(org, time_filter)
            if segment_slug == "location":
                output_data = PollStats.get_location_response_rate_series(org, time_filter)
            if segment_slug == "scheme":
                output_data = PollStats.get_scheme_response_rate_series(org, time_filter)

        if metric == "active-users":
            if segment_slug == "all":
                output_data = ContactActivity.get_activity(org, time_filter)
            if segment_slug == "age":
                output_data = ContactActivity.get_activity_age(org, time_filter)
            if segment_slug == "gender":
                output_data = ContactActivity.get_activity_gender(org, time_filter)
            if segment_slug == "location":
                output_data = ContactActivity.get_contact_activity_location(org, time_filter)
            if segment_slug == "scheme":
                output_data = ContactActivity.get_contact_activity_scheme(org, time_filter)

        if output_data:
            cache.set(key, {"results": output_data}, None)
        return output_data

    @classmethod
    def get_all_opinion_responses(cls, org, time_filter):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        translation.activate(org.language)

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        responses = (
            PollStats.objects.filter(org=org, date__gte=start, flow_result_id__in=flow_result_ids)
            .exclude(flow_result_category=None)
            .values("date")
            .annotate(Sum("count"))
        )
        return [dict(name=str(_("Opinion Responses")), data=PollStats.get_counts_data(responses, time_filter))]

    @classmethod
    def get_gender_opinion_responses(cls, org, time_filter):
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

        output_data = []
        for gender in genders:
            responses = (
                PollStats.objects.filter(
                    org=org, date__gte=start, gender_segment_id=gender["id"], flow_result_id__in=flow_result_ids
                )
                .exclude(flow_result_category=None)
                .values("date")
                .annotate(Sum("count"))
            )
            series = PollStats.get_counts_data(responses, time_filter)
            output_data.append(dict(name=org_gender_labels.get(gender["gender"]), data=series))
        return output_data

    @classmethod
    def get_scheme_opinion_responses(cls, org, time_filter):
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

        output_data = []
        for scheme in schemes:
            if scheme["scheme"] not in org_schemes:
                continue

            responses = (
                PollStats.objects.filter(
                    org=org, date__gte=start, scheme_segment_id=scheme["id"], flow_result_id__in=flow_result_ids
                )
                .exclude(flow_result_category=None)
                .values("date")
                .annotate(Sum("count"))
            )
            series = PollStats.get_counts_data(responses, time_filter)

            name = SchemeSegment.SCHEME_DISPLAY.get(scheme["scheme"], scheme["scheme"].upper())
            if not name:
                continue
            output_data.append(dict(name=name, data=series))
        return output_data

    @classmethod
    def get_location_opinion_responses(cls, org, time_filter):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        top_boundaries = Boundary.get_org_top_level_boundaries_name(org)
        output_data = []
        for osm_id, name in top_boundaries.items():
            boundary_ids = list(
                Boundary.objects.filter(org=org)
                .filter(Q(osm_id=osm_id) | Q(parent__osm_id=osm_id) | Q(parent__parent__osm_id=osm_id))
                .values_list("pk", flat=True)
            )
            responses = (
                PollStats.objects.filter(
                    org=org, date__gte=start, location_id__in=boundary_ids, flow_result_id__in=flow_result_ids
                )
                .exclude(flow_result_category=None)
                .values("date")
                .annotate(Sum("count"))
            )
            series = PollStats.get_counts_data(responses, time_filter)
            output_data.append(dict(name=name, osm_id=osm_id, data=series))
        return output_data

    @classmethod
    def get_age_opinion_responses(cls, org, time_filter):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

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

            responses = (
                PollStats.objects.filter(
                    org=org, date__gte=start, age_segment_id=age["id"], flow_result_id__in=flow_result_ids
                )
                .exclude(flow_result_category=None)
                .values("date")
                .annotate(Sum("count"))
            )
            series = PollStats.get_counts_data(responses, time_filter)
            output_data.append(dict(name=data_key, data=series))
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
    def get_all_response_rate_series(cls, org, time_filter):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        translation.activate(org.language)

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        polled_stats = (
            PollStats.objects.filter(org=org, date__gte=start, flow_result_id__in=flow_result_ids)
            .values("date")
            .annotate(Sum("count"))
        )
        responded_stats = (
            PollStats.objects.filter(org=org, date__gte=start, flow_result_id__in=flow_result_ids)
            .exclude(flow_result_category=None)
            .values("date")
            .annotate(Sum("count"))
        )

        return [
            dict(
                name=str(_("Response Rate")),
                data=PollStats.get_response_rate_data(polled_stats, responded_stats, time_filter),
            )
        ]

    @classmethod
    def get_location_response_rate_series(cls, org, time_filter):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        top_boundaries = Boundary.get_org_top_level_boundaries_name(org)
        output_data = []
        for osm_id, name in top_boundaries.items():
            boundary_ids = list(
                Boundary.objects.filter(org=org)
                .filter(Q(osm_id=osm_id) | Q(parent__osm_id=osm_id) | Q(parent__parent__osm_id=osm_id))
                .values_list("pk", flat=True)
            )
            polled_stats = (
                PollStats.objects.filter(
                    org=org, date__gte=start, location_id__in=boundary_ids, flow_result_id__in=flow_result_ids
                )
                .values("date")
                .annotate(Sum("count"))
            )
            responded_stats = (
                PollStats.objects.filter(
                    org=org, date__gte=start, location_id__in=boundary_ids, flow_result_id__in=flow_result_ids
                )
                .exclude(flow_result_category=None)
                .values("date")
                .annotate(Sum("count"))
            )
            series = PollStats.get_response_rate_data(polled_stats, responded_stats, time_filter)
            output_data.append(dict(name=name, osm_id=osm_id, data=series))
        return output_data

    @classmethod
    def get_scheme_response_rate_series(cls, org, time_filter):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        schemes = SchemeSegment.objects.all().values("scheme", "id")
        org_contacts_counts = org.get_org_contacts_counts()
        org_schemes = [k[7:] for k, v in org_contacts_counts.items() if k.startswith("scheme:") if k[7:]]

        output_data = []
        for scheme in schemes:
            if scheme["scheme"] not in org_schemes:
                continue

            polled_stats = (
                PollStats.objects.filter(
                    org=org, date__gte=start, scheme_segment_id=scheme["id"], flow_result_id__in=flow_result_ids
                )
                .values("date")
                .annotate(Sum("count"))
            )
            responded_stats = (
                PollStats.objects.filter(
                    org=org, date__gte=start, scheme_segment_id=scheme["id"], flow_result_id__in=flow_result_ids
                )
                .exclude(flow_result_category=None)
                .values("date")
                .annotate(Sum("count"))
            )
            gender_rate_series = PollStats.get_response_rate_data(polled_stats, responded_stats, time_filter)

            name = SchemeSegment.SCHEME_DISPLAY.get(scheme["scheme"], scheme["scheme"].upper())
            if not name:
                continue
            output_data.append(dict(name=name, data=gender_rate_series))

        return output_data

    @classmethod
    def get_gender_response_rate_series(cls, org, time_filter):
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

        output_data = []
        for gender in genders:
            polled_stats = (
                PollStats.objects.filter(
                    org=org, date__gte=start, gender_segment_id=gender["id"], flow_result_id__in=flow_result_ids
                )
                .values("date")
                .annotate(Sum("count"))
            )
            responded_stats = (
                PollStats.objects.filter(
                    org=org, date__gte=start, gender_segment_id=gender["id"], flow_result_id__in=flow_result_ids
                )
                .exclude(flow_result_category=None)
                .values("date")
                .annotate(Sum("count"))
            )
            gender_rate_series = PollStats.get_response_rate_data(polled_stats, responded_stats, time_filter)
            output_data.append(dict(name=org_gender_labels.get(gender["gender"]), data=gender_rate_series))

        return output_data

    @classmethod
    def get_age_response_rate_series(cls, org, time_filter):
        now = timezone.now()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1)
        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

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

            polled_stats = (
                PollStats.objects.filter(
                    org=org, date__gte=start, age_segment_id=age["id"], flow_result_id__in=flow_result_ids
                )
                .values("date")
                .annotate(Sum("count"))
            )
            responded_stats = (
                PollStats.objects.filter(
                    org=org, date__gte=start, age_segment_id=age["id"], flow_result_id__in=flow_result_ids
                )
                .exclude(flow_result_category=None)
                .values("date")
                .annotate(Sum("count"))
            )
            age_rate_series = PollStats.get_response_rate_data(polled_stats, responded_stats, time_filter)
            output_data.append(dict(name=data_key, data=age_rate_series))
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

    @classmethod
    def get_average_response_rate(cls, org):

        key = f"org:{org.id}:average_response_rate"
        output_data = cache.get(key, None)
        if output_data:
            return output_data["results"]

        return PollStats.calculate_average_response_rate(org)

    @classmethod
    def calculate_average_response_rate(cls, org):

        key = f"org:{org.id}:average_response_rate"

        flow_result_ids = list(
            PollQuestion.objects.filter(is_active=True, poll__org_id=org.id).values_list("flow_result_id", flat=True)
        )

        polled_stats = PollStats.objects.filter(org=org, flow_result_id__in=flow_result_ids).aggregate(Sum("count"))
        responded_stats = (
            PollStats.objects.filter(org=org, flow_result_id__in=flow_result_ids)
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


class PollContactResult(models.Model):
    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="poll_contact_results", db_index=False)

    contact = models.CharField(max_length=36)

    flow = models.CharField(max_length=36)

    flow_result = models.ForeignKey(FlowResult, null=True, on_delete=models.SET_NULL)

    flow_result_category = models.ForeignKey(FlowResultCategory, null=True, on_delete=models.SET_NULL)

    text = models.TextField(null=True)

    age_segment = models.ForeignKey(AgeSegment, null=True, on_delete=models.SET_NULL)

    gender_segment = models.ForeignKey(GenderSegment, null=True, on_delete=models.SET_NULL)

    scheme_segment = models.ForeignKey(SchemeSegment, null=True, on_delete=models.SET_NULL)

    location = models.ForeignKey(Boundary, null=True, on_delete=models.SET_NULL)

    date = models.DateTimeField(null=True)

    class Meta:
        indexes = [
            models.Index(name="%(app_label)s_pcr_contact", fields=["contact"]),
            models.Index(name="%(app_label)s_pcr_org_flow_contact", fields=["org", "flow", "contact"]),
            models.Index(name="%(app_label)s_pcr_org_flow", fields=["org", "flow"]),
            models.Index(name="%(app_label)s_pcr_org_flow_result_text", fields=["org", "flow", "flow_result", "text"]),
        ]


class ContactEngagementActivity(models.Model):
    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="contact_engagement_activities")

    contact = models.CharField(max_length=36)

    age_segment = models.ForeignKey(AgeSegment, null=True, on_delete=models.SET_NULL)

    gender_segment = models.ForeignKey(GenderSegment, null=True, on_delete=models.SET_NULL)

    scheme_segment = models.ForeignKey(SchemeSegment, null=True, on_delete=models.SET_NULL)

    location = models.ForeignKey(Boundary, null=True, on_delete=models.SET_NULL)

    date = models.DateField(help_text="The starting date for for the month")

    used = models.BooleanField(null=True)

    class Meta:
        indexes = [
            models.Index(name="%(app_label)s_cea_org_contact", fields=["org", "contact"]),
            models.Index(name="%(app_label)s_cea_org_date", fields=["org", "date"]),
            models.Index(
                name="%(app_label)s_cea_org_date_used", fields=["org", "date", "used"], condition=Q(used=True)
            ),
            models.Index(
                name="%(app_label)s_cea_org_date_state_used",
                fields=["org", "date", "location", "used"],
                condition=Q(location__isnull=False) & Q(used=True),
            ),
            models.Index(
                name="%(app_label)s_cea_org_date_age_used",
                fields=["org", "date", "age_segment", "used"],
                condition=Q(age_segment__isnull=False) & Q(used=True),
            ),
            models.Index(
                name="%(app_label)s_cea_org_date_scheme_used",
                fields=["org", "date", "scheme_segment", "used"],
                condition=Q(scheme_segment__isnull=False) & Q(used=True),
            ),
            models.Index(
                name="%(app_label)s_cea_org_date_gender_used",
                fields=["org", "date", "gender_segment", "used"],
                condition=Q(gender_segment__isnull=False) & Q(used=True),
            ),
        ]
        unique_together = ("org", "contact", "date")


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
        index_together = (("org", "contact"), ("org", "date"))
        unique_together = ("org", "contact", "date")

    @classmethod
    def get_activity_data(cls, activities_qs, time_filter):
        from ureport.utils import get_time_filter_dates_map

        dates_map = get_time_filter_dates_map(time_filter=time_filter)
        keys = list(set(dates_map.values()))

        activity_data = defaultdict(int)
        for elt in activities_qs:
            key = dates_map.get(str(elt["date"]))
            activity_data[key] += elt["id__count"]

        data = dict()
        for key in keys:
            data_key = key[:-2] + "01"
            data[key] = activity_data[data_key]

        return dict(data)

    @classmethod
    def get_activity(cls, org, time_filter):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()
        translation.activate(org.language)

        activities = (
            ContactActivity.objects.filter(org=org, date__lte=today, date__gte=start, used=True)
            .values("date")
            .annotate(Count("id"))
        )
        return [dict(name=str(_("Active Users")), data=ContactActivity.get_activity_data(activities, time_filter))]

    @classmethod
    def get_activity_age(cls, org, time_filter):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()

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

            activities = (
                ContactActivity.objects.filter(org=org, date__lte=today, date__gte=start, used=True)
                .exclude(born=None)
                .exclude(date=None)
                .annotate(year=ExtractYear("date"))
                .annotate(age=ExpressionWrapper(F("year") - F("born"), output_field=IntegerField()))
                .filter(age__gte=age["min_age"], age__lte=age["max_age"])
                .values("date")
                .annotate(Count("id"))
            )
            series = ContactActivity.get_activity_data(activities, time_filter)
            output_data.append(dict(name=data_key, data=series))
        return output_data

    @classmethod
    def get_activity_gender(cls, org, time_filter):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()
        org_gender_labels = org.get_gender_labels()

        genders = GenderSegment.objects.all()
        if not org.get_config("common.has_extra_gender"):
            genders = genders.exclude(gender="O")

        genders = genders.values("gender", "id")

        output_data = []
        for gender in genders:
            activities = (
                ContactActivity.objects.filter(
                    org=org, date__lte=today, date__gte=start, gender=gender["gender"], used=True
                )
                .values("date")
                .annotate(Count("id"))
            )
            series = ContactActivity.get_activity_data(activities, time_filter)
            output_data.append(dict(name=org_gender_labels.get(gender["gender"]), data=series))

        return output_data

    @classmethod
    def get_contact_activity_location(cls, org, time_filter):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()

        top_boundaries = Boundary.get_org_top_level_boundaries_name(org)
        output_data = []
        for osm_id, name in top_boundaries.items():
            activities = (
                ContactActivity.objects.filter(org=org, date__lte=today, date__gte=start, state=osm_id, used=True)
                .values("date")
                .annotate(Count("id"))
            )
            series = ContactActivity.get_activity_data(activities, time_filter)
            output_data.append(dict(name=name, osm_id=osm_id, data=series))
        return output_data

    @classmethod
    def get_contact_activity_scheme(cls, org, time_filter):
        now = timezone.now()
        today = now.date()
        year_ago = now - timedelta(days=365)
        start = year_ago.replace(day=1).date()

        org_contacts_counts = org.get_org_contacts_counts()
        schemes = [k[7:] for k, v in org_contacts_counts.items() if k.startswith("scheme:") if k[7:]]

        output_data = []
        for scheme in schemes:
            activities = (
                ContactActivity.objects.filter(org=org, date__lte=today, date__gte=start, scheme=scheme, used=True)
                .values("date")
                .annotate(Count("id"))
            )
            series = ContactActivity.get_activity_data(activities, time_filter)

            name = SchemeSegment.SCHEME_DISPLAY.get(scheme, scheme.upper())
            if not name:
                continue

            output_data.append(dict(name=name, data=series))

        return output_data


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
