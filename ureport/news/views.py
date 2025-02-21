# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django import forms

from dash.categories.fields import CategoryChoiceField
from dash.categories.models import Category
from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView

from .models import NewsItem, Video


class NewsForm(forms.ModelForm):
    category = CategoryChoiceField(Category.objects.none())

    def __init__(self, *args, **kwargs):
        self.org = kwargs["org"]
        del kwargs["org"]

        super(NewsForm, self).__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(org=self.org).order_by("name")

    class Meta:
        model = NewsItem
        fields = ("is_active", "title", "description", "link", "category", "org")


class VideoForm(forms.ModelForm):
    category = CategoryChoiceField(Category.objects.none())

    def __init__(self, *args, **kwargs):
        self.org = kwargs["org"]
        del kwargs["org"]

        super(VideoForm, self).__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(org=self.org).order_by("name")

    class Meta:
        model = Video
        fields = ("is_active", "title", "description", "video_id", "category", "org")


class NewsItemCRUDL(SmartCRUDL):
    model = NewsItem
    actions = ("create", "update", "list")

    class Update(OrgObjPermsMixin, SmartUpdateView):
        form_class = NewsForm
        fields = ("is_active", "title", "description", "link", "category")

        def get_form_kwargs(self):
            kwargs = super(NewsItemCRUDL.Update, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs

    class List(OrgPermsMixin, SmartListView):
        fields = ("title", "link", "category")
        ordering = ("-pk",)

        def get_queryset(self, **kwargs):
            queryset = super(NewsItemCRUDL.List, self).get_queryset(**kwargs)

            queryset = queryset.filter(org=self.derive_org())

            return queryset

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = NewsForm

        def get_form_kwargs(self):
            kwargs = super(NewsItemCRUDL.Create, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("title", "description", "link", "category", "org")
            return ("title", "description", "link", "category")

        def pre_save(self, obj):
            obj = super(NewsItemCRUDL.Create, self).pre_save(obj)

            org = self.derive_org()
            if org:
                obj.org = org

            return obj


class VideoCRUDL(SmartCRUDL):
    model = Video
    actions = ("create", "update", "list")

    class Update(OrgObjPermsMixin, SmartUpdateView):
        form_class = VideoForm
        fields = ("is_active", "title", "description", "video_id", "category")

        def get_form_kwargs(self):
            kwargs = super(VideoCRUDL.Update, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs

    class List(OrgPermsMixin, SmartListView):
        fields = ("title", "video_id", "category")
        ordering = ("-pk",)

        def get_queryset(self, **kwargs):
            queryset = super(VideoCRUDL.List, self).get_queryset(**kwargs)

            queryset = queryset.filter(org=self.derive_org())

            return queryset

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = VideoForm

        def get_form_kwargs(self):
            kwargs = super(VideoCRUDL.Create, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("title", "description", "video_id", "category", "org")
            return ("title", "description", "video_id", "category")

        def pre_save(self, obj):
            obj = super(VideoCRUDL.Create, self).pre_save(obj)

            org = self.derive_org()
            if org:
                obj.org = org

            return obj
