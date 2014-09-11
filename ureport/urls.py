from django.conf.urls import patterns, include, url
from django.contrib.auth.decorators import permission_required, login_required
from django.conf import settings

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r'^', include('ureport.public.urls')),
    url(r'^manage/', include('dash.orgs.urls')),
    url(r'^manage/', include('dash.dashblocks.urls')),
    url(r'^manage/', include('dash.stories.urls')),
    url(r'^manage/', include('ureport.polls.urls')),
    url(r'^manage/', include('ureport.categories.urls')),
    url(r'^manage/', include('ureport.news.urls')),
    url(r'^users/', include('dash.users.urls')),
)

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = patterns('',
    url(r'^__debug__/', include(debug_toolbar.urls)),
    url(r'^media/(?P<path>.*)$', 'django.views.static.serve',
        {'document_root': settings.MEDIA_ROOT, 'show_indexes': True}),
    url(r'', include('django.contrib.staticfiles.urls')),
) + urlpatterns
