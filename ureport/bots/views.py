from django import forms
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView
from ureport.bots.models import Bot


class BotForm(forms.ModelForm):
    is_active = forms.BooleanField(required=False, help_text=_("Whether this bot should be shown to the public"))

    class Meta:
        model = Bot
        fields = (
            "is_active",
            "featured",
            "landing_page_only",
            "title",
            "channel",
            "keyword",
            "facebook_deeplink",
            "telegram_deeplink",
            "viber_deeplink",
            "whatsapp_deeplink",
            "description",
            "priority",
        )


class BotCRUDL(SmartCRUDL):
    model = Bot
    actions = ("create", "list", "update")

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = BotForm
        fields = (
            "featured",
            "landing_page_only",
            "title",
            "channel",
            "keyword",
            "facebook_deeplink",
            "telegram_deeplink",
            "viber_deeplink",
            "whatsapp_deeplink",
            "description",
            "priority",
        )

        def pre_save(self, obj):
            obj = super(BotCRUDL.Create, self).pre_save(obj)
            org = self.request.org
            obj.org = org

            return obj

    class List(OrgPermsMixin, SmartListView):
        fields = ("title", "featured", "channel", "keyword", "priority")

        def get_queryset(self, **kwargs):
            queryset = super(BotCRUDL.List, self).get_queryset(**kwargs)
            queryset = queryset.filter(org=self.derive_org()).order_by(Lower("title"))

            return queryset

    class Update(OrgObjPermsMixin, SmartUpdateView):
        form_class = BotForm
        fields = (
            "is_active",
            "featured",
            "landing_page_only",
            "title",
            "channel",
            "keyword",
            "facebook_deeplink",
            "telegram_deeplink",
            "viber_deeplink",
            "whatsapp_deeplink",
            "description",
            "priority",
        )
