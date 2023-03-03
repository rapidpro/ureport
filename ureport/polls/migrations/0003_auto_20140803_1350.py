# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0002_auto_20140803_1309")]

    operations = [
        migrations.RemoveField(model_name="poll", name="description"),
        migrations.RemoveField(model_name="pollquestion", name="description"),
        migrations.AlterField(
            model_name="pollquestion",
            name="title",
            field=models.CharField(help_text="The title of this question", max_length=255),
        ),
    ]
