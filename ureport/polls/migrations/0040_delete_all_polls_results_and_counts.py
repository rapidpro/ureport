# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations

# language=SQL;
CUSTOM_SQL = """
TRUNCATE polls_pollresult, polls_pollresultscounter;
"""


class Migration(migrations.Migration):
    dependencies = [("polls", "0039_pollresult_ward")]

    operations = [migrations.RunSQL(CUSTOM_SQL)]
