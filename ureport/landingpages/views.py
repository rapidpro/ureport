from django import forms
from django.db.models.functions import Lower
from django.utils.translation import ugettext_lazy as _

from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView
from ureport.landingpages.models import LandingPage


class LandingPageForm(forms.ModelForm):
    is_active = forms.BooleanField(required=False, help_text=_("Whether this page should be active to the public"))

    class Meta:
        model = LandingPage
        fields = (
            "is_active",
            "title",
            "slug",
            "content",
            "image",
        )


class LandingPageCRUDL(SmartCRUDL):
    model = LandingPage
    actions = ("create", "list", "update")

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = LandingPageForm
        fields = (
            "title",
            "slug",
            "content",
            "image",
        )

        def pre_save(self, obj):
            obj = super(LandingPageCRUDL.Create, self).pre_save(obj)
            org = self.request.org
            obj.org = org

            return obj

    class List(OrgPermsMixin, SmartListView):
        fields = (
            "title",
            "slug",
        )

        def get_queryset(self, **kwargs):
            queryset = super(LandingPageCRUDL.List, self).get_queryset(**kwargs)
            queryset = queryset.filter(org=self.derive_org()).order_by(Lower("title"))

            return queryset

    class Update(OrgObjPermsMixin, SmartUpdateView):
        form_class = LandingPageForm
        fields = (
            "is_active",
            "title",
            "slug",
            "content",
            "image",
        )
