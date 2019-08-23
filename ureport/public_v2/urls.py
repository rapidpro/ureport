# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf.urls import url

from .views import (
    AboutView,
    Count,
    CustomPage,
    EngagementDataView,
    IndexView,
    JobsView,
    JoinEngageView,
    NewsView,
    PollReadView,
    PollsView,
    ReportersResultsView,
    StoriesView,
    StoryReadView,
    UreportersView,
)

urlpatterns = [
    url(r"^$", IndexView.as_view(), {}, "v2.public.index"),
    url(r"^news/$", NewsView.as_view(), {}, "v2.public.news"),
    url(r"^about/$", AboutView.as_view(), {}, "v2.public.about"),
    url(r"^opinions/$", PollsView.as_view(), {}, "v2.public.opinions"),
    url(r"^opinion/(?P<pk>\d+)/$", PollReadView.as_view(), {}, "v2.public.opinion_read"),
    url(r"^contact_field_results/$", ReportersResultsView.as_view(), {}, "v2.public.contact_field_results"),
    url(r"^ureporters/$", UreportersView.as_view(), {}, "v2.public.ureporters"),
    url(r"^engagement_data/$", EngagementDataView.as_view(), {}, "v2.public.engagement_data"),
    url(r"^stories/$", StoriesView.as_view(), {}, "v2.public.stories"),
    url(r"^story/(?P<pk>\d+)/$", StoryReadView.as_view(), {}, "v2.public.story_read"),
    url(r"^join/$", JoinEngageView.as_view(), {}, "v2.public.join"),
    url(r"^jobs/$", JobsView.as_view(), {}, "v2.public.jobs"),
    url(r"^page/(?P<link>\w+)/$", CustomPage.as_view(), {}, "v2.public.custom_page"),
    url(r"^count/$", Count.as_view(), {}, "v2.public.count"),
]
