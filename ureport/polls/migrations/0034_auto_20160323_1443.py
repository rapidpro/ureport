# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0033_auto_20160322_0958'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='pollresultscounter',
            index_together=set([('org', 'ruleset', 'type')]),
        ),
    ]
