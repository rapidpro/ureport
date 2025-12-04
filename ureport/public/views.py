# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import calendar
import json
import operator
from collections import defaultdict
from datetime import timedelta
from functools import reduce

import pycountry
import six
from django_valkey import get_valkey_connection

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import RedirectView

from dash.categories.models import Category
from dash.dashblocks.models import DashBlock, DashBlockType
from dash.orgs.models import Org, TaskState
from dash.orgs.views import OrgObjPermsMixin
from dash.stories.models import Story, StoryImage
from smartmin.views import SmartReadView, SmartTemplateView
from ureport.assets.models import Image
from ureport.bots.models import Bot
from ureport.countries.models import CountryAlias
from ureport.jobs.models import JobSource
from ureport.landingpages.models import LandingPage
from ureport.locations.models import Boundary
from ureport.news.models import NewsItem
from ureport.polls.models import Poll, PollQuestion
from ureport.stats.models import GenderSegment, PollEngagementDailyCount, PollStatsCounter
from ureport.utils import (
    get_global_count,
    get_shared_countries_number,
    get_shared_global_count,
    get_shared_sites_count,
)


class RedirectConfigMixin(object):
    def has_permission(self, request, *args, **kwargs):
        org = request.org
        redirect_site_url = org.get_config("redirect_site_url", "").strip()
        if redirect_site_url:
            return request.user.is_authenticated and (org in request.user.get_user_orgs() or request.user.is_superuser)
        return super(RedirectConfigMixin, self).has_permission(request, *args, **kwargs)


class IndexView(SmartTemplateView):
    template_name = "public/index.html"

    def pre_process(self, request, *args, **kwargs):
        org = request.org
        redirect_site_url = org.get_config("redirect_site_url", "").strip()
        if redirect_site_url and not request.user.is_authenticated:
            return HttpResponse(status=302, headers={"Location": redirect_site_url})

        return super().pre_process(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org

        latest_poll = Poll.get_main_poll(org)
        context["latest_poll"] = latest_poll

        cache_value = cache.get("shared_sites", None)
        if not cache_value:
            get_shared_sites_count()

        # global counters
        context["global_contact_count"] = get_shared_global_count()
        context["global_org_count"] = get_shared_countries_number()

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = json.loads(org.get_age_stats())
        context["reporters"] = org.get_reporters_count()

        context["featured_bots"] = Bot.objects.filter(is_active=True, org=org, featured=True).order_by("-priority")

        context["main_stories"] = Story.get_main_stories(org, 5)

        return context


class Count(SmartTemplateView):
    template_name = "public/count"

    def get_context_data(self, **kwargs):
        context = super(Count, self).get_context_data()

        org = self.request.org
        context["org"] = org
        context["count"] = org.get_reporters_count()
        return context


class IconsDisplay(SmartTemplateView):
    template_name = "public/icons.html"

    def has_permission(self, request, *args, **kwargs):
        return request.user.is_authenticated

    def get_context_data(self, **kwargs):
        context = super(IconsDisplay, self).get_context_data(**kwargs)

        linked_sites = list(getattr(settings, "COUNTRY_FLAGS_SITES", []))
        icon_sites = []
        for elt in linked_sites:
            if elt.get("show_icon", True) and elt.get("flag", ""):
                icon_sites.append(elt)

        context["icon_sites"] = icon_sites
        return context


class SharedSitesCount(SmartTemplateView):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(SharedSitesCount, self).dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        global_count = get_global_count()
        linked_sites = list(getattr(settings, "COUNTRY_FLAGS_SITES", []))

        for elt in linked_sites:
            if (
                elt.get("show_icon", True)
                and elt.get("flag", "")
                and not elt["flag"].startswith("https://ureport.in/sitestatic/img/site_flags/")
            ):
                elt["flag"] = f'https://ureport.in/sitestatic/img/site_flags/{elt["flag"]}'

        unique_countries = set()
        for elt in linked_sites:
            unique_countries.update(elt.get("country_codes", []))
        countries_count = len(unique_countries)

        json_dict = dict(global_count=global_count, linked_sites=linked_sites, countries_count=countries_count)

        return HttpResponse(json.dumps(json_dict), status=200, content_type="application/json")


class NewsView(RedirectConfigMixin, SmartTemplateView):
    def render_to_response(self, context, **kwargs):
        org = self.request.org

        news_items = NewsItem.objects.filter(is_active=True, org=org).order_by("-created_on")
        paginator = Paginator(news_items, 3)

        page = self.request.GET.get("page")
        try:
            news_page = paginator.page(page)
        except PageNotAnInteger:
            news_page = paginator.page(1)
        except EmptyPage:
            news_page = None

        news = []
        next_page = False
        if news_page:
            next_page = news_page.has_next()
            for elt in news_page.object_list:
                news.append(elt.as_brick_json())

        output_json = dict(news=news, next=next_page)
        return HttpResponse(json.dumps(output_json))


class CustomPage(RedirectConfigMixin, SmartReadView):
    template_name = "public/custom_page.html"
    model = DashBlock
    slug_url_kwarg = "link"

    def derive_queryset(self):
        org = self.request.org
        try:
            dashblock_type = DashBlockType.objects.get(slug="additional_menu")
        except DashBlockType.DoesNotExist:
            return DashBlock.objects.none()

        queryset = DashBlock.objects.filter(dashblock_type=dashblock_type, org=org, is_active=True)
        queryset = queryset.order_by("-priority")

        return queryset


class LandingPageView(RedirectConfigMixin, SmartReadView):
    template_name = "public/landing_page.html"
    model = LandingPage
    slug_url_kwarg = "slug"

    def derive_queryset(self):
        org = self.request.org

        queryset = LandingPage.objects.filter(org=org, is_active=True).prefetch_related(
            Prefetch("bots", queryset=Bot.objects.filter(is_active=True).order_by("-priority"))
        )

        return queryset


class AboutView(RedirectConfigMixin, SmartTemplateView):
    template_name = "public/about.html"

    def get_context_data(self, **kwargs):
        context = super(AboutView, self).get_context_data(**kwargs)
        org = self.request.org

        context["org"] = org

        partners_logos = Image.objects.filter(org=org, is_active=True, image_type="A").order_by("-priority")
        context["partners_logos"] = partners_logos

        context["main_stories"] = Story.get_main_stories(org, 5)
        return context


class PollContextMixin(object):
    def derive_main_poll(self):
        org = self.request.org
        return Poll.get_main_poll(org)

    def get_context_data(self, **kwargs):
        context = super(PollContextMixin, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org
        translation.activate(org.language)

        context["states"] = sorted(
            [dict(id=k, name=v) for k, v in Boundary.get_org_top_level_boundaries_name(org).items()],
            key=lambda c: c["name"],
        )

        main_poll = self.derive_main_poll()
        context["latest_poll"] = main_poll

        if main_poll:
            top_question = main_poll.get_top_question()
            context["top_question"] = top_question

            if top_question:
                gender_stats = top_question.get_gender_stats()
                total_gender = 0
                for elt in gender_stats:
                    total_gender += elt["set"]

                gender_label_dict = {str(v.lower()): k.lower() for k, v in GenderSegment.GENDERS.items()}
                gender_stats_dict = {
                    gender_label_dict.get(elt["label"].lower()): dict(
                        count=elt["set"], percentage=int(round(elt["set"] * 100 / float(total_gender)))
                    )
                    for elt in gender_stats
                    if total_gender
                }

                context["gender_stats"] = gender_stats_dict

                age_stats = top_question.get_age_stats()
                total_age = 0
                for elt in age_stats:
                    total_age += elt["set"]

                context["age_stats"] = [
                    dict(name=elt["label"], y=int(round(elt["set"] * 100 / float(total_age))))
                    for elt in age_stats
                    if total_age
                ]
                context["locations_stats"] = top_question.get_location_stats()

        if not main_poll or not main_poll.get_questions():
            context["gender_stats"] = org.get_gender_stats()
            context["age_stats"] = org.get_age_stats()

        polls = Poll.get_public_polls(org=org).order_by("-poll_date")

        categories_dict = defaultdict(list)
        date_categories_dict = defaultdict(list)
        for poll in polls:
            month_key = poll.poll_date.date().replace(day=1)
            date_categories_dict[month_key].append(poll)

            categories_dict[poll.category.name].append(poll)

        context["categories"] = sorted(
            [dict(name=k, polls=v) for k, v in categories_dict.items()], key=lambda c: c["name"]
        )

        context["categories_by_date"] = [dict(name=k, polls=v) for k, v in date_categories_dict.items()]

        context["polls"] = polls

        context["main_stories"] = Story.get_main_stories(org, 5)
        return context


class PollsView(RedirectConfigMixin, PollContextMixin, SmartTemplateView):
    template_name = "public/polls.html"

    def get_context_data(self, **kwargs):
        context = super(PollsView, self).get_context_data(**kwargs)
        context["tab"] = "list"
        return context


class PollReadView(RedirectConfigMixin, PollContextMixin, SmartReadView):
    template_name = "public/polls.html"
    model = Poll

    def derive_queryset(self):
        queryset = super(PollReadView, self).derive_queryset()
        queryset = Poll.get_public_polls(self.request.org)
        return queryset

    def derive_main_poll(self):
        return self.get_object()


class PollPreview(RedirectConfigMixin, OrgObjPermsMixin, PollContextMixin, SmartReadView):
    template_name = "public/polls.html"
    model = Poll
    permission = "polls.poll_read"

    def get_context_data(self, **kwargs):
        context = super(PollPreview, self).get_context_data(**kwargs)
        context["poll_preview"] = True
        return context

    def derive_queryset(self):
        queryset = super(PollPreview, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True)
        return queryset

    def derive_main_poll(self):
        return self.get_object()


class PollRedirectView(RedirectView):
    def get_redirect_url(*args, **kwargs):
        return reverse("public.opinion_read", args=[kwargs["pk"]])


class StoriesView(RedirectConfigMixin, SmartTemplateView):
    template_name = "public/stories.html"

    def get_context_data(self, **kwargs):
        context = super(StoriesView, self).get_context_data(**kwargs)

        org = self.request.org

        context["org"] = org
        context["categories"] = (
            Category.objects.filter(org=org, is_active=True)
            .prefetch_related(
                Prefetch(
                    "story_set",
                    queryset=Story.objects.filter(is_active=True)
                    .filter(Q(attachment="") | Q(attachment=None))
                    .prefetch_related(
                        Prefetch(
                            "images",
                            queryset=StoryImage.objects.filter(is_active=True)
                            .exclude(image="")
                            .only("is_active", "image", "story_id"),
                            to_attr="prefetched_images",
                        )
                    )
                    .order_by("-created_on"),
                )
            )
            .order_by("name")
        )
        context["stories"] = (
            Story.objects.filter(org=org, is_active=True)
            .filter(Q(attachment="") | Q(attachment=None))
            .order_by("title")
        )

        featured_stories = Story.get_main_stories(org, 5)
        context["main_stories"] = featured_stories

        return context


class ReportsView(RedirectConfigMixin, SmartTemplateView):
    template_name = "public/reports.html"

    def get_context_data(self, **kwargs):
        context = super(ReportsView, self).get_context_data(**kwargs)

        org = self.request.org

        context["org"] = org
        context["categories"] = (
            Category.objects.filter(org=org, is_active=True)
            .prefetch_related(
                Prefetch(
                    "story_set",
                    queryset=Story.objects.filter(is_active=True)
                    .prefetch_related(
                        Prefetch(
                            "images",
                            queryset=StoryImage.objects.filter(is_active=True)
                            .exclude(image="")
                            .only("is_active", "image", "story_id"),
                            to_attr="prefetched_images",
                        )
                    )
                    .exclude(Q(attachment="") | Q(attachment=None))
                    .order_by("-created_on"),
                )
            )
            .order_by("name")
        )
        context["stories"] = (
            Story.objects.filter(org=org, is_active=True)
            .exclude(Q(attachment="") | Q(attachment=None))
            .order_by("-created_on")
        )

        return context


class StoryReadView(RedirectConfigMixin, SmartReadView):
    template_name = "public/story_read.html"
    model = Story

    def derive_queryset(self):
        queryset = super(StoryReadView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True).prefetch_related(
            Prefetch(
                "images",
                queryset=StoryImage.objects.filter(is_active=True)
                .exclude(image="")
                .only("is_active", "story_id", "image"),
                to_attr="prefetched_images",
            )
        )
        return queryset

    def get_context_data(self, **kwargs):
        context = super(StoryReadView, self).get_context_data(**kwargs)

        org = self.request.org

        context["org"] = org
        context["categories"] = Category.objects.filter(org=org, is_active=True).order_by("name")

        context["main_stories"] = Story.get_main_stories(org, 5)
        return context


class ReportersResultsView(RedirectConfigMixin, SmartReadView):
    model = Org
    http_method_names = ["get"]

    def get_object(self):
        return self.request.org

    def render_to_response(self, context, **kwargs):
        output_data = []
        try:
            segment = self.request.GET.get("segment", None)
            if segment:
                segment = json.loads(segment)
                output_data = self.get_object().get_ureporters_locations_stats(segment)
        except json.JSONDecodeError:
            output_data = []
            pass
        except Exception as e:
            output_data = []
            raise e

        return HttpResponse(json.dumps(output_data))


class EngagementDataView(RedirectConfigMixin, SmartReadView):
    model = Org
    http_method_names = ["get"]

    def get_object(self):
        return self.request.org

    def render_to_response(self, context, **kwargs):
        output_data = []

        try:
            results_params = self.request.GET.get("results_params", None)
            if results_params:
                results_params = json.loads(results_params)
                metric = results_params.get("metric")
                segment_slug = results_params.get("segment")
                time_filter = int(results_params.get("filter", "12"))

                output_data = PollEngagementDailyCount.get_engagement_data(
                    self.get_object(), metric, segment_slug, time_filter
                )
        except json.JSONDecodeError:
            output_data = []
            pass
        except Exception as e:
            output_data = []
            raise e

        return HttpResponse(json.dumps(output_data))


class UreportersView(RedirectConfigMixin, SmartTemplateView):
    template_name = "public/ureporters.html"
    http_method_names = ["get"]

    def get_context_data(self, **kwargs):
        context = super(UreportersView, self).get_context_data(**kwargs)

        org = self.request.org
        user = self.request.user
        context["org"] = org
        translation.activate(org.language)

        # remove the first option '' from calender.month_abbr
        context["months"] = [six.text_type(_("%s")) % m for m in calendar.month_abbr][1:]

        context["states"] = sorted(
            [dict(id=k, name=v) for k, v in Boundary.get_org_top_level_boundaries_name(org).items()],
            key=lambda c: c["name"],
        )

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = json.loads(org.get_age_stats())
        context["registration_stats"] = org.get_registration_stats()

        scheme_stats = org.get_schemes_stats()
        context["scheme_bar_height"] = (50 * len(scheme_stats)) + 30
        context["schemes_stats"] = scheme_stats
        context["reporters"] = org.get_reporters_count()
        context["main_stories"] = Story.get_main_stories(org, 5)

        # global counter
        context["global_counter"] = get_global_count()
        context["average_response_rate"] = PollStatsCounter.get_average_response_rate(org)

        context["data_time_filters"] = [
            dict(time_filter_number=key, label=str(val))
            for key, val in PollEngagementDailyCount.DATA_TIME_FILTERS.items()
        ]

        backend_options = org.backends.filter(is_active=True).values_list("slug", flat=True)
        show_maps = reduce(
            operator.or_, [bool(org.get_config("%s.state_label" % option)) for option in backend_options], False
        )

        context["data_segments"] = [
            dict(segment_type=key, label=str(val))
            for key, val in PollEngagementDailyCount.DATA_SEGMENTS.items()
            if (key != "location" or show_maps)
        ]

        context["data_metrics"] = [
            dict(slug=key, title=str(val)) for key, val in PollEngagementDailyCount.DATA_METRICS.items()
        ]

        context["hide_charts_breakdown"] = org.get_config("common.has_charts_hidden", False) and not (
            (user.is_authenticated and org in user.get_user_orgs()) or user.is_superuser
        )

        return context


class JoinEngageView(RedirectConfigMixin, SmartTemplateView):
    template_name = "public/join_engage.html"

    def get_context_data(self, **kwargs):
        context = super(JoinEngageView, self).get_context_data(**kwargs)
        org = self.request.org
        context["org"] = org
        context["main_stories"] = Story.get_main_stories(org, 5)
        return context


class Bots(RedirectConfigMixin, SmartTemplateView):
    template_name = "public/bots.html"

    def get_context_data(self, **kwargs):
        context = super(Bots, self).get_context_data(**kwargs)
        org = self.request.org
        context["org"] = org
        context["bots"] = Bot.objects.filter(org=org, is_active=True, landing_page_only=False).order_by("-priority")
        return context


class JobsView(RedirectConfigMixin, SmartTemplateView):
    template_name = "public/jobs.html"

    def pre_process(self, *args, **kwargs):
        org = self.request.org
        if not org.get_config("has_jobs"):
            raise Http404("Page not found")
        return None

    def get_context_data(self, **kwargs):
        context = super(JobsView, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = self.request.org
        context["job_sources"] = JobSource.objects.filter(org=org, is_active=True).order_by(
            "-is_featured", "-created_on"
        )
        context["main_stories"] = Story.get_main_stories(org, 5)
        return context


class BoundaryView(RedirectConfigMixin, SmartTemplateView):
    def render_to_response(self, context, **kwargs):
        org = self.request.org

        if org.get_config("common.is_global"):
            location_boundaries = org.boundaries.filter(level=0)
            limit_states = org.get_config("common.limit_states")
            if limit_states:
                limit_states = [elt.strip() for elt in limit_states.split(",")]
                location_boundaries = location_boundaries.filter(osm_id__in=limit_states)

        else:
            osm_id = self.kwargs.get("osm_id", None)

            org_boundaries = org.boundaries.all()

            limit_states = org.get_config("common.limit_states")
            if limit_states:
                limit_states = [elt.strip() for elt in limit_states.split(",")]
                org_boundaries = org_boundaries.filter(
                    Q(level=1, name__in=limit_states)
                    | Q(parent__name__in=limit_states, level=2)
                    | Q(parent__parent__name__in=limit_states, level=3)
                )

            if osm_id:
                location_boundaries = org_boundaries.filter(parent__osm_id=osm_id)
            else:
                location_boundaries = org_boundaries.filter(level=1)

        boundaries = dict(
            type="FeatureCollection",
            features=[elt.as_geojson() for elt in location_boundaries if elt.geometry and json.loads(elt.geometry)],
        )

        return HttpResponse(json.dumps(boundaries))


class PollQuestionResultsView(RedirectConfigMixin, SmartReadView):
    model = PollQuestion

    def derive_queryset(self):
        queryset = super(PollQuestionResultsView, self).derive_queryset()
        queryset = queryset.filter(poll__org=self.request.org, is_active=True)
        return queryset

    def render_to_response(self, context, **kwargs):
        results = []
        try:
            segment = self.request.GET.get("segment", None)
            if segment:
                segment = json.loads(segment)

            results = self.object.get_results(segment=segment)
        except json.JSONDecodeError:
            results = []
            pass
        except Exception as e:
            results = []
            raise e

        return HttpResponse(json.dumps(results))


class CountriesView(SmartTemplateView):
    template_name = "public/countries.html"

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super(CountriesView, self).dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        json_dict = dict(exists="invalid")

        whole_text = request.GET.get("text", "")
        text = CountryAlias.normalize_name(whole_text)

        text_length = len(text)

        country = None
        if text_length == 2:
            try:
                country = pycountry.countries.get(alpha_2=text.upper())
            except KeyError:
                pass

        elif text_length == 3:
            try:
                country = pycountry.countries.get(alpha_3=text.upper())
            except KeyError:
                pass

        if not country:
            try:
                country = pycountry.countries.get(name=text.title())
            except KeyError:
                pass

        country_code = None
        if not country:
            country = CountryAlias.is_valid(text)
            if country:
                country_code = country.code

        if country and country_code:
            json_dict = dict(exists="valid", country_code=country_code)
        elif country:
            json_dict = dict(exists="valid", country_code=country.alpha_2)
        else:
            json_dict["text"] = whole_text

        return HttpResponse(json.dumps(json_dict), status=200, content_type="application/json")


def status(request):
    """
    Meant to be a very lightweight view that checks our connectivity to both our database
    and valkey. This is hit by ELB to determine whether an instance is healthy.
    """
    # check our db
    org = Org.objects.all().first()
    db_up = org is not None

    # check valkey
    r = get_valkey_connection()
    r.set("ping", "pong")
    pong = r.get("ping")
    valkey_up = pong == b"pong"

    body = json.dumps(dict(db_up=db_up, valkey_up=valkey_up))

    if not db_up or not valkey_up:
        return HttpResponse(body, status=500, content_type="application/json")
    else:
        return HttpResponse(body, status=200, content_type="application/json")


def task_status(request):
    two_hour_ago = timezone.now() - timedelta(hours=2)

    active_states = (
        TaskState.objects.filter(is_disabled=False)
        .exclude(org__is_active=False)
        .exclude(org__domain__in=["beta", "test"])
    )

    active_contact_pull_states = active_states.filter(task_key="contact-pull")
    failing_contact_pull_states = active_contact_pull_states.exclude(last_successfully_started_on__gte=two_hour_ago)

    contact_sync_up = not failing_contact_pull_states.exists()

    all_tasks = dict()
    failing_tasks = dict()

    for obj in active_states:
        all_tasks[f"{obj.org.name} - {obj.task_key}"] = f"{obj.last_successfully_started_on}"
        if obj in failing_contact_pull_states:
            failing_tasks[f"{obj.org.name} - {obj.task_key}"] = f"{obj.last_successfully_started_on}"

    body = json.dumps(
        dict(contact_sync_up=contact_sync_up, tasks=all_tasks, failing_tasks=failing_tasks), sort_keys=True
    )

    if not contact_sync_up:
        return HttpResponse(body, status=500, content_type="application/json")
    else:
        return HttpResponse(body, status=200, content_type="application/json")


def counts_status(request):
    cached_counts_stats = cache.get("contact_counts_status", dict())

    has_error = cached_counts_stats.get("error_counts", dict())

    body = json.dumps(cached_counts_stats)

    if has_error:
        return HttpResponse(body, status=500, content_type="application/json")
    else:
        return HttpResponse(body, status=200, content_type="application/json")
