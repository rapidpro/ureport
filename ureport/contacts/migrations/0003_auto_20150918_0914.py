# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orgs", "0014_auto_20150722_1419"), ("contacts", "0002_contact")]

    operations = [
        migrations.CreateModel(
            name="ReportersCounter",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                ("type", models.CharField(max_length=255)),
                ("count", models.IntegerField(default=0, help_text="Number of items with this counter")),
                ("org", models.ForeignKey(related_name="reporters_counters", on_delete=models.PROTECT, to="orgs.Org")),
            ],
        ),
        migrations.AddIndex(
            model_name="reporterscounter",
            index=models.Index(fields=["org", "type"], name="contacts_reporterscounter_org_id_6e256be32b9ee5bf_idx"),
        ),
    ]
