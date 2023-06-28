# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations


def generate_job_block_types(apps, schema_editor):
    User = apps.get_model("auth", "User")
    root = User.objects.filter(username="root").first()

    if not root:
        root = User.objects.create(username="root")

    DashBlockType = apps.get_model("dashblocks", "DashBlockType")

    DashBlockType.objects.get_or_create(
        name="Jobs",
        slug="jobs",
        description="U-Report job pages",
        has_title=True,
        has_image=True,
        has_rich_text=False,
        has_summary=False,
        has_link=False,
        has_gallery=False,
        has_color=False,
        has_video=False,
        has_tags=False,
        created_by_id=root.id,
        modified_by_id=root.id,
    )


class Migration(migrations.Migration):
    dependencies = [("jobs", "0001_initial"), ("dashblocks", "0006_auto_20140922_1514")]

    operations = [migrations.RunPython(generate_job_block_types)]
