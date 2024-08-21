# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orgs", "0014_auto_20150722_1419")]

    operations = [
        migrations.CreateModel(
            name="Boundary",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                (
                    "osm_id",
                    models.CharField(help_text="This is the OSM id for this administrative boundary", max_length=15),
                ),
                ("name", models.CharField(help_text="The name of our administrative boundary", max_length=128)),
                (
                    "level",
                    models.IntegerField(
                        help_text="The level of the boundary, 0 for country, 1 for state, 2 for district"
                    ),
                ),
                (
                    "geometry",
                    models.TextField(
                        help_text="The json representing the geometry type and coordinates of the boundaries",
                        verbose_name="Geometry",
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        related_name="boundaries", on_delete=models.PROTECT, verbose_name="Organization", to="orgs.Org"
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        related_name="children",
                        on_delete=models.PROTECT,
                        to="locations.Boundary",
                        help_text="The parent to this political boundary if any",
                        null=True,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="boundary",
            constraint=models.UniqueConstraint(
                fields=["org", "osm_id"],
                name="locations_boundary_org_id_5c2d99160b82334a_uniq",
            ),
        ),
    ]
