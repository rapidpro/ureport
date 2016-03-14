# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0026_auto_20160202_0950'),
    ]

    operations = [
        migrations.AddField(
            model_name='poll',
            name='base_language',
            field=models.CharField(default='base', help_text='The base language of the flow to use', max_length=4),
        ),
    ]
