# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('categories', '0002_auto_20140820_1415'),
        ('polls', '0007_remove_poll_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='poll',
            name='category',
            field=models.ForeignKey(blank=True, to='categories.Category', help_text='The category this Poll belongs to', null=True),
            preserve_default=True,
        ),
    ]
