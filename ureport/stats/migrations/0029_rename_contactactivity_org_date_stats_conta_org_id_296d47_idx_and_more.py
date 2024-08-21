# Generated by Django 5.0.8 on 2024-08-21 12:10

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0028_activities_counter_triggers"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="contactactivity",
            new_name="stats_conta_org_id_296d47_idx",
            old_fields=("org", "date"),
        ),
        migrations.RenameIndex(
            model_name="contactactivity",
            new_name="stats_conta_org_id_e76e89_idx",
            old_fields=("org", "contact"),
        ),
    ]
