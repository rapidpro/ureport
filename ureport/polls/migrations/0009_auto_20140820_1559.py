# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations


def populate_categories(apps, schema_editor):
    Poll = apps.get_model("polls", "Poll")
    Category = apps.get_model("categories", "Category")

    for poll in Poll.objects.all():
        poll_category = poll.poll_category
        category = Category.objects.get(name=poll_category.name, org=poll_category.org)
        poll.category = category
        poll.save()


class Migration(migrations.Migration):
    dependencies = [("polls", "0008_poll_category")]

    operations = [migrations.RunPython(populate_categories)]
