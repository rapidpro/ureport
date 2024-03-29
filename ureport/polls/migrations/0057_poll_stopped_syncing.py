# Generated by Django 2.2.5 on 2019-11-08 10:02

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0056_auto_20190926_1554")]

    operations = [
        migrations.AddField(
            model_name="poll",
            name="stopped_syncing",
            field=models.BooleanField(default=False, help_text="Whether the poll should stop regenerating stats."),
        )
    ]
