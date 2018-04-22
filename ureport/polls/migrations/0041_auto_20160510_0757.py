# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0040_delete_all_polls_results_and_counts'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='pollresult',
            index_together=set([('org', 'flow', 'ruleset', 'text'), ('org', 'flow')]),
        ),
    ]
