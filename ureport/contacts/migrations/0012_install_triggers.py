# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from ureport.sql import InstallSQL

class Migration(migrations.Migration):

    dependencies = [
        ('contacts', '0011_contactfield_is_active'),
    ]

    operations = [
        InstallSQL('contacts_0012')
    ]
