# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("jobs", "0002_auto_20150320_1404")]

    operations = [
        migrations.AlterField(
            model_name="jobsource",
            name="is_featured",
            field=models.BooleanField(
                default=False, help_text="Featured job sources are shown first on the jobs page."
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="jobsource",
            name="source_type",
            field=models.CharField(
                help_text="Choose the type for the Job source. Twitter, Facebook or RSS feed",
                max_length=1,
                choices=[("T", "Twitter"), ("F", "Facebook"), ("R", "RSS")],
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="jobsource",
            name="source_url",
            field=models.URLField(help_text="The full URL to navigate to this Job source."),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="jobsource",
            name="title",
            field=models.CharField(help_text="The title or name to reference this Job source.", max_length=100),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="jobsource",
            name="widget_id",
            field=models.CharField(
                help_text="For Twitter, a widget Id is required to embed tweets on the website. Read carefully the instructions above on how to get the right widget Id",
                max_length=50,
                null=True,
                blank=True,
            ),
            preserve_default=True,
        ),
    ]
