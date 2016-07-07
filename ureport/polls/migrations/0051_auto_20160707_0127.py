# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0050_merge'),
    ]

    operations = [
        migrations.AlterField(
            model_name='poll',
            name='poll_date',
            field=models.DateTimeField(default=datetime.datetime(2016, 7, 7, 1, 27, 6, 581263, tzinfo=utc), help_text='The date to display for this poll. Make it empty to use flow created_on.'),
            preserve_default=False,
        ),
    ]
