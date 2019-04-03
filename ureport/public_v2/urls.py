# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf.urls import url

from .views import (
    AboutView,
    AdditionalMenu,
    Count,
    IndexView,
    JobsView,
    JoinEngageView,
    NewsView,
    PollReadView,
    PollsView,
    StoriesView,
    StoryReadView,
    UreportersView,
)

urlpatterns = [
    url(r"^$", IndexView.as_view(), {}, "v2.public.index"),
    url(r"^news/$", NewsView.as_view(), {}, "v2.public.news"),
    url(r"^about/$", AboutView.as_view(), {}, "v2.public.about"),
    url(r"^polls/$", PollsView.as_view(), {}, "v2.public.polls"),
    url(r"^poll/(?P<pk>\d+)/$", PollReadView.as_view(), {}, "v2.public.poll_read"),
    url(r"^ureporters/$", UreportersView.as_view(), {}, "v2.public.ureporters"),
    url(r"^stories/$", StoriesView.as_view(), {}, "v2.public.stories"),
    url(r"^story/(?P<pk>\d+)/$", StoryReadView.as_view(), {}, "v2.public.story_read"),
    url(r"^join/$", JoinEngageView.as_view(), {}, "v2.public.join"),
    url(r"^jobs/$", JobsView.as_view(), {}, "v2.public.jobs"),
    url(r"^added/$", AdditionalMenu.as_view(), {}, "v2.public.added"),
    url(r"^count/$", Count.as_view(), {}, "v2.public.count"),
]
