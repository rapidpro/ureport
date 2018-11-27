# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf.urls import url

from .views import (
    AboutView,
    AdditionalMenu,
    BoundaryView,
    Chooser,
    Count,
    CountriesView,
    IndexView,
    JobsView,
    JoinEngageView,
    NewsView,
    PollQuestionResultsView,
    PollReadView,
    PollsView,
    ReportersResultsView,
    StoriesView,
    StoryReadView,
    UreportersView,
    PolicyView,
)

urlpatterns = [
    url(r"^home/$", Chooser.as_view(), {}, "public.home"),
    url(r"^$", IndexView.as_view(), {}, "public.index"),
    url(r"^news/$", NewsView.as_view(), {}, "public.news"),
    url(r"^about/$", AboutView.as_view(), {}, "public.about"),
    url(r"^polls/$", PollsView.as_view(), {}, "public.polls"),
    url(r"^poll/(?P<pk>\d+)/$", PollReadView.as_view(), {}, "public.poll_read"),
    url(r"^pollquestion/(?P<pk>\d+)/results/$", PollQuestionResultsView.as_view(), {}, "public.pollquestion_results"),
    url(r"^contact_field_results/$", ReportersResultsView.as_view(), {}, "public.contact_field_results"),
    url(r"^boundaries/$", BoundaryView.as_view(), {}, "public.boundaries"),
    url(r"^boundaries/(?P<osm_id>[a-zA-Z0-9]+)/$", BoundaryView.as_view(), {}, "public.boundaries"),
    url(r"^ureporters/$", UreportersView.as_view(), {}, "public.ureporters"),
    url(r"^stories/$", StoriesView.as_view(), {}, "public.stories"),
    url(r"^story/(?P<pk>\d+)/$", StoryReadView.as_view(), {}, "public.story_read"),
    url(r"^join/$", JoinEngageView.as_view(), {}, "public.join"),
    url(r"^jobs/$", JobsView.as_view(), {}, "public.jobs"),
    url(r"^countries/$", CountriesView.as_view(), {}, "public.countries"),
    url(r"^added/$", AdditionalMenu.as_view(), {}, "public.added"),
    url(r"^count/$", Count.as_view(), {}, "public.count"),
    url(r"^policies/(?P<policy_type>[a-zA-Z]+)/$", PolicyView.as_view(), {}, "public.policies"),
]
