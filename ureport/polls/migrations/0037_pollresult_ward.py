# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0036_auto_20160331_1527'),
    ]

    operations = [
        migrations.AddField(
            model_name='pollresult',
            name='ward',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
