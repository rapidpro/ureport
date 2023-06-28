# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations

from ureport.sql import InstallSQL


class Migration(migrations.Migration):
    dependencies = [("contacts", "0013_contact_ward")]

    operations = [InstallSQL("contacts_0014")]
