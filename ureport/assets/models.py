from dash.orgs.models import Org
from django.db import models
from django.utils.translation import ugettext_lazy as _
from smartmin.models import SmartModel


BACKGROUND_TYPES = (('B', _("Banner")),
                   ('P', _("Pattern")))

class Background(SmartModel):
    org = models.ForeignKey(Org, verbose_name=_("Org"), related_name="ureport_backgrounds",
                            help_text=_("The organization in which the image will be used"))

    name = models.CharField(verbose_name=_("Name"), max_length=128,
                            help_text=_("The name to describe this background"))

    background_type = models.CharField(max_length=1, choices=BACKGROUND_TYPES, default='P', verbose_name=_("Background type"))

    image = models.ImageField(upload_to='org_bgs', help_text=_("The image file"))
