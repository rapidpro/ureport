# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0025_populate_response_categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='poll',
            name='flow_archived',
            field=models.BooleanField(default=False, help_text='Whether the flow for this poll is archived on RapidPro'),
        ),
        migrations.AlterField(
            model_name='poll',
            name='base_language',
            field=models.CharField(default='base', help_text='The base language of the flow to use', max_length=4),
        ),
    ]
