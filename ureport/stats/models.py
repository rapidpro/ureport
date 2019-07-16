from django.db import models

# Create your models here.


class GenderSegment(models.Model):
    gender = models.CharField(max_length=1)


class AgeSegment(models.Model):
    min_age = models.IntegerField(null=True)
    max_age = models.IntegerField(null=True)
