# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0003_auto_20140803_1350")]

    operations = [
        migrations.AddField(
            model_name="poll",
            name="image",
            field=models.ImageField(
                help_text="An image that should be displayed with this poll on the homepage",
                null=True,
                upload_to="polls",
                blank=True,
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="poll",
            name="is_featured",
            field=models.BooleanField(default=False, help_text="Whether this poll should be featured on the homepage"),
            preserve_default=True,
        ),
    ]
