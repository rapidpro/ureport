# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import str

import regex

from django.db import migrations


def normalize_name(name):
    words = regex.split(r"\W+", str(name).lower(), flags=regex.UNICODE | regex.V0)
    output = " ".join([word for word in words if word])
    return output


def normalize_country_aliases(apps, schema_editor):
    CountryAlias = apps.get_model("countries", "CountryAlias")

    for alias in CountryAlias.objects.all():
        name = alias.name
        new_name = normalize_name(str(name))
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
