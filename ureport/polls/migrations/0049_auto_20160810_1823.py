# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0048_populate_age_and_gender_on_poll_results'),
    ]

    operations = [
        migrations.AlterField(
            model_name='poll',
            name='poll_date',
            field=models.DateTimeField(help_text='The date to display for this poll. Leave empty to use flow creation date.'),
        ),
    ]
