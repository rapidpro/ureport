# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import calendar
import json

import pycountry
import six
from dash.categories.models import Category
from dash.orgs.models import Org
from dash.stories.models import Story
from django_redis import get_redis_connection
from smartmin.views import SmartReadView, SmartTemplateView

from django.conf import settings
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponsePermanentRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import RedirectView

from ureport.countries.models import CountryAlias
from ureport.jobs.models import JobSource
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll, PollQuestion
from ureport.utils import get_global_count, get_linked_orgs


class IndexView(SmartTemplateView):
    template_name = "public/index.html"

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

        # global counter
        if org.get_config("common.is_global"):
            context["global_counter"] = get_global_count()

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = org.get_age_stats()
        context["reporters"] = org.get_reporters_count()

        return context


class Count(SmartTemplateView):
    template_name = "public/count"

    def get_context_data(self, **kwargs):
        context = super(Count, self).get_context_data()

        org = self.request.org
        context["org"] = org
        context["count"] = org.get_reporters_count()
        return context


class Chooser(IndexView):
    def pre_process(self, request, *args, **kwargs):
        if not self.request.org:
            org = Org.objects.filter(subdomain="", is_active=True).first()
            if not org:
                linked_sites = get_linked_orgs()
                return TemplateResponse(request, settings.SITE_CHOOSER_TEMPLATE, dict(orgs=linked_sites))
            else:
                return HttpResponsePermanentRedirect("//" + getattr(settings, "HOSTNAME", "locahost"))


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


class AdditionalMenu(SmartTemplateView):
    template_name = "public/additional_menu.haml"

    def get_context_data(self, **kwargs):
        context = super(AdditionalMenu, self).get_context_data(**kwargs)
        org = self.request.org

        context["org"] = org
        return context


class AboutView(SmartTemplateView):
    template_name = "public/about.html"

    def get_context_data(self, **kwargs):
        context = super(AboutView, self).get_context_data(**kwargs)
        org = self.request.org

        context["org"] = org

        videos = Video.objects.filter(is_active=True, org=org).order_by("-created_on")
        context["videos"] = videos

        return context


class PollContextMixin(object):
    def derive_main_poll(self):
        org = self.request.org
        return Poll.get_main_poll(org)

    def get_context_data(self, **kwargs):
        context = super(PollContextMixin, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org

        main_poll = self.derive_main_poll()
        context["latest_poll"] = main_poll

        context["categories"] = Category.objects.filter(org=org, is_active=True).order_by("name")
        context["polls"] = Poll.get_public_polls(org=org).order_by("-poll_date")

        context["related_stories"] = []
        if main_poll:
            related_stories = Story.objects.filter(org=org, is_active=True, category=main_poll.category)
            related_stories = related_stories.order_by("-featured", "-created_on")
            context["related_stories"] = related_stories

        return context


class PollsView(PollContextMixin, SmartTemplateView):
    template_name = "public/polls.html"

    def get_context_data(self, **kwargs):
        context = super(PollsView, self).get_context_data(**kwargs)

        context["tab"] = "list"

        return context


class PollReadView(PollContextMixin, SmartReadView):
    template_name = "public/polls.html"
    model = Poll

    def derive_queryset(self):
        queryset = super(PollReadView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True, has_synced=True)
        return queryset

    def derive_main_poll(self):
        return self.get_object()


class PollRedirectView(RedirectView):
    def get_redirect_url(*args, **kwargs):
        return reverse("v2.public.poll_read", args=[kwargs["pk"]])


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


class StoriesView(SmartTemplateView):
    template_name = "public/stories.html"

    def get_context_data(self, **kwargs):
        context = super(StoriesView, self).get_context_data(**kwargs)

        org = self.request.org

        context["org"] = org
        context["categories"] = Category.objects.filter(org=org, is_active=True).order_by("name")
        context["featured"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        context["other_stories"] = Story.objects.filter(org=org, featured=False, is_active=True).order_by(
            "-created_on"
        )

        return context


class StoryReadView(SmartReadView):
    template_name = "public/story_read.html"
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

        return context


class UreportersView(SmartTemplateView):
    template_name = "public/ureporters.html"

    def get_context_data(self, **kwargs):
        context = super(UreportersView, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org

        # remove the first option '' from calender.month_abbr
        context["months"] = [six.text_type(_("%s")) % m for m in calendar.month_abbr][1:]

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = org.get_age_stats()
        context["registration_stats"] = org.get_registration_stats()
        context["occupation_stats"] = org.get_occupation_stats()
        context["reporters"] = org.get_reporters_count()

        return context


class JoinEngageView(SmartTemplateView):
    template_name = "public/join_engage.html"

    def get_context_data(self, **kwargs):
        context = super(JoinEngageView, self).get_context_data(**kwargs)

        context["org"] = self.request.org
        return context


class JobsView(SmartTemplateView):
    template_name = "public/jobs.html"

    def get_context_data(self, **kwargs):
        context = super(JobsView, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = self.request.org
        context["job_sources"] = JobSource.objects.filter(org=org, is_active=True).order_by(
            "-is_featured", "-created_on"
        )
        return context


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
    and redis. This is hit by ELB to determine whether an instance is healthy.
    """
    # check our db
    org = Org.objects.all().first()
    db_up = org is not None

    # check redis
    r = get_redis_connection()
    r.set("ping", "pong")
    pong = r.get("ping")
    redis_up = pong == b"pong"

    body = json.dumps(dict(db_up=db_up, redis_up=redis_up))

    if not db_up or not redis_up:
        return HttpResponse(body, status=500)
    else:
        return HttpResponse(body, status=200)
