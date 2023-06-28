# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0035_auto_20160330_1550")]

    operations = [migrations.AlterField(model_name="pollresult", name="date", field=models.DateTimeField(null=True))]
