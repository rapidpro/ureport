from dash.orgs.models import Org

from django.db import models
from django.utils.translation import ugettext_lazy as _

from ureport.locations.models import Boundary
from ureport.polls.models import PollQuestion, PollResponseCategory


class PollStats(models.Model):
    id = models.BigAutoField(auto_created=True, primary_key=True, verbose_name="ID")

    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="poll_stats")

    question = models.ForeignKey(PollQuestion, null=True, on_delete=models.SET_NULL)

    category = models.ForeignKey(PollResponseCategory, null=True, on_delete=models.SET_NULL)

    gender = models.CharField(max_length=1, null=True)

    born = models.IntegerField(null=True)

    location = models.ForeignKey(Boundary, null=True, on_delete=models.SET_NULL)

    date = models.DateTimeField(null=True)

    count = models.IntegerField(default=0, help_text=_("Number of items with this counter"))
