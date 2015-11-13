# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0021_auto_20150508_1212'),
    ]

    operations = [
        migrations.AddField(
            model_name='poll',
            name='base_language',
            field=models.CharField(default='base', help_text='Th base language of the flow to use', max_length=4),
        ),
    ]
