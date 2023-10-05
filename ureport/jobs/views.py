# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.utils.translation import gettext_lazy as _

from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView
from ureport.jobs.models import JobSource


class JobSourceCRUDL(SmartCRUDL):
    model = JobSource
    actions = ("create", "list", "update")

    class Create(OrgPermsMixin, SmartCreateView):
        success_url = "@jobs.jobsource_list"
        success_message = _("Your job source has been added successfully")

        def derive_fields(self):
            source_type = self.request.GET.get("source_type", None)
            if source_type:
                source_type = source_type.strip().upper()

            if source_type == JobSource.TWITTER:
                return ("is_featured", "title", "source_url", "widget_id")

            elif source_type in [JobSource.FACEBOOK, JobSource.RSS]:
                return ("is_featured", "title", "source_url")

            return ("source_type",)

        def pre_save(self, obj):
            obj = super(JobSourceCRUDL.Create, self).pre_save(obj)
            obj.org = self.request.org

            source_type = self.request.GET.get("source_type")
            obj.source_type = source_type.strip().upper()

            return obj

    class Update(OrgObjPermsMixin, SmartUpdateView):
        success_url = "@jobs.jobsource_list"
        success_message = _("Your job source has been updated successfully")

        def derive_fields(self):
            if self.get_object().source_type == JobSource.TWITTER:
                return ("is_active", "is_featured", "title", "source_url", "widget_id")
            return ("is_active", "is_featured", "title", "source_url")

        def pre_save(self, obj):
            obj = super(JobSourceCRUDL.Update, self).pre_save(obj)
            obj.org = self.request.org
            return obj

        def post_save(self, obj):
            obj = super(JobSourceCRUDL.Update, self).post_save(obj)
            obj.get_feed(True)
            return obj

    class List(OrgPermsMixin, SmartListView):
        fields = ("title", "source_type", "source_url", "modified_on")
        default_order = ("-created_on", "id")

        def get_queryset(self):
            queryset = super(JobSourceCRUDL.List, self).get_queryset().filter(org=self.request.org)
            return queryset
