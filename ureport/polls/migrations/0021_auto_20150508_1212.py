# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0020_auto_20150508_1210")]

    operations = [
        migrations.RemoveField(model_name="poll", name="flow_id"),
        migrations.RemoveField(model_name="pollquestion", name="ruleset_id"),
        migrations.AlterField(
            model_name="poll",
            name="flow_uuid",
            field=models.CharField(default=1, help_text="The Flow this Poll is based on", max_length=36),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="pollquestion",
            name="ruleset_uuid",
            field=models.CharField(default=1, help_text="The RuleSet this question is based on", max_length=36),
            preserve_default=False,
        ),
    ]
