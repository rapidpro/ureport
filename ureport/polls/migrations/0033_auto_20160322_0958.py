# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0032_install_poll_results_count_triggers")]

    operations = [
        # remove duplicated index, added later in 0041
    ]
