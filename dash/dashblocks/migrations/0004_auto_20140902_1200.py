# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

def generate_initial_block_types(apps, schema_editor):
    User = apps.get_model("auth", "User")
    root = User.objects.filter(username="root").first()

    if not root:
        root = User.objects.filter(username="root2").first()

    if not root:
        root = User.objects.create(username="root2")

    DashBlockType = apps.get_model("dashblocks", "DashBlockType")

    DashBlockType.objects.get_or_create(name="Missions",
                                        slug="missions",
                                        description="U-Report missions blocks",
                                        has_title=True,
                                        has_image=True,
                                        has_rich_text=False,
                                        has_summary=False,
                                        has_link=False,
                                        has_gallery=False,
                                        has_color=False,
                                        has_video=False,
                                        has_tags=False,
                                        created_by=root,
                                        modified_by=root)

    DashBlockType.objects.get_or_create(name="Contact Us",
                                        slug="contact_us",
                                        description="U-Report contact us blocks",
                                        has_title=True,
                                        has_image=False,
                                        has_rich_text=False,
                                        has_summary=False,
                                        has_link=False,
                                        has_gallery=False,
                                        has_color=False,
                                        has_video=False,
                                        has_tags=False,
                                        created_by=root,
                                        modified_by=root)

class Migration(migrations.Migration):

    dependencies = [
        ('dashblocks', '0003_auto_20140804_0236'),
    ]

    operations = [
        migrations.RunPython(generate_initial_block_types),
    ]
