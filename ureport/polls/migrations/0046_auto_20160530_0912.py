# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0045_fix_has_synced_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='pollresult',
            name='born',
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name='pollresult',
            name='gender',
            field=models.CharField(max_length=1, null=True),
        ),
    ]
