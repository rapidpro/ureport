# -*- coding: utf-8 -*-
# Generated by Django 1.11.12 on 2018-04-05 13:30
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("polls", "0051_poll_backend")]

    operations = [migrations.RemoveField(model_name="poll", name="backend")]
