from django.conf.urls import patterns, url
from ureport.api.views import PollList, PollDetails, NewsItemList, NewsItemDetails, VideoList, VideoDetails, ImageList, \
    ImageDetails, OrgList, OrgDetails, StoryList, StoryDetails, TokenCRUDL

__author__ = 'kenneth'

urlpatterns = patterns('',
                       url(r'^orgs/$', OrgList.as_view()),
                       url(r'^orgs/(?P<pk>[\w]+)/$', OrgDetails.as_view()),

                       url(r'^polls/$', PollList.as_view()),
                       url(r'^polls/org/(?P<org>[\w]+)/$', PollList.as_view()),
                       url(r'^polls/(?P<pk>[\w]+)/$', PollDetails.as_view()),

                       url(r'^news-items/$', NewsItemList.as_view()),
                       url(r'^news-items/org/(?P<org>[\w]+)/$', NewsItemList.as_view()),
                       url(r'^news-items/(?P<pk>[\w]+)/$', NewsItemDetails.as_view()),

                       url(r'^videos/$', VideoList.as_view()),
                       url(r'^videos/org/(?P<org>[\w]+)/$', VideoList.as_view()),
                       url(r'^videos/(?P<pk>[\w]+)/$', VideoDetails.as_view()),

                       url(r'^assets/$', ImageList.as_view()),
                       url(r'^assets/org/(?P<org>[\w]+)/$', ImageList.as_view()),
                       url(r'^assets/(?P<pk>[\w]+)/$', ImageDetails.as_view()),

                       url(r'^stories/$', StoryList.as_view()),
                       url(r'^stories/org/(?P<org>[\w]+)/$', StoryList.as_view()),
                       url(r'^stories/(?P<pk>[\w]+)/$', StoryDetails.as_view()),
                       )

urlpatterns += TokenCRUDL().as_urlpatterns()
