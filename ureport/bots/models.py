from django.db import models
from django.utils.translation import gettext_lazy as _

from dash.orgs.models import Org
from smartmin.models import SmartModel


class Bot(SmartModel):
    org = models.ForeignKey(
        Org, on_delete=models.PROTECT, related_name="bots", help_text=_("The organization this bot is part of")
    )

    featured = models.BooleanField(
        default=False,
        help_text=_(
            "Whether this bot is displayed on the homepage, up to 3 only with the highest priorities are displayed"
        ),
    )

    landing_page_only = models.BooleanField(
        default=False,
        help_text=_("Whether this bot is hidden on public pages except landing pages"),
    )

    title = models.CharField(max_length=128, help_text=_("The title to display for this bot"))

    channel = models.CharField(
        max_length=128, help_text=_("The shortcode, number or bot name of the channel for this bot")
    )

    keyword = models.CharField(max_length=128, help_text=_("The keyword for this bot"))

    facebook_deeplink = models.URLField(null=True, blank=True, help_text=_("The Facebook bot deeplink, optional"))

    telegram_deeplink = models.URLField(null=True, blank=True, help_text=_("The Telegram bot deeplink, optional"))

    viber_deeplink = models.URLField(null=True, blank=True, help_text=_("The Viber bot deeplink, optional"))

    whatsapp_deeplink = models.URLField(null=True, blank=True, help_text=_("The WhatsApp bot deeplink, optional"))

    description = models.TextField(
        max_length=320, default="", help_text=_("A short description for this bot, required")
    )

    priority = models.IntegerField(
        default=0, help_text=_("The priority number for this bot among others on a list, high priority comes first")
    )

    def __str__(self):
        return self.title
