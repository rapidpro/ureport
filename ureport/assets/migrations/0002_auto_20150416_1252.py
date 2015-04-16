# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import shutil
from django.conf import settings

from django.db import models, migrations
import os


def populate_backgrounds(apps, schema_editor):
    OrgBackground = apps.get_model('orgs', "OrgBackground")
    Background = apps.get_model('assets', "Background")

    for org_bg in OrgBackground.objects.all():
        Background.objects.create(org=org_bg.org,
                                  name=org_bg.name,
                                  background_type=org_bg.background_type,
                                  image=org_bg.image,
                                  is_active=org_bg.is_active,
                                  created_by=org_bg.created_by,
                                  modified_by=org_bg.modified_by)

class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(populate_backgrounds),
    ]
