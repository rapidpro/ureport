# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0038_remove_poll_db_triggers'),
    ]

    operations = [
        migrations.AddField(
            model_name='pollresult',
            name='ward',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
