# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("polls", "0032_install_poll_results_count_triggers")]

    operations = [migrations.AlterIndexTogether(name="pollresult", index_together=set([("org", "flow")]))]
