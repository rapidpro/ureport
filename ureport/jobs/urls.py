from django.conf.urls import patterns
from ureport.jobs.views import JobsView

__author__ = 'awesome'

urlpatterns = patterns('',
                       (r'^$', JobsView.as_view(), {}, 'jobs.index'),
                       )
