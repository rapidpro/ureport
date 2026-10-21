# -*- coding: utf-8 -*-

import re

from django import forms
from django.utils.translation import gettext_lazy as _

from dash.dashblocks.models import DashBlock
from dash.dashblocks.views import DashBlockCRUDL as BaseDashBlockCRUDL, DashBlockForm
from dash.orgs.models import Org
from dash.orgs.views import OrgPermsMixin
from smartmin.views import SmartCRUDL, SmartUpdateView
from ureport.admins import OrgCache, refresh_caches

CUSTOM_PAGE_BLOCK_TYPE = "additional_menu"


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


class CustomPageDashBlockForm(DashBlockForm):
    """
    Custom pages are served at page/<link>/, so their link must be a non-empty slug that is unique within the org
    """

    def __init__(self, *args, **kwargs):
        self.org = kwargs.pop("org")
        self.block_type = kwargs.pop("block_type", None)

        super().__init__(*args, **kwargs)

    def get_block_type(self):
        if self.block_type:
            return self.block_type
        if self.cleaned_data.get("dashblock_type"):
            return self.cleaned_data["dashblock_type"]
        if self.instance.dashblock_type_id:
            return self.instance.dashblock_type
        return None

    def clean(self):
        cleaned_data = super().clean()

        block_type = self.get_block_type()
        if "link" not in self.fields or not block_type or block_type.slug != CUSTOM_PAGE_BLOCK_TYPE:
            return cleaned_data

        link = cleaned_data.get("link")
        if not link:
            self.add_error("link", self.fields["link"].error_messages["required"])
        elif not re.fullmatch(r"[\w-]+", link):
            self.add_error("link", _("The link can only contain letters, numbers, underscores and hyphens"))
        else:
            others = DashBlock.objects.filter(org=self.org, dashblock_type__slug=CUSTOM_PAGE_BLOCK_TYPE, link=link)
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                self.add_error("link", _("Another page already uses this link"))

        return cleaned_data


class DashBlockCRUDL(BaseDashBlockCRUDL):
    # keep dash's URL names and templates
    module_name = "dashblocks"

    class Update(BaseDashBlockCRUDL.Update):
        form_class = CustomPageDashBlockForm

        def get_form_kwargs(self):
            kwargs = super().get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs

    class Create(BaseDashBlockCRUDL.Create):
        form_class = CustomPageDashBlockForm

        def get_form_kwargs(self):
            kwargs = super().get_form_kwargs()
            kwargs["org"] = self.request.org
            kwargs["block_type"] = self.get_type()
            return kwargs
