# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.core.cache import cache


def clear_contacts(apps, schema_editor):
    Contact = apps.get_model('contacts', 'Contact')

    # delete fetched contacts
    Contact.objects.all().delete()

    # clear redis cache and locks to allow the next task to fetch all the contacts
    cache.delete_pattern('last:fetch_contacts:*')
    cache.delete_pattern('fetch_contacts')
    cache.delete_pattern('fetch_contacts*')


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0005_auto_20150921_0855'),
    ]

    operations = [
        migrations.RunPython(clear_contacts),
    ]
