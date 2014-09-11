# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

def move_category_to_poll_category(apps, schema_editor):
    Poll = apps.get_model('polls', "Poll")

    for poll in Poll.objects.all():
        poll.poll_category = poll.category
        poll.save()


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0005_poll_poll_category'),
    ]

    operations = [
        migrations.RunPython(move_category_to_poll_category),
    ]
