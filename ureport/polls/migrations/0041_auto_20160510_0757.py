# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0040_delete_all_polls_results_and_counts")]

    operations = [
        migrations.AddIndex(
            model_name="pollresult",
            index=models.Index(
                fields=["org", "flow", "ruleset", "text"], name="polls_pollresult_org_id_dfd50a4d782b673_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="pollresult",
            index=models.Index(fields=["org", "flow"], name="polls_pollresult_org_id_68705a7f5a6456ed_idx"),
        ),
    ]
