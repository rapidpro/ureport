# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations

# language=SQL
TRIGGER_SQL = """
--------------------------------------------------------------------------------------
-- Increment or decrement the results count on counter of given type and ruleset uuid
--------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
  ureport_insert_results_counter(_org_id INT, _ruleset CHAR(36), _type VARCHAR, _count INT)
RETURNS VOID AS $$
BEGIN
  INSERT INTO polls_pollresultscounter("org_id", "ruleset", "type", "count") VALUES(_org_id, _ruleset, _type, _count);
  PERFORM ureport_maybe_squash_resultscounters(_org_id, _ruleset, _type);
END;
$$ LANGUAGE plpgsql;
-----------------------------------------------------------------------------
-- Every 100 inserts or so this will squash the counters by gathering
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
  ureport_maybe_squash_resultscounters(_org_id INT, _ruleset CHAR(36), _type VARCHAR)
RETURNS VOID AS $$
BEGIN
  IF RANDOM() < .01 THEN
    WITH deleted as (DELETE FROM polls_pollresultscounter
      WHERE "org_id" = _org_id AND "type" = _type AND "ruleset" = _ruleset
      RETURNING "count")
      INSERT INTO polls_pollresultscounter("org_id", "ruleset", "type", "count")
      VALUES (_org_id, _ruleset, _type ,GREATEST(0, (SELECT SUM("count") FROM deleted)));
  END IF;
END;
$$ LANGUAGE plpgsql;
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
    -- total polled for this ruleset
    PERFORM ureport_insert_results_counter(_poll_result.org_id, _poll_result.ruleset, CONCAT('ruleset:', LOWER(_poll_result.ruleset), ':total-ruleset-polled'), _count);
    IF _poll_result.category iS NOT NULL THEN
      -- total replied to this ruleset
      PERFORM ureport_insert_results_counter(_poll_result.org_id, _poll_result.ruleset, CONCAT('ruleset:', LOWER(_poll_result.ruleset), ':total-ruleset-responded'), _count);
      -- We have a category, count the number with this category response, contacts the replied this question with this category
      PERFORM ureport_insert_results_counter(_poll_result.org_id, _poll_result.ruleset, CONCAT('ruleset:', LOWER(_poll_result.ruleset), ':category:', LOWER(_poll_result.category)), _count);
    END IF;
    IF _poll_result.state IS NOT NULL AND _poll_result.category IS NOT NULL THEN
      -- Maps counts with category; contacts from this state that replied with this category
      PERFORM ureport_insert_results_counter(_poll_result.org_id, _poll_result.ruleset, CONCAT('ruleset:', LOWER(_poll_result.ruleset), ':category:', LOWER(_poll_result.category), ':state:', UPPER(_poll_result.state)), _count);
    ELSIF _poll_result.state IS NOT NULL THEN
      -- Maps counts without replies; contacts from this state who did not reply
      PERFORM ureport_insert_results_counter(_poll_result.org_id, _poll_result.ruleset, CONCAT('ruleset:', LOWER(_poll_result.ruleset), ':nocategory:', 'state:', UPPER(_poll_result.state)), _count);
    END IF;
    IF _poll_result.district IS NOT NULL AND _poll_result.category IS NOT NULL THEN
      -- Maps counts with category; contacts from this district that replied with this category
      PERFORM ureport_insert_results_counter(_poll_result.org_id, _poll_result.ruleset, CONCAT('ruleset:', LOWER(_poll_result.ruleset), ':category:', LOWER(_poll_result.category), ':district:', UPPER(_poll_result.district)), _count);
    ELSIF _poll_result.district IS NOT NULL THEN
      -- Maps counts without replies; contacts from this district who did not reply
      PERFORM ureport_insert_results_counter(_poll_result.org_id, _poll_result.ruleset, CONCAT('ruleset:', LOWER(_poll_result.ruleset), ':nocategory:', 'district:', UPPER(_poll_result.district)), _count);
    END IF;
  END IF;
END;
$$ LANGUAGE plpgsql;
-----------------------------------------------------------------------------
-- Updates our results counters
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ureport_update_results_counters() RETURNS TRIGGER AS $$
BEGIN
  -- PollResult being created, increment counters for poll_result NEW
  IF TG_OP = 'INSERT' THEN
    PERFORM ureport_increment_counter_for_poll_result(NEW, TRUE);
  ELSIF TG_OP = 'UPDATE' THEN
    -- If a poll result is changed, decrement the counters for its OLD values
    PERFORM ureport_increment_counter_for_poll_result(OLD, FALSE);
    -- Then, increment the counters for its NEW values
    PERFORM ureport_increment_counter_for_poll_result(NEW, TRUE);
  -- poll_result is being deleted
  ELSIF TG_OP = 'DELETE' THEN
    -- A poll_result is deleted, decrement all reporters counters for its values
    PERFORM ureport_increment_counter_for_poll_result(OLD, FALSE);
  -- Poll_results table is being truncated
  ELSIF TG_OP = 'TRUNCATE' THEN
   -- Clear all counters
   TRUNCATE polls_pollresultscounter;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS ureport_when_poll_result_update_then_update_results_counters on polls_pollresult;
CREATE TRIGGER ureport_when_poll_result_update_then_update_results_counters
  AFTER INSERT OR DELETE OR UPDATE ON polls_pollresult
  FOR EACH ROW EXECUTE PROCEDURE ureport_update_results_counters();
DROP TRIGGER IF EXISTS ureport_when_poll_results_truncate_then_update_results_counters ON polls_pollresult;
CREATE TRIGGER ureport_when_poll_results_truncate_then_update_results_counters
  AFTER TRUNCATE ON polls_pollresult
  EXECUTE PROCEDURE ureport_update_results_counters();
"""


class Migration(migrations.Migration):
    dependencies = [("polls", "0031_pollresult_pollresultscounter")]

    operations = [migrations.RunSQL(TRIGGER_SQL)]
