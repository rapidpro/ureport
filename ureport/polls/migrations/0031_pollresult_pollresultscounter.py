# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orgs", "0016_taskstate_is_disabled"), ("polls", "0030_auto_20160314_2036")]

    operations = [
        migrations.CreateModel(
            name="PollResult",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                ("flow", models.CharField(max_length=36)),
                ("ruleset", models.CharField(max_length=36)),
                ("contact", models.CharField(max_length=36)),
                ("date", models.DateTimeField()),
                ("completed", models.BooleanField()),
                ("category", models.CharField(max_length=255, null=True)),
                ("text", models.CharField(max_length=640, null=True)),
                ("state", models.CharField(max_length=255, null=True)),
                ("district", models.CharField(max_length=255, null=True)),
                ("org", models.ForeignKey(related_name="poll_results", on_delete=models.PROTECT, to="orgs.Org")),
            ],
        ),
        migrations.CreateModel(
            name="PollResultsCounter",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                ("ruleset", models.CharField(max_length=36)),
                ("type", models.CharField(max_length=255)),
                ("count", models.IntegerField(default=0, help_text="Number of items with this counter")),
                ("org", models.ForeignKey(related_name="results_counters", on_delete=models.PROTECT, to="orgs.Org")),
            ],
        ),
    ]
