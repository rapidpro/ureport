from __future__ import unicode_literals
from django.db import models
from smartmin.models import SmartModel
from dash.orgs.models import Org
from django.utils.translation import ugettext_lazy as _
from dash.categories.models import Category


class NewsItem(SmartModel):
    title = models.CharField(max_length=255,
                             help_text=_("The title for this item"))

    description = models.TextField(blank=True, null=True,
                                   help_text=_("A short summary description for this item"))

    link = models.CharField(max_length=255,
                            help_text=_("A link that should be associated with this item"))

    category = models.ForeignKey(Category, related_name="news",
                                 help_text=_("The category this item belongs to"))

    org = models.ForeignKey(Org,
                            help_text=_("The organization this item belongs to"))

    def short_description(self):
        if len(self.description) > 300:
            return self.description[:300] + "..."
        return self.description

    def as_brick_json(self):
        return dict(title=self.title, description=self.short_description(), link=self.link, created_on=self.created_on.strftime('%b %d, %Y'))


class Video(SmartModel):
    title = models.CharField(max_length=255,
                             help_text=_("The title for this Video"))

    description = models.TextField(blank=True, null=True,
                                   help_text=_("A short summary description for this video"))

    video_id = models.CharField(max_length=255,
                                help_text=_("The id of the YouTube video that should be linked to this item"))

    category = models.ForeignKey(Category, related_name="videos",
                                 help_text=_("The category this item belongs to"))

    org = models.ForeignKey(Org,
                            help_text=_("The organization this video belongs to"))