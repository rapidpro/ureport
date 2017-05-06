# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0037_install_poll_results_count_triggers'),
    ]

    operations = [
        migrations.AlterField(
            model_name='poll',
            name='poll_date',
            field=models.DateTimeField(help_text='The date to display for this poll. Make it empty to use flow created_on.', null=True),
        ),
    ]
