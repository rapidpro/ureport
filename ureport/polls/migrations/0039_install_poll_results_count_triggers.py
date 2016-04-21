# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from ureport.sql import InstallSQL


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0038_pollresult_ward'),
    ]

    operations = [
        InstallSQL('polls_0039')
    ]
