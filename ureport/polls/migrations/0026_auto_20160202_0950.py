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
        migrations.AddConstraint(
            model_name="pollquestion",
            constraint=models.UniqueConstraint(
                fields=["poll", "ruleset_uuid"],
                name="polls_pollquestion_poll_id_4202706c8106f06_uniq",
            ),
        ),
    ]
