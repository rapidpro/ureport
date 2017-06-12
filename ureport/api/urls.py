from django.conf.urls import url, include
from django.views.generic import RedirectView
from ureport.api.views import PollList, PollDetails, FeaturedPollList, NewsItemList, NewsItemDetails, VideoList
from ureport.api.views import VideoDetails, ImageList, ImageDetails, OrgList, OrgDetails, StoryList, StoryDetails

__author__ = 'kenneth'

urlpatterns = [
    url(r'^$', RedirectView.as_view(pattern_name='django.swagger.base.view', permanent=False)),
    url(r'^docs/', include('rest_framework_swagger.urls')),

    url(r'^orgs/$', OrgList.as_view()),
    url(r'^orgs/(?P<pk>[\w]+)/$', OrgDetails.as_view()),

    url(r'^polls/org/(?P<org>[\w]+)/$', PollList.as_view()),
    url(r'^polls/org/(?P<org>[\w]+)/featured/$', FeaturedPollList.as_view()),
    url(r'^polls/(?P<pk>[\w]+)/$', PollDetails.as_view()),

    url(r'^news/org/(?P<org>[\w]+)/$', NewsItemList.as_view()),
    url(r'^news/(?P<pk>[\w]+)/$', NewsItemDetails.as_view()),

    url(r'^videos/org/(?P<org>[\w]+)/$', VideoList.as_view()),
    url(r'^videos/(?P<pk>[\w]+)/$', VideoDetails.as_view()),

    url(r'^assets/org/(?P<org>[\w]+)/$', ImageList.as_view()),
    url(r'^assets/(?P<pk>[\w]+)/$', ImageDetails.as_view()),

    url(r'^stories/org/(?P<org>[\w]+)/$', StoryList.as_view()),
    url(r'^stories/(?P<pk>[\w]+)/$', StoryDetails.as_view()),
]
