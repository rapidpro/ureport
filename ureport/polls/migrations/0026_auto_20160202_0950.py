# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0025_auto_20160129_1422")]

    operations = [
        migrations.AddField(
            model_name="pollquestion",
            name="ruleset_type",
            field=models.CharField(default="wait_message", max_length=32),
        ),
        migrations.AlterUniqueTogether(name="pollquestion", unique_together=set([("poll", "ruleset_uuid")])),
    ]
