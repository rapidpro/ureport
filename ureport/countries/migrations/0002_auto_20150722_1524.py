# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import regex

from django.db import models, migrations


def normalize_name(name):
    words = regex.split(r"\W+", unicode(name).lower(), flags=regex.UNICODE | regex.V0)
    output = " ".join([word for word in words if word])
    return output


def normalize_country_aliases(apps, schema_editor):
    CountryAlias = apps.get_model("countries", "CountryAlias")

    for alias in CountryAlias.objects.all():
        name = alias.name
        new_name = normalize_name(unicode(name))
        alias.name = new_name
        alias.save()

    # Delete aliases with empty names after normalization
    CountryAlias.objects.filter(name="").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('countries', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(normalize_country_aliases),
    ]
