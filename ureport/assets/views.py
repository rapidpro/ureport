# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db.models.functions import Lower

from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView
from ureport.assets.models import Image


class ImageCRUDL(SmartCRUDL):
    model = Image
    actions = ("create", "update", "list")

    class Update(OrgObjPermsMixin, SmartUpdateView):
        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("is_active", "org", "name", "image_type", "image", "priority")
            return ("is_active", "name", "image", "priority")

        def has_permission(self, request, *args, **kwargs):
            has_perm = super(OrgObjPermsMixin, self).has_permission(request, *args, **kwargs)

            if has_perm:
                if not self.get_user().is_superuser:
                    return self.get_object().image_type == "A"
                return True
            return False

    class List(OrgPermsMixin, SmartListView):
        ordering = ("name",)

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("org", "name", "image_type", "priority")
            return ("name", "priority")

        def get_background_type(self, obj):
            return obj.get_background_type_display()

        def get_queryset(self, **kwargs):
            queryset = super(ImageCRUDL.List, self).get_queryset(**kwargs)

            queryset = queryset.filter(org=self.derive_org())

            if not self.get_user().is_superuser:
                queryset = queryset.filter(image_type="A")

            return queryset.order_by(Lower("org__name"), Lower("name"))

    class Create(OrgPermsMixin, SmartCreateView):
        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("org", "name", "image_type", "image", "priority")
            return ("name", "image", "priority")

        def pre_save(self, obj):
            obj = super(ImageCRUDL.Create, self).pre_save(obj)

            if not self.get_user().is_superuser:
                org = self.derive_org()
                if org:
                    obj.org = org

            return obj
