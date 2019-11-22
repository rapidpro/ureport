# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import calendar
import json
import operator
from functools import reduce

import six
from dash.categories.models import Category
from dash.dashblocks.models import DashBlock, DashBlockType
from dash.orgs.models import Org
from dash.stories.models import Story
from smartmin.views import SmartReadView, SmartTemplateView

from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils import translation
from django.utils.translation import ugettext_lazy as _
from django.views.generic.base import RedirectView

from ureport.jobs.models import JobSource
from ureport.locations.models import Boundary
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll, PollQuestion
from ureport.stats.models import PollStats
from ureport.utils import get_global_count


class IndexView(SmartTemplateView):
    template_name = "v2/public/index.html"

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org

        latest_poll = Poll.get_main_poll(org)
        context["latest_poll"] = latest_poll
        if context["latest_poll"]:
            context["trending_words"] = latest_poll.get_trending_words()

        brick_poll_ids = Poll.get_brick_polls_ids(org)
        context["recent_polls"] = Poll.objects.filter(id__in=brick_poll_ids).order_by("-created_on")

        context["stories"] = Story.objects.filter(org=org, is_active=True, featured=True).order_by("-created_on")

        videos = Video.objects.filter(is_active=True, org=org).order_by("-created_on")
        context["videos"] = videos

        news = NewsItem.objects.filter(is_active=True, org=org).order_by("-created_on")
        context["news"] = news.count() > 0

        context["most_active_regions"] = org.get_regions_stats()

        # global counters
        context["global_contact_count"] = get_global_count()
        context["global_org_count"] = len(settings.COUNTRY_FLAGS_SITES) - 1  # remove Nigeria24x7

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = json.loads(org.get_age_stats())
        context["reporters"] = org.get_reporters_count()
        context["feat_images"] = range(10)

        # fake photos, generated from stories that are featured and have a photo
        context["stories_photos"] = (
            Story.objects.filter(org=org, featured=True, is_active=True)
            .exclude(images=None)
            .order_by("-created_on")[4:]
        )

        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")

        return context


class Count(SmartTemplateView):
    template_name = "v2/public/count"

    def get_context_data(self, **kwargs):
        context = super(Count, self).get_context_data()

        org = self.request.org
        context["org"] = org
        context["count"] = org.get_reporters_count()
        return context


class NewsView(SmartTemplateView):
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


class CustomPage(SmartReadView):
    template_name = "v2/public/custom_page.html"
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


class AboutView(SmartTemplateView):
    template_name = "v2/public/about.html"

    def get_context_data(self, **kwargs):
        context = super(AboutView, self).get_context_data(**kwargs)
        org = self.request.org

        context["org"] = org

        videos = Video.objects.filter(is_active=True, org=org).order_by("-created_on")
        context["videos"] = videos

        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        return context


class PollContextMixin(object):
    def derive_main_poll(self):
        org = self.request.org
        return Poll.get_main_poll(org)

    def get_context_data(self, **kwargs):
        context = super(PollContextMixin, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = org.get_age_stats()

        context["states"] = sorted(
            [dict(id=k, name=v) for k, v in Boundary.get_org_top_level_boundaries_name(org).items()],
            key=lambda c: c["name"],
        )

        main_poll = self.derive_main_poll()
        context["latest_poll"] = main_poll

        if main_poll:
            top_question = main_poll.get_questions().first()
            context["top_question"] = top_question

            if top_question:
                gender_stats = top_question.get_gender_stats()
                total_gender = 0
                for elt in gender_stats:
                    total_gender += elt["set"]
                gender_stats_dict = {
                    elt["label"].lower(): dict(
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

        context["categories"] = (
            Category.objects.filter(org=org, is_active=True)
            .prefetch_related(Prefetch("polls", queryset=Poll.objects.filter(is_active=True).order_by("-poll_date")))
            .order_by("name")
        )
        context["polls"] = Poll.get_public_polls(org=org).order_by("-poll_date")

        context["related_stories"] = []
        if main_poll:
            related_stories = Story.objects.filter(org=org, is_active=True, category=main_poll.category)
            related_stories = related_stories.order_by("-featured", "-created_on")
            context["related_stories"] = related_stories

        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        return context


class PollsView(PollContextMixin, SmartTemplateView):
    template_name = "v2/public/polls.html"

    def get_context_data(self, **kwargs):
        context = super(PollsView, self).get_context_data(**kwargs)
        context["tab"] = "list"
        return context


class PollReadView(PollContextMixin, SmartReadView):
    template_name = "v2/public/polls.html"
    model = Poll

    def derive_queryset(self):
        queryset = super(PollReadView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True, has_synced=True)
        return queryset

    def derive_main_poll(self):
        return self.get_object()


class PollRedirectView(RedirectView):
    def get_redirect_url(*args, **kwargs):
        return reverse("v2.public.opinion_read", args=[kwargs["pk"]])


class StoriesView(SmartTemplateView):
    template_name = "v2/public/stories.html"

    def get_context_data(self, **kwargs):
        context = super(StoriesView, self).get_context_data(**kwargs)

        org = self.request.org

        context["org"] = org
        context["categories"] = (
            Category.objects.filter(org=org, is_active=True)
            .prefetch_related(
                Prefetch("story_set", queryset=Story.objects.filter(is_active=True).order_by("-created_on"))
            )
            .order_by("name")
        )
        context["stories"] = Story.objects.filter(org=org, is_active=True).order_by("title")

        context["featured"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        context["other_stories"] = Story.objects.filter(org=org, featured=False, is_active=True).order_by(
            "-created_on"
        )
        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")

        return context


class StoryReadView(SmartReadView):
    template_name = "v2/public/story_read.html"
    model = Story

    def derive_queryset(self):
        queryset = super(StoryReadView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super(StoryReadView, self).get_context_data(**kwargs)

        org = self.request.org

        story = self.get_object()
        story_category = story.category

        context["org"] = org
        context["categories"] = Category.objects.filter(org=org, is_active=True).order_by("name")
        context["other_stories"] = Story.objects.filter(org=org, featured=False, is_active=True).order_by(
            "-created_on"
        )

        related_polls = Poll.objects.filter(
            org=org, is_active=True, has_synced=True, category=story_category
        ).order_by("-created_on")
        context["related_polls"] = related_polls

        related_stories = Story.objects.filter(
            org=org, is_active=True, category=story_category, featured=True
        ).exclude(pk=story.pk)
        related_stories = related_stories.order_by("-created_on")
        context["related_stories"] = related_stories

        context["story_featured_images"] = story.get_featured_images()
        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        return context


class ReportersResultsView(SmartReadView):
    model = Org

    def get_object(self):
        return self.request.org

    def render_to_response(self, context, **kwargs):
        output_data = []
        segment = self.request.GET.get("segment", None)
        if segment:
            segment = json.loads(segment)
            output_data = self.get_object().get_ureporters_locations_stats(segment)

        return HttpResponse(json.dumps(output_data))


class EngagementDataView(SmartReadView):
    model = Org

    def get_object(self):
        return self.request.org

    def render_to_response(self, context, **kwargs):
        output_data = []

        results_params = self.request.GET.get("results_params", None)
        if results_params:
            results_params = json.loads(results_params)
            metric = results_params.get("metric")
            segment_slug = results_params.get("segment")
            time_filter = int(results_params.get("filter", "12"))

            output_data = PollStats.get_engagement_data(self.get_object(), metric, segment_slug, time_filter)

        return HttpResponse(json.dumps(output_data))


class UreportersView(SmartTemplateView):
    template_name = "v2/public/ureporters.html"

    def get_context_data(self, **kwargs):
        context = super(UreportersView, self).get_context_data(**kwargs)

        org = self.request.org
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
        context["occupation_stats"] = org.get_occupation_stats()
        context["reporters"] = org.get_reporters_count()
        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")

        # global counter
        context["global_counter"] = get_global_count()
        context["average_response_rate"] = PollStats.get_average_response_rate(org)

        context["data_time_filters"] = [
            dict(time_filter_number=key, label=str(val)) for key, val in PollStats.DATA_TIME_FILTERS.items()
        ]

        backend_options = org.backends.filter(is_active=True).values_list("slug", flat=True)
        show_maps = reduce(
            operator.or_, [bool(org.get_config("%s.state_label" % option)) for option in backend_options], False
        )

        context["data_segments"] = [
            dict(segment_type=key, label=str(val))
            for key, val in PollStats.DATA_SEGMENTS.items()
            if key != "location" or show_maps
        ]

        context["data_metrics"] = [dict(slug=key, title=str(val)) for key, val in PollStats.DATA_METRICS.items()]

        return context


class JoinEngageView(SmartTemplateView):
    template_name = "v2/public/join_engage.html"

    def get_context_data(self, **kwargs):
        context = super(JoinEngageView, self).get_context_data(**kwargs)
        org = self.request.org
        context["org"] = org
        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        return context


class JobsView(SmartTemplateView):
    template_name = "v2/public/jobs.html"

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
        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        return context


class BoundaryView(SmartTemplateView):
    def render_to_response(self, context, **kwargs):
        org = self.request.org

        if org.get_config("common.is_global"):
            location_boundaries = org.boundaries.filter(level=0)
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


class PollQuestionResultsView(SmartReadView):
    model = PollQuestion

    def derive_queryset(self):
        queryset = super(PollQuestionResultsView, self).derive_queryset()
        queryset = queryset.filter(poll__org=self.request.org, is_active=True)
        return queryset

    def render_to_response(self, context, **kwargs):
        segment = self.request.GET.get("segment", None)
        if segment:
            segment = json.loads(segment)

        results = self.object.get_results(segment=segment)

        return HttpResponse(json.dumps(results))
