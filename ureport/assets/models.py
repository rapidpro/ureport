# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from smartmin.models import SmartModel

from django.db import models
from django.utils.translation import gettext_lazy as _

from dash.orgs.models import Org

BANNER = "B"
PATTERN = "P"
FLAG = "F"
LOGO = "L"
ABOUT_PARTNER_LOGO = "A"

IMAGE_TYPES = (
    (BANNER, _("Banner")),
    (PATTERN, _("Pattern")),
    (FLAG, _("Flag")),
    (LOGO, "Logo"),
    (ABOUT_PARTNER_LOGO, _("About Partner Logo")),
)


class Image(SmartModel):
    org = models.ForeignKey(
        Org,
        on_delete=models.PROTECT,
        verbose_name=_("Org"),
        related_name="images",
        help_text=_("The organization to which the image will be used"),
    )

    name = models.CharField(
        verbose_name=_("Name"), max_length=128, help_text=_("A short descriptive name for this image")
    )

    image_type = models.CharField(max_length=1, choices=IMAGE_TYPES, default="A", verbose_name=_("Image type"))

    image = models.ImageField(upload_to="images", help_text=_("The image file"))

    priority = models.IntegerField(
        default=0, help_text=_("The priority number for this image among others on a list, high priority comes first")
    )
