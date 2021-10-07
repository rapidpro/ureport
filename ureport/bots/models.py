from dash.orgs.models import Org
from smartmin.models import SmartModel

from django.db import models
from django.utils.translation import ugettext_lazy as _


class Bot(SmartModel):

    org = models.ForeignKey(
        Org, on_delete=models.PROTECT, related_name="bots", help_text=_("The organization this bot is part of")
    )

    featured = models.BooleanField(
        default=False, help_text=_("Whether this bot is featured and displayed on the homepage")
    )

    title = models.CharField(max_length=128, help_text=_("The title to display for this bot"))

    channel = models.CharField(
        max_length=128, help_text=_("The shortcode, number or bot name of the channel for this bot")
    )

    keyword = models.CharField(max_length=128, help_text=_("The keyword for this bot"))

    deeplink = models.URLField(null=True, blank=True, help_text=_("The deeplink for this bot, optional"))

    description = models.TextField(blank=True, null=True, help_text=_("The description of this bot, optional"))

    priority = models.IntegerField(
        default=0, help_text=_("The priority number for this bot among others on a list, high priority comes first")
    )
