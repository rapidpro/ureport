# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("polls", "0001_initial")]

    operations = [
        migrations.AlterModelOptions(name="pollcategory", options={"verbose_name_plural": "Poll Categories"})
    ]
