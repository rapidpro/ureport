# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0022_poll_base_language'),
    ]

    operations = [
        migrations.AddField(
            model_name='pollquestion',
            name='ruleset_type',
            field=models.CharField(default='wait_message', max_length=32),
        ),
        migrations.AlterUniqueTogether(
            name='pollquestion',
            unique_together=set([('poll', 'ruleset_uuid')]),
        ),
    ]
