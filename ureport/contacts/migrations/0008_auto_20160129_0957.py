# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("contacts", "0007_auto_20151007_2044")]

    operations = [migrations.AlterUniqueTogether(name="contact", unique_together=set([("org", "uuid")]))]
