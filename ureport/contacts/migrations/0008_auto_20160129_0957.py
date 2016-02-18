# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0007_auto_20151007_2044'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='contact',
            unique_together=set([('org', 'uuid')]),
        ),
    ]
