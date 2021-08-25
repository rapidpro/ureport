from dash.orgs.models import Org
from smartmin.models import SmartModel

from django.db import models
from django.utils.translation import ugettext_lazy as _


class Topic(SmartModel):

    name = models.CharField(max_length=64, help_text=_("The name of this topic"))
    org = models.ForeignKey(Org, on_delete=models.PROTECT, help_text=_("The organization this topic belongs to"))

    def __str__(self) -> str:
        return self.name

    class Meta:
        unique_together = ("name", "org")
