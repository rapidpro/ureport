# Generated by Django 2.2.3 on 2019-07-16 14:31

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0006_boundary_backend"),
        ("polls", "0053_poll_backend"),
        ("orgs", "0026_fix_org_config_rapidpro"),
        ("stats", "0002_add_segments"),
    ]

    operations = [
        migrations.CreateModel(
            name="PollStats",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(max_length=255)),
                ("count", models.IntegerField(default=0, help_text="Number of items with this counter")),
                (
                    "age_segment",
                    models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="stats.AgeSegment"),
                ),
                (
                    "category",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL, to="polls.PollResponseCategory"
                    ),
                ),
                (
                    "gender_segment",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL, to="stats.GenderSegment"
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="poll_stats", to="orgs.Org"
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL, to="polls.PollQuestion"
                    ),
                ),
                (
                    "state",
                    models.ForeignKey(
                        null=True, on_delete=django.db.models.deletion.SET_NULL, to="locations.Boundary"
                    ),
                ),
            ],
        )
    ]
