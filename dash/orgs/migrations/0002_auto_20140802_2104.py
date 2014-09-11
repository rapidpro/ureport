# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='org',
            name='language',
            field=models.CharField(choices=[(b'en_us', b'English')], max_length=64, blank=True, help_text='The main language used by this organization', null=True, verbose_name='Language'),
        ),
    ]
