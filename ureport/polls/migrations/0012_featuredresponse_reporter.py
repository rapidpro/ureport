# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0011_remove_poll_poll_category")]

    operations = [
        migrations.AddField(
            model_name="featuredresponse",
            name="reporter",
            field=models.CharField(
                help_text="The name of the sender of the message", max_length=255, null=True, blank=True
            ),
            preserve_default=True,
        )
    ]
