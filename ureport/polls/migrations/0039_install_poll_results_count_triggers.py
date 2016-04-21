# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


# language=SQL
TRIGGER_SQL = """
-----------------------------------------------------------------------------
-- Increment counters for a poll result
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ureport_increment_counter_for_poll_result(_poll_result polls_pollresult, _add BOOLEAN)
RETURNS VOID AS $$
DECLARE
  _count INT;
BEGIN
  IF _add THEN
    _count = 1;
  ELSE
    _count = -1;
  END IF;
  -- Count only if we have an org and a flow and a ruleset
  IF _poll_result.org_id IS NOT NULL AND _poll_result.flow IS NOT NULL AND _poll_result.ruleset IS NOT NULL THEN
    IF _poll_result.ward IS NOT NULL AND _poll_result.category IS NOT NULL THEN
      -- Maps counts with category; contacts from this ward that replied with this category
      PERFORM ureport_insert_results_counter(_poll_result.org_id, _poll_result.ruleset, CONCAT('ruleset:', LOWER(_poll_result.ruleset), ':category:', LOWER(_poll_result.category), ':ward:', UPPER(_poll_result.ward)), _count);
    ELSIF _poll_result.ward IS NOT NULL THEN
      -- Maps counts without replies; contacts from this ward who did not reply
      PERFORM ureport_insert_results_counter(_poll_result.org_id, _poll_result.ruleset, CONCAT('ruleset:', LOWER(_poll_result.ruleset), ':nocategory:', 'ward:', UPPER(_poll_result.ward)), _count);
    END IF;
  END IF;
END;
$$ LANGUAGE plpgsql;
"""



class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0038_pollresult_ward'),
    ]

    operations = [
        migrations.RunSQL(TRIGGER_SQL)
    ]
