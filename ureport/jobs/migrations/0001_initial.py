# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Source',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('source', models.URLField()),
                ('title', models.CharField(max_length=100, blank=True)),
                ('source_type', models.CharField(max_length=1, choices=[(b't', b'twitter'), (b'f', b'facebook'), (b'r', b'rss')])),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
