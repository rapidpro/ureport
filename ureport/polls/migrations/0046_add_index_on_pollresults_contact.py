# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations

# language=SQL
INDEX_SQL = """
CREATE INDEX polls_pollresult_contact
ON polls_pollresult (contact);
"""


class Migration(migrations.Migration):
    dependencies = [("polls", "0045_fix_has_synced_field")]

    operations = [migrations.RunSQL(INDEX_SQL)]
