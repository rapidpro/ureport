from dash.orgs.models import Org

from django.db import models
from django.db.models import Count, Sum
from django.utils import timezone
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

    location = models.ForeignKey(Boundary, null=True, on_delete=models.SET_NULL)

    date = models.DateTimeField(null=True)

    count = models.IntegerField(default=0, help_text=_("Number of items with this counter"))

    @classmethod
    def get_engagement_opinion_responses(cls, org):
        responses = PollStats.objects.filter(org=org).exclude(category=None).values("date").annotate(Sum("count"))
        return {str(elt["date"].date()): elt["sum__count"] for elt in responses}


class ContactActivity(models.Model):
    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="contact_activities")

    contact = models.CharField(max_length=36)

    born = models.IntegerField(null=True)

    gender = models.CharField(max_length=1, null=True)

    state = models.CharField(max_length=255, null=True)

    district = models.CharField(max_length=255, null=True)

    ward = models.CharField(max_length=255, null=True)

    date = models.DateField(help_text="The starting date for for the month")

    class Meta:
        index_together = (("org", "contact"), ("org", "date"))
        unique_together = ("org", "contact", "date")

    @classmethod
    def get_activity(cls, org):
        today = timezone.now().date()

        activities = ContactActivity.objects.filter(org=org, date__lte=today).values("date").annotate(Count("id"))

        return {str(elt["date"]): elt["id__count"] for elt in activities}
