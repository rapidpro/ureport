# Generated by Django 2.2.3 on 2019-07-16 13:30

from django.db import migrations


def populate_segments(apps, schema_editor):
    GenderSegment = apps.get_model("stats", "GenderSegment")
    AgeSegment = apps.get_model("stats", "AgeSegment")

    GenderSegment.objects.get_or_create(gender="M")
    GenderSegment.objects.get_or_create(gender="F")
    AgeSegment.objects.get_or_create(min_age=0, max_age=14)
    AgeSegment.objects.get_or_create(min_age=15, max_age=19)
    AgeSegment.objects.get_or_create(min_age=20, max_age=24)
    AgeSegment.objects.get_or_create(min_age=25, max_age=30)
    AgeSegment.objects.get_or_create(min_age=31, max_age=35)
    AgeSegment.objects.get_or_create(min_age=36, max_age=2000)


class Migration(migrations.Migration):

    dependencies = [("stats", "0001_initial")]

    operations = [migrations.RunPython(populate_segments)]
