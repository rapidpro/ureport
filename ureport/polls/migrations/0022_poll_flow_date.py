# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0021_auto_20150508_1212")]

    operations = [migrations.AddField(model_name="poll", name="poll_date", field=models.DateTimeField(null=True))]
