# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0002_auto_20140802_2104'),
    ]

    operations = [
        migrations.AddField(
            model_name='org',
            name='logo',
            field=models.ImageField(help_text='The logo that should be used for this organization', null=True, upload_to=b'logos', blank=True),
            preserve_default=True,
        ),
    ]
