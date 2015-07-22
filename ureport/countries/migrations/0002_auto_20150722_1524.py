# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import re

from django.db import models, migrations


def name_stemming(name):
    words = re.split(r'\W+', name, re.UNICODE)
    return " ".join([word.lower() for word in words if word])


def populated_stemmed_name(apps, schema_editor):
    CountryAlias = apps.get_model("countries", "CountryAlias")

    for alias in CountryAlias.objects.all():
        name = alias.name
        new_name = name_stemming(name)
        alias.name = new_name
        alias.save()


class Migration(migrations.Migration):

    dependencies = [
        ('countries', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(populated_stemmed_name),
    ]
