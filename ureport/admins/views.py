# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from smartmin.views import SmartCRUDL, SmartUpdateView

from django import forms
from django.utils.translation import gettext_lazy as _

from dash.orgs.models import Org
from dash.orgs.views import OrgPermsMixin
from ureport.admins import OrgCache, refresh_caches


class RefreshCacheForm(forms.ModelForm):
    cache = forms.IntegerField(required=True)

    class Meta:
        model = Org
        fields = ("cache",)


class AdminCRUDL(SmartCRUDL):
    actions = ("refresh_cache",)
    model = Org

    class RefreshCache(OrgPermsMixin, SmartUpdateView):
        fields = ("id",)
        success_message = None
        success_url = "@orgs.org_home"
        form_class = RefreshCacheForm

        def post_save(self, obj):
            cache = OrgCache(int(self.request.POST["cache"]))
            refresh_caches(self.get_object(), [cache])
            self.success_message = _("Refreshed %s cache for this organization") % cache.name
