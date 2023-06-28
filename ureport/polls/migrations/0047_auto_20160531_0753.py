# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("polls", "0046_add_index_on_pollresults_contact")]

    operations = [
        migrations.AddField(model_name="pollresult", name="born", field=models.IntegerField(null=True)),
        migrations.AddField(model_name="pollresult", name="gender", field=models.CharField(max_length=1, null=True)),
    ]
