# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0042_add_index_on_poll_result_org_flow_contact'),
    ]

    operations = [
        migrations.AddField(
            model_name='poll',
            name='has_synced',
            field=models.BooleanField(default=False, help_text='Whether the poll has finished the initial results sync.'),
        ),
    ]
