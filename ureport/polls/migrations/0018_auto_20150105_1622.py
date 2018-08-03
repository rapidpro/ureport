# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    def fix_users(apps, schema_editor):
        User = apps.get_model("auth", "User")

        # root2 should be a superuser
        User.objects.filter(username="root2").update(is_superuser=True)

        # all other users are not superusers
        User.objects.filter(pk__gt=0).exclude(username="root2").exclude(username="root").update(is_superuser=False)

    dependencies = [("polls", "0017_auto_20140922_1921")]

    operations = [migrations.RunPython(fix_users)]
