-----------------------------------------------------------------------------
-- Increment or decrement the reporters count on counter of given type
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
  ureport_insert_reporters_counter(_org_id INT, _type VARCHAR, _count INT)
RETURNS VOID AS $$
BEGIN
  INSERT INTO contacts_reporterscounter("org_id", "type", "count") VALUES(_org_id, _type, _count);
END;
$$ LANGUAGE plpgsql;
-----------------------------------------------------------------------------
-- Increment counters for a contact
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ureport_increment_counter_for_contact(_contact contacts_contact, _add BOOLEAN)
RETURNS VOID AS $$
DECLARE
  _count INT;
  _counters TEXT[];
  _counter TEXT;
BEGIN
  IF _add THEN
    _count = 1;
  ELSE
    _count = -1;
  END IF;
  
  -- If we have a org, batch all counter increments into fewer operations
  IF _contact.org_id IS NOT NULL THEN
    -- Collect all counter types to insert in a single batch
    _counters := ARRAY['total-reporters'];
    
    IF _contact.gender IS NOT NULL THEN
      _counters := _counters || ARRAY[CONCAT('gender:', LOWER(_contact.gender))];
    END IF;
    IF _contact.born IS NOT NULL THEN
      _counters := _counters || ARRAY[CONCAT('born:', LOWER(CAST(_contact.born AS VARCHAR)))];
    END IF;
    IF _contact.occupation IS NOT NULL THEN
      _counters := _counters || ARRAY[CONCAT('occupation:', LOWER(_contact.occupation))];
    END IF;
    IF _contact.state IS NOT NULL THEN
      _counters := _counters || ARRAY[CONCAT('state:', UPPER(_contact.state))];
    END IF;
    IF _contact.district IS NOT NULL THEN
      _counters := _counters || ARRAY[CONCAT('district:', UPPER(_contact.district))];
    END IF;
    IF _contact.ward IS NOT NULL THEN
      _counters := _counters || ARRAY[CONCAT('ward:', UPPER(_contact.ward))];
    END IF;
    IF _contact.scheme IS NOT NULL THEN
      _counters := _counters || ARRAY[CONCAT('scheme:', LOWER(_contact.scheme))];
    END IF;
    
    -- Batch insert all basic counters
    INSERT INTO contacts_reporterscounter("org_id", "type", "count")
    SELECT _contact.org_id, unnest(_counters), _count;
    
    -- Handle registration-related counters only if registered_on exists
    IF _contact.registered_on IS NOT NULL THEN
      _counters := ARRAY[CONCAT('registered_on:', DATE(_contact.registered_on))];
      
      IF _contact.gender IS NOT NULL THEN
        _counters := _counters || ARRAY[CONCAT('registered_gender:', DATE(date_trunc('day', _contact.registered_on)::timestamp), ':', LOWER(_contact.gender))];
      END IF;
      IF _contact.born IS NOT NULL THEN
        _counters := _counters || ARRAY[CONCAT('registered_born:', DATE(date_trunc('day', _contact.registered_on)::timestamp), ':', LOWER(CAST(_contact.born AS VARCHAR)))];
      END IF;
      IF _contact.state IS NOT NULL THEN
        _counters := _counters || ARRAY[CONCAT('registered_state:', DATE(date_trunc('day', _contact.registered_on)::timestamp), ':', UPPER(_contact.state))];
      END IF;
      IF _contact.scheme IS NOT NULL THEN
        _counters := _counters || ARRAY[CONCAT('registered_scheme:', DATE(date_trunc('day', _contact.registered_on)::timestamp), ':', LOWER(_contact.scheme))];
      END IF;
      
      -- Batch insert all registration counters
      INSERT INTO contacts_reporterscounter("org_id", "type", "count")
      SELECT _contact.org_id, unnest(_counters), _count;
    END IF;
  END IF;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION ureport_adjust_counter_for_contact(_new_contact contacts_contact, _old_contact contacts_contact)
RETURNS VOID AS $$
BEGIN
  -- no org id, decrement all reporters counters for its previous values
  IF _new_contact.org_id IS NULL THEN
    PERFORM ureport_increment_counter_for_contact(_old_contact, FALSE);
  ELSIF _new_contact.is_active != _old_contact.is_active THEN
    PERFORM ureport_increment_counter_for_contact(_old_contact, _new_contact.is_active);
  ELSIF _new_contact.org_id = _old_contact.org_id THEN
    IF _new_contact.gender != _old_contact.gender THEN
      PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('gender:', LOWER(_old_contact.gender)), -1);
      PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('gender:', LOWER(_new_contact.gender)), 1);
    END IF;
    IF _new_contact.born != _old_contact.born THEN
      PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('born:', LOWER(CAST(_old_contact.born AS VARCHAR ))), -1);
      PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('born:', LOWER(CAST(_new_contact.born AS VARCHAR ))), 1);
    END IF;
    IF _new_contact.occupation != _old_contact.occupation THEN
      PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('occupation:', LOWER(_old_contact.occupation)), -1);
      PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('occupation:', LOWER(_new_contact.occupation)), 1);
    END IF;
    IF _new_contact.registered_on != _old_contact.registered_on THEN
      PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('registered_on:', DATE(_old_contact.registered_on)), -1);
      PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('registered_on:', DATE(_new_contact.registered_on)), 1);
      IF _new_contact.gender != _old_contact.gender THEN
        PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('registered_gender:', DATE(date_trunc('day', _old_contact.registered_on)::timestamp), ':', LOWER(_old_contact.gender)), -1);
        PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('registered_gender:', DATE(date_trunc('day', _new_contact.registered_on)::timestamp), ':', LOWER(_new_contact.gender)), 1);
      END IF;

      IF _new_contact.born != _old_contact.born THEN
        PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('registered_born:', DATE(date_trunc('day', _old_contact.registered_on)::timestamp), ':', LOWER(CAST(_old_contact.born AS VARCHAR ))), -1);
        PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('registered_born:', DATE(date_trunc('day', _new_contact.registered_on)::timestamp), ':', LOWER(CAST(_new_contact.born AS VARCHAR ))), 1);
      END IF;

      IF _new_contact.state != _old_contact.state THEN
        PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('registered_state:', DATE(date_trunc('day', _old_contact.registered_on)::timestamp), ':', UPPER(_old_contact.state)), -1);
        PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('registered_state:', DATE(date_trunc('day', _new_contact.registered_on)::timestamp), ':', UPPER(_new_contact.state)), 1);
      END IF;

      IF _new_contact.scheme != _old_contact.scheme THEN
        PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('registered_scheme:', DATE(date_trunc('day', _old_contact.registered_on)::timestamp), ':', LOWER(_old_contact.scheme)), -1);
        PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('registered_scheme:', DATE(date_trunc('day', _new_contact.registered_on)::timestamp), ':', LOWER(_new_contact.scheme)), 1);
      END IF;

    END IF;
    IF _new_contact.state != _old_contact.state THEN
      PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('state:', UPPER(_old_contact.state)), -1);
      PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('state:', UPPER(_new_contact.state)), 1);
    END IF;
    IF _new_contact.district != _old_contact.district THEN
      PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('district:', UPPER(_old_contact.district)), -1);
      PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('district:', UPPER(_new_contact.district)), 1);
    END IF;
    IF _new_contact.ward != _old_contact.ward THEN
      PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('ward:', UPPER(_old_contact.ward)), -1);
      PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('ward:', UPPER(_new_contact.ward)), 1);
    END IF;

    IF _new_contact.scheme != _old_contact.scheme THEN
      PERFORM ureport_insert_reporters_counter(_old_contact.org_id, CONCAT('scheme:', LOWER(_old_contact.scheme)), -1);
      PERFORM ureport_insert_reporters_counter(_new_contact.org_id, CONCAT('scheme:', LOWER(_new_contact.scheme)), 1);
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
    -- If a contact is changed, adjust the counters
    PERFORM ureport_adjust_counter_for_contact(NEW, OLD);
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

-- Install trigger on INSERT DELETE OR UPDATE on contacts_contact
DROP TRIGGER IF EXISTS ureport_when_contacts_update_then_update_counters on contacts_contact;
CREATE TRIGGER ureport_when_contacts_update_then_update_counters
  AFTER INSERT OR DELETE OR UPDATE ON contacts_contact
  FOR EACH ROW EXECUTE PROCEDURE ureport_update_counters();

-- Install trigger on TRUNCATE on contacts_contact
DROP TRIGGER IF EXISTS ureport_when_contacts_truncate_then_update_counters ON contacts_contact;
CREATE TRIGGER ureport_when_contacts_truncate_then_update_counters
  AFTER TRUNCATE ON contacts_contact
  EXECUTE PROCEDURE ureport_update_counters();

-----------------------------------------------------------------------------
-- Squash the counters by gathering the counts in one row
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
  ureport_squash_reporterscounters(_org_id INT, _type VARCHAR)
RETURNS VOID AS $$
BEGIN
  WITH deleted as (DELETE FROM contacts_reporterscounter
    WHERE "org_id" = _org_id AND "type" = _type
    RETURNING "count")
    INSERT INTO contacts_reporterscounter("org_id", "type", "count")
    VALUES (_org_id, _type ,GREATEST(0, (SELECT SUM("count") FROM deleted)));
END;
$$ LANGUAGE plpgsql;
