# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0024_auto_20160118_0934")]

    operations = [
        migrations.AddField(
            model_name="poll",
            name="flow_archived",
            field=models.BooleanField(
                default=False, help_text="Whether the flow for this poll is archived on RapidPro"
            ),
        ),
        migrations.AlterField(
            model_name="poll",
            name="poll_date",
            field=models.DateTimeField(
                help_text="The date to display for this poll. Make it empty to use flow created_on."
            ),
        ),
    ]
