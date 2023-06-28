# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0029_populate_response_categories")]

    operations = [
        migrations.AddField(
            model_name="poll",
            name="runs_count",
            field=models.IntegerField(default=0, help_text="The number of polled reporters on this poll"),
        ),
        migrations.AddField(
            model_name="pollquestion",
            name="priority",
            field=models.IntegerField(
                default=0, help_text="The priority number for this question on the poll", null=True, blank=True
            ),
        ),
        migrations.AddField(
            model_name="pollquestion",
            name="ruleset_label",
            field=models.CharField(
                help_text="The label of the ruleset on RapidPro", max_length=255, null=True, blank=True
            ),
        ),
    ]
