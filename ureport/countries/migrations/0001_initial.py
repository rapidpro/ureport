# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import django_countries.fields

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="CountryAlias",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                (
                    "is_active",
                    models.BooleanField(
                        default=True, help_text="Whether this item is active, use this instead of deleting"
                    ),
                ),
                (
                    "created_on",
                    models.DateTimeField(help_text="When this item was originally created", auto_now_add=True),
                ),
                ("modified_on", models.DateTimeField(help_text="When this item was last modified", auto_now=True)),
                ("country", django_countries.fields.CountryField(max_length=2)),
                ("name", models.CharField(help_text="The name for our alias", max_length=128)),
                (
                    "created_by",
                    models.ForeignKey(
                        related_name="countries_countryalias_creations",
                        on_delete=models.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                        help_text="The user which originally created this item",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        related_name="countries_countryalias_modifications",
                        on_delete=models.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                        help_text="The user which last modified this item",
                    ),
                ),
            ],
            options={"abstract": False},
            bases=(models.Model,),
        )
    ]
