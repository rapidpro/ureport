# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0030_auto_20160314_1412'),
    ]

    operations = [
        migrations.AddField(
            model_name='poll',
            name='runs_count',
            field=models.IntegerField(default=0, help_text='The number of polled reporters on this poll'),
        ),
    ]
