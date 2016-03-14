# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0029_populate_response_categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='pollquestion',
            name='order',
            field=models.IntegerField(default=0, help_text='The order number for this question on the poll', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='pollquestion',
            name='ruleset_label',
            field=models.CharField(help_text='The label of the ruleset on RapidPro', max_length=255, null=True, blank=True),
        ),
    ]
