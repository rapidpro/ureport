# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0002_source_widget_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='is_featured',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
    ]
