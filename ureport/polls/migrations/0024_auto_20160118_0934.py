# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0023_populate_flow_date")]

    operations = [migrations.AlterField(model_name="poll", name="poll_date", field=models.DateTimeField())]
