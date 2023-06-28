# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("categories", "0002_auto_20140820_1415"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orgs", "0005_orgbackground"),
    ]

    operations = [
        migrations.CreateModel(
            name="NewsItem",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                (
                    "is_active",
                    models.BooleanField(
                        default=True, help_text="Whether this item is active, use this instead of deleting"
                    ),
                ),
                (
                    "created_on",
                    models.DateTimeField(help_text="When this item was originally created", auto_now_add=True),
                ),
                ("modified_on", models.DateTimeField(help_text="When this item was last modified", auto_now=True)),
                ("title", models.CharField(help_text="The title for this item", max_length=255)),
                (
                    "description",
                    models.TextField(help_text="A short summary description for this item", null=True, blank=True),
                ),
                (
                    "link",
                    models.CharField(help_text="A link that should be associated with this item", max_length=255),
                ),
                (
                    "category",
                    models.ForeignKey(
                        help_text="The category this item belongs to",
                        on_delete=models.PROTECT,
                        to="categories.Category",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        help_text="The user which originally created this item",
                        on_delete=models.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        help_text="The user which last modified this item",
                        on_delete=models.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        help_text="The organization this item belongs to", on_delete=models.PROTECT, to="orgs.Org"
                    ),
                ),
            ],
            options={"abstract": False},
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name="Video",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                (
                    "is_active",
                    models.BooleanField(
                        default=True, help_text="Whether this item is active, use this instead of deleting"
                    ),
                ),
                (
                    "created_on",
                    models.DateTimeField(help_text="When this item was originally created", auto_now_add=True),
                ),
                ("modified_on", models.DateTimeField(help_text="When this item was last modified", auto_now=True)),
                ("title", models.CharField(help_text="The title for this Video", max_length=255)),
                (
                    "description",
                    models.TextField(help_text="A short summary description for this video", null=True, blank=True),
                ),
                (
                    "video_id",
                    models.CharField(
                        help_text="The id of the YouTube video that should be linked to this item", max_length=255
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        help_text="The category this item belongs to",
                        on_delete=models.PROTECT,
                        to="categories.Category",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        help_text="The user which originally created this item",
                        on_delete=models.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        help_text="The user which last modified this item",
                        on_delete=models.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "org",
                    models.ForeignKey(
                        help_text="The organization this video belongs to", on_delete=models.PROTECT, to="orgs.Org"
                    ),
                ),
            ],
            options={"abstract": False},
            bases=(models.Model,),
        ),
    ]
