# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from ureport.sql import InstallSQL


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0037_install_poll_results_count_triggers'),
    ]

    operations = [
        InstallSQL('polls_0038')
    ]
