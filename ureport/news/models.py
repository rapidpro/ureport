from django.db import models
from smartmin.models import SmartModel
from dash.orgs.models import Org
from django.utils.translation import ugettext_lazy as _
from ureport.categories.models import Category

class NewsItem(SmartModel):
    title = models.CharField(max_length=255,
                             help_text=_("The title for this item"))

    description = models.TextField(blank=True, null=True,
                                   help_text=_("A short summary description for this item"))

    link = models.CharField(max_length=255,
                            help_text="A link that should be associated with this item")

    category = models.ForeignKey(Category, related_name="news",
                                 help_text=_("The category this item belongs to"))

    org = models.ForeignKey(Org,
                            help_text="The organization this item belongs to")

class Video(SmartModel):
    title = models.CharField(max_length=255,
                             help_text=_("The title for this Video"))

    description = models.TextField(blank=True, null=True,
                                   help_text=_("A short summary description for this video"))

    video_id = models.CharField(max_length=255,
                                help_text="The id of the YouTube video that should be linked to this item")

    category = models.ForeignKey(Category, related_name="videos",
                                 help_text=_("The category this item belongs to"))

    org = models.ForeignKey(Org,
                            help_text="The organization this video belongs to")