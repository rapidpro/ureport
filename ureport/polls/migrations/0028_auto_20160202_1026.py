# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0027_poll_base_language")]

    operations = [
        migrations.CreateModel(
            name="PollResponseCategory",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                (
                    "rule_uuid",
                    models.CharField(help_text="The Rule this response category is based on", max_length=36),
                ),
                ("category", models.TextField(null=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "question",
                    models.ForeignKey(
                        related_name="response_categories", on_delete=models.PROTECT, to="polls.PollQuestion"
                    ),
                ),
            ],
        ),
        migrations.AlterUniqueTogether(name="pollresponsecategory", unique_together=set([("question", "rule_uuid")])),
    ]
