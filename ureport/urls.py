# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf import settings
from django.conf.urls import include
# Uncomment the next two lines to enable the admin:
from django.contrib import admin
from django.urls import re_path
from django.views import static
from django.views.generic import RedirectView
from django.views.i18n import JavaScriptCatalog

admin.autodiscover()


urlpatterns = [
    re_path(r"^v2/", include("ureport.public.urls")),
    re_path(r"^v2/manage/", include("ureport.admins.urls")),
    re_path(r"^v2/manage/", include("dash.orgs.urls")),
    re_path(r"^v2/manage/", include("dash.dashblocks.urls")),
    re_path(r"^v2/manage/", include("dash.stories.urls")),
    re_path(r"^v2/manage/", include("ureport.polls.urls")),
    re_path(r"^v2/manage/", include("dash.categories.urls")),
    re_path(r"^v2/manage/", include("ureport.news.urls")),
    re_path(r"^v2/manage/", include("ureport.jobs.urls")),
    re_path(r"^v2/manage/", include("ureport.bots.urls")),
    re_path(r"^v2/manage/", include("ureport.landingpages.urls")),
    re_path(r"^v2/manage/", include("ureport.countries.urls")),
    re_path(r"^v2/manage/", include("ureport.assets.urls")),
    re_path(r"^v2/users/", include("dash.users.urls")),
    re_path(r"^v1/", include("ureport.public.urls")),
    re_path(r"^v1/manage/", include("ureport.admins.urls")),
    re_path(r"^v1/manage/", include("dash.orgs.urls")),
    re_path(r"^v1/manage/", include("dash.dashblocks.urls")),
    re_path(r"^v1/manage/", include("dash.stories.urls")),
    re_path(r"^v1/manage/", include("ureport.polls.urls")),
    re_path(r"^v1/manage/", include("dash.categories.urls")),
    re_path(r"^v1/manage/", include("ureport.news.urls")),
    re_path(r"^v1/manage/", include("ureport.jobs.urls")),
    re_path(r"^v1/manage/", include("ureport.bots.urls")),
    re_path(r"^v1/manage/", include("ureport.landingpages.urls")),
    re_path(r"^v1/manage/", include("ureport.countries.urls")),
    re_path(r"^v1/manage/", include("ureport.assets.urls")),
    re_path(r"^v1/users/", include("dash.users.urls")),
    re_path(r"^", include("ureport.public.urls")),
    re_path(r"^manage/", include("ureport.admins.urls")),
    re_path(r"^manage/", include("dash.orgs.urls")),
    re_path(r"^manage/", include("dash.dashblocks.urls")),
    re_path(r"^manage/", include("dash.stories.urls")),
    re_path(r"^manage/", include("ureport.polls.urls")),
    re_path(r"^manage/", include("dash.categories.urls")),
    re_path(r"^manage/", include("dash.tags.urls")),
    re_path(r"^manage/", include("ureport.news.urls")),
    re_path(r"^manage/", include("ureport.jobs.urls")),
    re_path(r"^manage/", include("ureport.bots.urls")),
    re_path(r"^manage/", include("ureport.landingpages.urls")),
    re_path(r"^manage/", include("ureport.countries.urls")),
    re_path(r"^manage/", include("ureport.assets.urls")),
    re_path(r"^users/", include("dash.users.urls")),
    re_path(r"^api/$", RedirectView.as_view(pattern_name="api.v1.docs", permanent=False), name="api"),
    re_path(r"^api/v1/", include("ureport.api.urls")),
    re_path(r"^jsi18n/$", JavaScriptCatalog.as_view(), name="javascript-catalog"),
]

if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns.append(re_path(r"^__debug__/", include(debug_toolbar.urls)))
    except ImportError:
        pass

    urlpatterns = [
        re_path(r"^media/(?P<path>.*)$", static.serve, {"document_root": settings.MEDIA_ROOT, "show_indexes": True}),
        re_path(r"", include("django.contrib.staticfiles.urls")),
    ] + urlpatterns
