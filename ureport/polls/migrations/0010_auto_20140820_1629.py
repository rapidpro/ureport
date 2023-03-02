# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0009_auto_20140820_1559")]

    operations = [
        migrations.AlterField(
            model_name="poll",
            name="category",
            field=models.ForeignKey(
                help_text="The category this Poll belongs to", on_delete=models.PROTECT, to="categories.Category"
            ),
        )
    ]
