# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('stories', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='story',
            name='image',
            field=models.ImageField(help_text='Any image that should be displayed with this story', null=True, upload_to=b'stories', blank=True),
        ),
    ]
