# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0016_auto_20140922_1514")]

    operations = [
        migrations.AlterField(
            model_name="poll",
            name="category_image",
            field=models.ForeignKey(
                to="categories.CategoryImage",
                on_delete=models.PROTECT,
                help_text="The splash category image to display for the poll (optional)",
                null=True,
            ),
        )
    ]
