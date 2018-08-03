# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView

from ureport.assets.models import Image


class ImageCRUDL(SmartCRUDL):
    model = Image
    actions = ("create", "update", "list")

    class Update(OrgObjPermsMixin, SmartUpdateView):
        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("is_active", "org", "name", "image_type", "image")
            return ("is_active", "name", "image_type", "image")

    class List(OrgPermsMixin, SmartListView):
        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("org", "name", "image_type")
            return ("name", "image_type")

        def get_background_type(self, obj):
            return obj.get_background_type_display()

        def get_queryset(self, **kwargs):
            queryset = super(ImageCRUDL.List, self).get_queryset(**kwargs)

            if not self.get_user().is_superuser:
                queryset = queryset.filter(org=self.derive_org())

            return queryset

    class Create(OrgPermsMixin, SmartCreateView):
        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("org", "name", "image_type", "image")
            return ("name", "image_type", "image")

        def pre_save(self, obj):
            obj = super(ImageCRUDL.Create, self).pre_save(obj)

            if not self.get_user().is_superuser:
                org = self.derive_org()
                if org:
                    obj.org = org

            return obj
