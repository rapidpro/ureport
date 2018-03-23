# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import *

from django.conf.urls import url, include
from django.views.generic import RedirectView
from ureport.api.views import PollList, PollDetails, FeaturedPollList, NewsItemList, NewsItemDetails, VideoList
from ureport.api.views import VideoDetails, ImageList, ImageDetails, OrgList, OrgDetails, StoryList, StoryDetails
from rest_framework_swagger.views import get_swagger_view

schema_view = get_swagger_view(title='API')


urlpatterns = [
    url(r'^$', RedirectView.as_view(pattern_name='api.v1.docs', permanent=False), name='api.v1'),
    url(r'^docs/',  schema_view, name="api.v1.docs"),

    url(r'^orgs/$', OrgList.as_view(), name="api.v1.org_list"),
    url(r'^orgs/(?P<pk>[\w]+)/$', OrgDetails.as_view(), name="api.v1.org_details"),

    url(r'^polls/org/(?P<org>[\w]+)/$', PollList.as_view(), name="api.v1.org_poll_list"),
    url(r'^polls/org/(?P<org>[\w]+)/featured/$', FeaturedPollList.as_view(), name="api.v1.org_poll_fetured"),
    url(r'^polls/(?P<pk>[\w]+)/$', PollDetails.as_view(), name="api.v1.poll_details"),

    url(r'^news/org/(?P<org>[\w]+)/$', NewsItemList.as_view(), name="api.v1.org_newsitem_list"),
    url(r'^news/(?P<pk>[\w]+)/$', NewsItemDetails.as_view(), name="api.v1.newsitem_details"),

    url(r'^videos/org/(?P<org>[\w]+)/$', VideoList.as_view(), name="api.v1.org_video_list"),
    url(r'^videos/(?P<pk>[\w]+)/$', VideoDetails.as_view(), name="api.v1.video_details"),

    url(r'^assets/org/(?P<org>[\w]+)/$', ImageList.as_view(), name="api.v1.org_asset_list"),
    url(r'^assets/(?P<pk>[\w]+)/$', ImageDetails.as_view(), name="api.v1.asset_details"),

    url(r'^stories/org/(?P<org>[\w]+)/$', StoryList.as_view(), name="api.v1.org_story_list"),
    url(r'^stories/(?P<pk>[\w]+)/$', StoryDetails.as_view(), name="api.v1.story_details"),
]
