# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

def pollcategory_to_category(apps, schema_editor):
    Category = apps.get_model('categories', "Category")
    User = apps.get_model("auth", "User")
    Org = apps.get_model("orgs", "Org")
    from ureport.polls.models import PollCategory

    root = User.objects.filter(username="root").first()
    
    if not root:
        root = User.objects.filter(username="root2").first()

    if not root:
        root = User.objects.create(username="root2")
    
    for poll_cat in PollCategory.objects.all():
        org = Org.objects.get(pk=poll_cat.org.pk)
        
        Category.objects.create(name=poll_cat.name,
                                org=org,
                                is_active=poll_cat.is_active,
                                created_by=root,
                                modified_by=root)

class Migration(migrations.Migration):

    dependencies = [
        ('categories', '0001_initial'),
        ('polls', '0005_poll_poll_category'),
    ]

    operations = [
        migrations.RunPython(pollcategory_to_category),
    ]
