# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0038_remove_poll_db_triggers")]

    operations = [
        migrations.AddField(model_name="pollresult", name="ward", field=models.CharField(max_length=255, null=True))
    ]
