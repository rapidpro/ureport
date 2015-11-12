# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0022_auto_20151110_1315'),
    ]

    operations = [
        migrations.CreateModel(
            name='PollResponseCategory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('rule_uuid', models.CharField(help_text='The Rule this response category is based on', max_length=36)),
                ('category', models.TextField(null=True)),
                ('question', models.ForeignKey(related_name='response_categories', to='polls.PollQuestion')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='pollresponsecategory',
            unique_together=set([('question', 'rule_uuid')]),
        ),
    ]
