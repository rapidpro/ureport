# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

def add_category_to_current_stories(apps, schema_editor):
    Story = apps.get_model('stories', "Story")
    Category = apps.get_model('categories', "Category")

    for story in Story.objects.all():
        general_category = Category.objects.get(name__icontains="general", org=story.org)
        story.category = general_category
        story.save()


class Migration(migrations.Migration):

    dependencies = [
        ('stories', '0005_story_category'),
    ]

    operations = [
        migrations.RunPython(add_category_to_current_stories),
    ]
