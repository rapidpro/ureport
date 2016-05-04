# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0038_remove_poll_db_triggers'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='pollresult',
            index_together=set([('org', 'flow', 'ruleset', 'text'), ('org', 'flow')]),
        ),
    ]
