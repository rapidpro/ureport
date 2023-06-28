# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations

from ureport.sql import InstallSQL


class Migration(migrations.Migration):
    dependencies = [("polls", "0036_auto_20160331_1527")]

    operations = [InstallSQL("polls_0037")]
