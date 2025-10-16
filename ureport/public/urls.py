# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import re_path
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView

from .views import (
    AboutView,
    Bots,
    BoundaryView,
    Count,
    CountriesView,
    CustomPage,
    EngagementDataView,
    IconsDisplay,
    IndexView,
    JobsView,
    JoinEngageView,
    LandingPageView,
    NewsView,
    PollPreview,
    PollQuestionResultsView,
    PollReadView,
    PollRedirectView,
    PollsView,
    ReportersResultsView,
    ReportsView,
    SharedSitesCount,
    StoriesView,
    StoryReadView,
    UreportersView,
    counts_status,
    status,
    task_status,
)

urlpatterns = [
    re_path(r"^$", IndexView.as_view(), {}, "public.index"),
    re_path(r"^news/$", NewsView.as_view(), {}, "public.news"),
    re_path(r"^about/$", AboutView.as_view(), {}, "public.about"),
    re_path(r"^bots/$", Bots.as_view(), {}, "public.bots"),
    re_path(r"^opinions/$", PollsView.as_view(), {}, "public.opinions"),
    re_path(r"^polls/$", RedirectView.as_view(pattern_name="public.opinions"), {}, "public.polls"),
    re_path(r"^opinion/(?P<pk>\d+)/$", PollReadView.as_view(), {}, "public.opinion_read"),
    re_path(r"^preview/(?P<pk>\d+)/$", PollPreview.as_view(), {}, "public.opinion_preview"),
    re_path(r"^poll/(?P<pk>\d+)/$", PollRedirectView.as_view(), {}, "public.poll_read"),
    re_path(r"^contact_field_results/$", ReportersResultsView.as_view(), {}, "public.contact_field_results"),
    re_path(
        r"^pollquestion/(?P<pk>\d+)/results/$",
        csrf_exempt(PollQuestionResultsView.as_view()),
        {},
        "public.pollquestion_results",
    ),
    re_path(r"^boundaries/$", cache_page(60 * 30)(BoundaryView.as_view()), {}, "public.boundaries"),
    re_path(
        r"^boundaries/(?P<osm_id>[\.a-zA-Z0-9_-]+)/$",
        cache_page(60 * 30)(BoundaryView.as_view()),
        {},
        "public.boundaries",
    ),
    re_path(r"^engagement/$", UreportersView.as_view(), {}, "public.engagement"),
    re_path(r"^ureporters/$", RedirectView.as_view(pattern_name="public.engagement"), {}, "public.ureporters"),
    re_path(r"^engagement_data/$", csrf_exempt(EngagementDataView.as_view()), {}, "public.engagement_data"),
    re_path(r"^reports/$", ReportsView.as_view(), {}, "public.reports"),
    re_path(r"^stories/$", StoriesView.as_view(), {}, "public.stories"),
    re_path(r"^story/(?P<pk>\d+)/$", StoryReadView.as_view(), {}, "public.story_read"),
    re_path(r"^join/$", JoinEngageView.as_view(), {}, "public.join"),
    re_path(r"^jobs/$", JobsView.as_view(), {}, "public.jobs"),
    re_path(r"^page/(?P<link>[\w-]+)/$", CustomPage.as_view(), {}, "public.custom_page"),
    re_path(r"^lp/(?P<slug>[\w-]+)/$", LandingPageView.as_view(), {}, "public.landing_page"),
    re_path(r"^count/$", Count.as_view(), {}, "public.count"),
    re_path(
        r"^shared_sites_count/$", cache_page(60 * 10)(SharedSitesCount.as_view()), {}, "public.shared_sites_count"
    ),
    re_path(r"^icons_display/$", IconsDisplay.as_view(), {}, "public.icons_display"),
    re_path(r"^status/$", status, {}, "public.status"),
    re_path(r"^task_status/$", task_status, {}, "public.task_status"),
    re_path(r"^count_status/$", counts_status, {}, "public.counts_status"),
    re_path(r"^countries/$", CountriesView.as_view(), {}, "public.countries"),
]
