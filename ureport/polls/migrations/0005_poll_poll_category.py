# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0004_auto_20140804_0005")]

    operations = [
        migrations.AddField(
            model_name="poll",
            name="poll_category",
            field=models.ForeignKey(
                blank=True,
                to="polls.PollCategory",
                on_delete=models.PROTECT,
                help_text="The category this Poll belongs to",
                null=True,
            ),
            preserve_default=True,
        )
    ]
