# -*- coding: utf-8 -*-
# Generated by Django 1.11.11 on 2018-03-14 13:17
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("locations", "0003_remove_inactive_boundaries")]

    operations = [
        migrations.AddField(
            model_name="boundary", name="backend", field=models.CharField(default="rapidpro", max_length=16)
        )
    ]
