# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orgs", "0014_auto_20150722_1419"), ("contacts", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Contact",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                ("uuid", models.CharField(unique=True, max_length=36)),
                (
                    "gender",
                    models.CharField(
                        choices=[("M", "Male"), ("F", "Female")],
                        max_length=1,
                        blank=True,
                        help_text="Gender of the contact",
                        null=True,
                        verbose_name="Gender",
                    ),
                ),
                ("born", models.IntegerField(null=True, verbose_name="Born Field", blank=True)),
                (
                    "occupation",
                    models.CharField(max_length=255, null=True, verbose_name="Occupation Field", blank=True),
                ),
                ("registered_on", models.DateTimeField(null=True, verbose_name="Registration Date", blank=True)),
                ("state", models.CharField(max_length=255, null=True, verbose_name="State Field")),
                ("district", models.CharField(max_length=255, null=True, verbose_name="District Field")),
                (
                    "org",
                    models.ForeignKey(
                        related_name="contacts", on_delete=models.PROTECT, verbose_name="Organization", to="orgs.Org"
                    ),
                ),
            ],
        )
    ]
