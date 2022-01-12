from django import forms
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView
from ureport.bots.models import Bot
from ureport.landingpages.models import LandingPage


class LandingPageForm(forms.ModelForm):
    is_active = forms.BooleanField(required=False, help_text=_("Whether this page should be active to the public"))

    def __init__(self, *args, **kwargs):
        self.org = kwargs["org"]
        del kwargs["org"]

        super(LandingPageForm, self).__init__(*args, **kwargs)
        self.fields["bots"].queryset = Bot.objects.filter(org=self.org)

    class Meta:
        model = LandingPage
        fields = ("is_active", "title", "slug", "action_text", "content", "image", "bots")


class LandingPageCRUDL(SmartCRUDL):
    model = LandingPage
    actions = ("create", "list", "update")

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = LandingPageForm
        fields = (
            "title",
            "slug",
            "action_text",
            "content",
            "image",
            "bots",
        )

        def pre_save(self, obj):
            obj = super(LandingPageCRUDL.Create, self).pre_save(obj)
            org = self.request.org
            obj.org = org

            return obj

        def get_form_kwargs(self):
            kwargs = super(LandingPageCRUDL.Create, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs

    class List(OrgPermsMixin, SmartListView):
        fields = (
            "title",
            "slug",
            "public_page",
        )

        def get_public_page(self, obj):
            if obj.is_active:
                return mark_safe(
                    f'<a href="{reverse("public.landing_page", args=[obj.slug])}" target="_blank" rel="noopener noreferrer" class="button  is-inline-block is-info">View public page</a>'
                )
            else:
                return "Deactivated page"

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
            "action_text",
            "content",
            "image",
            "bots",
        )

        def get_form_kwargs(self):
            kwargs = super(LandingPageCRUDL.Update, self).get_form_kwargs()
            kwargs["org"] = self.request.org
            return kwargs
