# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0014_auto_20150722_1419'),
        ('contacts', '0003_install_count_triggers'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContactField',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('label', models.CharField(max_length=36, verbose_name='Label')),
                ('key', models.CharField(max_length=36, verbose_name='Key')),
                ('value_type', models.CharField(max_length=1, verbose_name='Field Type')),
                ('org', models.ForeignKey(related_name='contactfields', verbose_name='Org', to='orgs.Org')),
            ],
        ),
    ]
