# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from ureport.sql import InstallSQL


class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0013_contact_ward'),
    ]

    operations = [
        InstallSQL('contacts_0014')
    ]
