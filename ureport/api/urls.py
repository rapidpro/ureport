from django.conf.urls import patterns
from .views import get_flow_info


urlpatterns = patterns('',
    (r'^flow/(?P<poll_id>\d+)/?$', get_flow_info, {}, 'api.flow'),
)
