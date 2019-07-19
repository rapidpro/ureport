from dash.orgs.models import Org

from django.db import models
from django.utils.translation import ugettext_lazy as _

from ureport.locations.models import Boundary
from ureport.polls.models import PollQuestion, PollResponseCategory


class GenderSegment(models.Model):
    gender = models.CharField(max_length=1)


class AgeSegment(models.Model):
    min_age = models.IntegerField(null=True)
    max_age = models.IntegerField(null=True)

    @classmethod
    def get_age_segment_min_age(cls, age):
        min_ages = [0, 15, 20, 25, 31, 35]
        return [elt for elt in min_ages if age >= elt][-1]


class PollStats(models.Model):
    id = models.BigAutoField(auto_created=True, primary_key=True, verbose_name="ID")

    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="poll_stats")

    question = models.ForeignKey(PollQuestion, null=True, on_delete=models.SET_NULL)

    category = models.ForeignKey(PollResponseCategory, null=True, on_delete=models.SET_NULL)

    age_segment = models.ForeignKey(AgeSegment, null=True, on_delete=models.SET_NULL)

    gender_segment = models.ForeignKey(GenderSegment, null=True, on_delete=models.SET_NULL)

    state = models.ForeignKey(Boundary, null=True, on_delete=models.SET_NULL)

    type = models.CharField(max_length=255)

    count = models.IntegerField(default=0, help_text=_("Number of items with this counter"))
