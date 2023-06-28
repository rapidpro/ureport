
-----------------------------------------------------------------------------
-- Increment or decrement the activity count on counter of given type
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
  ureport_insert_activity_counter(_org_id INT, _date DATE, _type VARCHAR, _value VARCHAR, _count INT)
RETURNS VOID AS $$
BEGIN
  INSERT INTO stats_contactactivitycounter("org_id", "date", "type", "value", "count", "is_squashed") VALUES(_org_id, _date, _type, _value, _count, FALSE);
END;
$$ LANGUAGE plpgsql;

----------------------------------------------------------------------------
-- Increment counters for a contact activity
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ureport_increment_counter_for_activity(_activity stats_contactactivity, _add BOOLEAN)
RETURNS VOID AS $$
DECLARE
  _count INT;
BEGIN
  IF _add THEN
    _count = 1;
  ELSE
    _count = -1;
  END IF;
  -- If we have a org, increment all activity counters for its values
  IF _activity.org_id IS NOT NULL THEN

    PERFORM ureport_insert_activity_counter(_activity.org_id, _activity.date, 'A', '', _count);

    IF _activity.born IS NOT NULL THEN
      PERFORM ureport_insert_activity_counter(_activity.org_id, _activity.date, 'B', (EXTRACT('year' FROM _activity.date::date) - _activity.born)::VARCHAR, _count);
    END IF;

    IF _activity.gender IS NOT NULL THEN
      PERFORM ureport_insert_activity_counter(_activity.org_id, _activity.date, 'G', _activity.gender, _count);
    END IF;

    IF _activity.state IS NOT NULL THEN
      PERFORM ureport_insert_activity_counter(_activity.org_id, _activity.date, 'L', _activity.state, _count);
    END IF;

    IF _activity.scheme IS NOT NULL THEN
      PERFORM ureport_insert_activity_counter(_activity.org_id, _activity.date, 'S', _activity.scheme, _count);
    END IF;

  END IF;
END;
$$ LANGUAGE plpgsql;

-----------------------------------------------------------------------------
-- Updates our activity counters
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ureport_update_activity_counters() RETURNS TRIGGER AS $$
BEGIN
  -- Activity being created, increment activity counters for activity NEW
  IF TG_OP = 'INSERT' THEN
    PERFORM ureport_increment_counter_for_activity(NEW, TRUE);
  ELSIF TG_OP = 'UPDATE' THEN
    -- If a activity is changed, adjust the activity counters
    PERFORM ureport_increment_counter_for_activity(NEW, TRUE);
    PERFORM ureport_increment_counter_for_activity(OLD, FALSE);
  -- Activity is being deleted
  ELSIF TG_OP = 'DELETE' THEN
    -- A activity is deleted, decrement all activity counters for its values
    PERFORM ureport_increment_counter_for_activity(OLD, FALSE);
  -- Activities table is being truncated
  ELSIF TG_OP = 'TRUNCATE' THEN
   -- Clear all activity counters
   TRUNCATE stats_contactactivitycounter;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;


-- Install trigger on INSERT DELETE OR UPDATE on stats_contactactivity
DROP TRIGGER IF EXISTS ureport_when_activity_update_then_update_activity_counters on stats_contactactivity;
CREATE TRIGGER ureport_when_activity_update_then_update_activity_counters
  AFTER INSERT OR DELETE OR UPDATE ON stats_contactactivity
  FOR EACH ROW EXECUTE PROCEDURE ureport_update_activity_counters();

-- Install trigger on TRUNCATE on stats_contactactivity
DROP TRIGGER IF EXISTS ureport_when_contacts_truncate_then_update_counters ON stats_contactactivity;
CREATE TRIGGER ureport_when_contacts_truncate_then_update_counters
  AFTER TRUNCATE ON stats_contactactivity
  EXECUTE PROCEDURE ureport_update_activity_counters();
