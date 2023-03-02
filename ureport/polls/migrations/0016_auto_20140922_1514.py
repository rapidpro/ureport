# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("categories", "0005_auto_20140922_1514"), ("polls", "0015_remove_poll_image")]

    operations = [
        migrations.AddField(
            model_name="poll",
            name="category_image",
            field=models.ForeignKey(
                to="categories.CategoryImage",
                on_delete=models.PROTECT,
                help_text="The splash category image to display for the poll",
                null=True,
            ),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name="featuredresponse",
            name="created_by",
            field=models.ForeignKey(
                related_name="polls_featuredresponse_creations",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which originally created this item",
            ),
        ),
        migrations.AlterField(
            model_name="featuredresponse",
            name="modified_by",
            field=models.ForeignKey(
                related_name="polls_featuredresponse_modifications",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which last modified this item",
            ),
        ),
        migrations.AlterField(
            model_name="featuredresponse",
            name="poll",
            field=models.ForeignKey(
                related_name="featured_responses",
                on_delete=models.PROTECT,
                to="polls.Poll",
                help_text="The poll for this response",
            ),
        ),
        migrations.AlterField(
            model_name="poll",
            name="category",
            field=models.ForeignKey(
                related_name="polls",
                on_delete=models.PROTECT,
                to="categories.Category",
                help_text="The category this Poll belongs to",
            ),
        ),
        migrations.AlterField(
            model_name="poll",
            name="created_by",
            field=models.ForeignKey(
                related_name="polls_poll_creations",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which originally created this item",
            ),
        ),
        migrations.AlterField(
            model_name="poll",
            name="modified_by",
            field=models.ForeignKey(
                related_name="polls_poll_modifications",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which last modified this item",
            ),
        ),
        migrations.AlterField(
            model_name="pollcategory",
            name="created_by",
            field=models.ForeignKey(
                related_name="polls_pollcategory_creations",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which originally created this item",
            ),
        ),
        migrations.AlterField(
            model_name="pollcategory",
            name="modified_by",
            field=models.ForeignKey(
                related_name="polls_pollcategory_modifications",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which last modified this item",
            ),
        ),
        migrations.AlterField(
            model_name="pollimage",
            name="created_by",
            field=models.ForeignKey(
                related_name="polls_pollimage_creations",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which originally created this item",
            ),
        ),
        migrations.AlterField(
            model_name="pollimage",
            name="modified_by",
            field=models.ForeignKey(
                related_name="polls_pollimage_modifications",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which last modified this item",
            ),
        ),
        migrations.AlterField(
            model_name="pollimage",
            name="poll",
            field=models.ForeignKey(
                related_name="images", on_delete=models.PROTECT, to="polls.Poll", help_text="The poll to associate to"
            ),
        ),
        migrations.AlterField(
            model_name="pollquestion",
            name="created_by",
            field=models.ForeignKey(
                related_name="polls_pollquestion_creations",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which originally created this item",
            ),
        ),
        migrations.AlterField(
            model_name="pollquestion",
            name="modified_by",
            field=models.ForeignKey(
                related_name="polls_pollquestion_modifications",
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
                help_text="The user which last modified this item",
            ),
        ),
        migrations.AlterField(
            model_name="pollquestion",
            name="poll",
            field=models.ForeignKey(
                related_name="questions",
                on_delete=models.PROTECT,
                to="polls.Poll",
                help_text="The poll this question is part of",
            ),
        ),
    ]
