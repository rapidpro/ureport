# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("news", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="newsitem",
            name="category",
            field=models.ForeignKey(
                related_name="news",
                on_delete=models.PROTECT,
                to="categories.Category",
                help_text="The category this item belongs to",
            ),
        ),
        migrations.AlterField(
            model_name="newsitem",
            name="created_by",
            field=models.ForeignKey(
                related_name="news_newsitem_creations",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which originally created this item",
            ),
        ),
        migrations.AlterField(
            model_name="newsitem",
            name="modified_by",
            field=models.ForeignKey(
                related_name="news_newsitem_modifications",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which last modified this item",
            ),
        ),
        migrations.AlterField(
            model_name="video",
            name="category",
            field=models.ForeignKey(
                related_name="videos",
                on_delete=models.PROTECT,
                to="categories.Category",
                help_text="The category this item belongs to",
            ),
        ),
        migrations.AlterField(
            model_name="video",
            name="created_by",
            field=models.ForeignKey(
                related_name="news_video_creations",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which originally created this item",
            ),
        ),
        migrations.AlterField(
            model_name="video",
            name="modified_by",
            field=models.ForeignKey(
                related_name="news_video_modifications",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which last modified this item",
            ),
        ),
    ]
