# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations

# language=SQL
INDEX_SQL = """
CREATE INDEX polls_pollresult_org_flow_contact
ON polls_pollresult (org_id, flow, contact);
"""


class Migration(migrations.Migration):
    dependencies = [("polls", "0041_auto_20160510_0757")]

    operations = [migrations.RunSQL(INDEX_SQL)]
