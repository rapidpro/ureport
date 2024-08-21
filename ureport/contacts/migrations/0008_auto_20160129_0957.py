# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contacts", "0007_auto_20151007_2044")]

    operations = [
        migrations.AddConstraint(
            model_name="contact",
            constraint=models.UniqueConstraint(
                fields=["org", "uuid"], name="contacts_contact_org_id_563dcefdcba190b9_uniq"
            ),
        ),
    ]
