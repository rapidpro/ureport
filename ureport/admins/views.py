# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import *

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

        def post_save(self, obj):
            cache = OrgCache(int(self.request.POST['cache']))
            refresh_caches(self.get_object(), [cache])
            self.success_message = _("Refreshed %s cache for this organization") % cache.name