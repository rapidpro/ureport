# Generated by Django 3.2.8 on 2021-11-04 12:00

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orgs", "0029_auto_20211025_1504"),
        ("stats", "0025_more_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contactactivity",
            name="org",
            field=models.ForeignKey(
                db_index=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="contact_activities",
                to="orgs.org",
            ),
        ),
    ]
