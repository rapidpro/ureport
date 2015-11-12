# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0024_populate-response-categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='pollresponsecategory',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
