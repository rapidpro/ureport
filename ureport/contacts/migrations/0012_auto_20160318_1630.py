# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0011_contactfield_is_active'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='contact',
            index_together=set([('org', 'uuid')]),
        ),
        migrations.AlterIndexTogether(
            name='contactfield',
            index_together=set([('org', 'key'), ('org', 'label')]),
        ),
    ]
