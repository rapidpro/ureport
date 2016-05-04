# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

#language=SQL
INDEX_SQL = """
CREATE INDEX polls_pollresult_org_flow_ruleset_text
ON polls_pollresult (org_id, flow, ruleset, text);

"""

class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0038_remove_poll_db_triggers'),
    ]

    operations = [
        migrations.RunSQL(INDEX_SQL)
    ]
