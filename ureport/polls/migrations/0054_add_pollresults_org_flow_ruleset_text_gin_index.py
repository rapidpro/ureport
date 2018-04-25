# -*- coding: utf-8 -*-
# Generated by Django 1.11.12 on 2018-04-25 16:16
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('polls', '0053_poll_backend'),
    ]

    operations = [
        migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS btree_gin;"),
        migrations.RunSQL("CREATE INDEX CONCURRENTLY IF NOT EXISTS polls_pollresult_org_flow_ruleset_text_gin_idx "
                          "ON polls_pollresult USING GIN (org_id, flow, ruleset, text);"),
    ]
