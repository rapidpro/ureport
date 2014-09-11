# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

def populate_category_images(apps, schema_editor):
    Category = apps.get_model('categories', "Category")
    CategoryImage = apps.get_model('categories', "CategoryImage")
    User = apps.get_model("auth", "User")
    root = User.objects.filter(username="root").first()

    if not root:
        root = User.objects.filter(username="root2").first()

    if not root:
        root = User.objects.create(username="root2")

    for category in Category.objects.all():
        CategoryImage.objects.create(name=category.name,
                                     category=category,
                                     image=category.image,
                                     created_by=root,
                                     modified_by=root)


class Migration(migrations.Migration):

    dependencies = [
        ('categories', '0003_categoryimage'),
    ]

    operations = [
        migrations.RunPython(populate_category_images),
    ]
