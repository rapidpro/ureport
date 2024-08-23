# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0033_auto_20160322_0958")]

    operations = [
        # model pollresultscounter was removed, the time to adjust this migration to replace index_together
    ]
