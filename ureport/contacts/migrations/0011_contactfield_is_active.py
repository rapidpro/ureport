# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contacts", "0010_contact_triggerts")]

    operations = [
        migrations.AddField(model_name="contactfield", name="is_active", field=models.BooleanField(default=True))
    ]
