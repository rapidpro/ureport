# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations

# language=SQL
TRIGGER_SQL = """
-----------------------------------------------------------------------------
-- Increment or decrement the reporters count on counter of given type
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
  ureport_insert_reporters_counter(_org_id INT, _type VARCHAR, _count INT)
RETURNS VOID AS $$
BEGIN
  INSERT INTO contacts_reporterscounter("org_id", "type", "count") VALUES(_org_id, _type, _count);
  PERFORM ureport_maybe_squash_reporterscounters(_org_id, _type);
END;
$$ LANGUAGE plpgsql;
-----------------------------------------------------------------------------
-- Every 100 inserts or so this will squash the counters by gathering
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
  ureport_maybe_squash_reporterscounters(_org_id INT, _type VARCHAR)
RETURNS VOID AS $$
BEGIN
  IF RANDOM() < .01 THEN
    WITH deleted as (DELETE FROM contacts_reporterscounter
      WHERE "org_id" = _org_id AND "type" = _type
      RETURNING "count")
      INSERT INTO contacts_reporterscounter("org_id", "type", "count")
      VALUES (_org_id, _type ,GREATEST(0, (SELECT SUM("count") FROM deleted)));
  END IF;
END;
$$ LANGUAGE plpgsql;
-----------------------------------------------------------------------------
-- Increment counters for a contact
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ureport_increment_counter_for_contact(_contact contacts_contact, _add BOOLEAN)
RETURNS VOID AS $$
DECLARE
  _count INT;
BEGIN
  IF _add THEN
    _count = 1;
  ELSE
    _count = -1;
  END IF;
  -- If we have a org, increment all reporters counters for its values
  IF _contact.org_id IS NOT NULL THEN
    PERFORM ureport_insert_reporters_counter(_contact.org_id, 'total-reporters', _count);
    IF _contact.gender IS NOT NULL THEN
      PERFORM ureport_insert_reporters_counter(_contact.org_id, CONCAT('gender:', LOWER(_contact.gender)), _count);
    END IF;
    IF _contact.born IS NOT NULL THEN
      PERFORM ureport_insert_reporters_counter(_contact.org_id, CONCAT('born:', LOWER(CAST(_contact.born AS VARCHAR ))), _count);
    END IF;
    IF _contact.occupation IS NOT NULL THEN
      PERFORM ureport_insert_reporters_counter(_contact.org_id, CONCAT('occupation:', LOWER(_contact.occupation)), _count);
    END IF;
    IF _contact.registered_on IS NOT NULL THEN
      PERFORM ureport_insert_reporters_counter(_contact.org_id, CONCAT('registered_on:', DATE(_contact.registered_on)), _count);
    END IF;
    IF _contact.state IS NOT NULL THEN
      PERFORM ureport_insert_reporters_counter(_contact.org_id, CONCAT('state:', UPPER(_contact.state)), _count);
      IF _contact.district IS NOT NULL THEN
        PERFORM ureport_insert_reporters_counter(_contact.org_id, CONCAT('district:', UPPER(_contact.district)), _count);
      END IF;
    END IF;
  END IF;
END;
$$ LANGUAGE plpgsql;
-----------------------------------------------------------------------------
-- Updates our reporters counters
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ureport_update_counters() RETURNS TRIGGER AS $$
BEGIN
  -- Contact being created, increment counters for contact NEW
  IF TG_OP = 'INSERT' THEN
    PERFORM ureport_increment_counter_for_contact(NEW, TRUE);
  ELSIF TG_OP = 'UPDATE' THEN
    -- If a contact is changed, decrement the counters for its OLD values
    PERFORM ureport_increment_counter_for_contact(OLD, FALSE);
    -- Then, increment the counters for its NEW values
    PERFORM ureport_increment_counter_for_contact(NEW, TRUE);
  -- Contact is being deleted
  ELSIF TG_OP = 'DELETE' THEN
    -- A contact is deleted, decrement all reporters counters for its values
    PERFORM ureport_increment_counter_for_contact(OLD, FALSE);
  -- Contacts table is being truncated
  ELSIF TG_OP = 'TRUNCATE' THEN
   -- Clear all counters
   TRUNCATE contacts_reporterscounter;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS ureport_when_contacts_update_then_update_counters on contacts_contact;
CREATE TRIGGER ureport_when_contacts_update_then_update_counters
  AFTER INSERT OR DELETE OR UPDATE ON contacts_contact
  FOR EACH ROW EXECUTE PROCEDURE ureport_update_counters();
DROP TRIGGER IF EXISTS ureport_when_contacts_truncate_then_update_counters ON contacts_contact;
CREATE TRIGGER ureport_when_contacts_truncate_then_update_counters
  AFTER TRUNCATE ON contacts_contact
  EXECUTE PROCEDURE ureport_update_counters();
"""


class Migration(migrations.Migration):
    dependencies = [("contacts", "0003_auto_20150918_0914")]

    operations = [migrations.RunSQL(TRIGGER_SQL)]
