from functools import partial

from django.db import models
from django.utils.translation import gettext_lazy as _

from dash.orgs.models import Org
from dash.utils import generate_file_path
from smartmin.models import SmartModel
from ureport.bots.models import Bot


class LandingPage(SmartModel):
    org = models.ForeignKey(
        Org,
        on_delete=models.PROTECT,
        related_name="landing_pages",
        help_text=_("The organization this landing page is part of"),
    )

    title = models.CharField(max_length=128, help_text=_("The title to display for this landing page"))

    action_text = models.CharField(
        max_length=128, null=True, blank=True, help_text=_("The call to action text for this landing page")
    )

    slug = models.CharField(max_length=128, help_text=_("The slug to use on the link for this landing page"))

    content = models.TextField(help_text=_("The body of text for the landing page"))

    image = models.ImageField(
        upload_to=partial(generate_file_path, "landingpages"),
        null=True,
        blank=True,
        help_text=_("The image file to use for the page"),
    )

    bots = models.ManyToManyField(Bot, blank=True)

    class Meta:
        index_together = (("org", "slug"),)
        unique_together = ("org", "slug")
