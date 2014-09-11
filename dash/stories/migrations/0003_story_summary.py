# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stories', '0002_auto_20140805_1158'),
    ]

    operations = [
        migrations.AddField(
            model_name='story',
            name='summary',
            field=models.TextField(help_text='The summary for the story', null=True, blank=True),
            preserve_default=True,
        ),
    ]
