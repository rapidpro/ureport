# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0012_install_triggers'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='ward',
            field=models.CharField(max_length=255, null=True, verbose_name='Ward Field'),
        ),
    ]
