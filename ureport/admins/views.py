from __future__ import absolute_import, unicode_literals

from django.utils.translation import ugettext_lazy as _

from dash.orgs.models import Org
from smartmin.views import SmartCRUDL, SmartUpdateView
from ureport.admins import OrgCache, refresh_caches


class AdminCRUDL(SmartCRUDL):
    actions = ('refresh_cache',)
    model = Org

    class RefreshCache(SmartUpdateView):
        fields = ('id',)
        success_message = None
        success_url = '@orgs.org_home'

        def pre_process(self, request, *args, **kwargs):
            cache = OrgCache(int(request.REQUEST['cache']))
            refresh_caches(self.get_object(), [cache])
            self.success_message = _("Refreshed %s cache for this organization") % cache.name