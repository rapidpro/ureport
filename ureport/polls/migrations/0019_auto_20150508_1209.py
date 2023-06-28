# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0018_auto_20150105_1622")]

    operations = [
        migrations.AddField(
            model_name="poll",
            name="flow_uuid",
            field=models.CharField(help_text="The Flow this Poll is based on", max_length=36, null=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="pollquestion",
            name="ruleset_uuid",
            field=models.CharField(help_text="The RuleSet this question is based on", max_length=36, null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="poll",
            name="org",
            field=models.ForeignKey(
                related_name="polls",
                on_delete=models.PROTECT,
                to="orgs.Org",
                help_text="The organization this poll is part of",
            ),
            preserve_default=True,
        ),
    ]
