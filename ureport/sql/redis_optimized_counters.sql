-- Redis-optimized version of contact counter triggers
-- This reduces database I/O by deferring counter writes to Redis buffering

-- Modified function that uses Redis for counter buffering instead of immediate DB writes
CREATE OR REPLACE FUNCTION ureport_increment_counter_for_contact_redis(_contact contacts_contact, _add BOOLEAN)
RETURNS VOID AS $$
DECLARE
  _count INT;
  _redis_cmd TEXT;
BEGIN
  IF _add THEN
    _count = 1;
  ELSE
    _count = -1;
  END IF;
  
  -- If we have an org, buffer counter increments in Redis instead of immediate DB writes
  IF _contact.org_id IS NOT NULL THEN
    -- Use Redis HINCRBY to buffer counter increments
    -- Format: HINCRBY ureport:counter_buffer "org_id:type" count
    
    -- Total reporters counter
    PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer', 
      CONCAT(_contact.org_id, ':total-reporters'), _count::text);
    
    IF _contact.gender IS NOT NULL THEN
      PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
        CONCAT(_contact.org_id, ':gender:', LOWER(_contact.gender)), _count::text);
    END IF;
    
    IF _contact.born IS NOT NULL THEN
      PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
        CONCAT(_contact.org_id, ':born:', LOWER(CAST(_contact.born AS VARCHAR))), _count::text);
    END IF;
    
    IF _contact.occupation IS NOT NULL THEN
      PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
        CONCAT(_contact.org_id, ':occupation:', LOWER(_contact.occupation)), _count::text);
    END IF;
    
    IF _contact.state IS NOT NULL THEN
      PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
        CONCAT(_contact.org_id, ':state:', UPPER(_contact.state)), _count::text);
    END IF;
    
    IF _contact.district IS NOT NULL THEN
      PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
        CONCAT(_contact.org_id, ':district:', UPPER(_contact.district)), _count::text);
    END IF;
    
    IF _contact.ward IS NOT NULL THEN
      PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
        CONCAT(_contact.org_id, ':ward:', UPPER(_contact.ward)), _count::text);
    END IF;
    
    IF _contact.scheme IS NOT NULL THEN
      PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
        CONCAT(_contact.org_id, ':scheme:', LOWER(_contact.scheme)), _count::text);
    END IF;
    
    -- Handle registration-related counters
    IF _contact.registered_on IS NOT NULL THEN
      PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
        CONCAT(_contact.org_id, ':registered_on:', DATE(_contact.registered_on)), _count::text);
      
      IF _contact.gender IS NOT NULL THEN
        PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
          CONCAT(_contact.org_id, ':registered_gender:', DATE(date_trunc('day', _contact.registered_on)::timestamp), ':', LOWER(_contact.gender)), _count::text);
      END IF;
      
      IF _contact.born IS NOT NULL THEN
        PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
          CONCAT(_contact.org_id, ':registered_born:', DATE(date_trunc('day', _contact.registered_on)::timestamp), ':', LOWER(CAST(_contact.born AS VARCHAR))), _count::text);
      END IF;
      
      IF _contact.state IS NOT NULL THEN
        PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
          CONCAT(_contact.org_id, ':registered_state:', DATE(date_trunc('day', _contact.registered_on)::timestamp), ':', UPPER(_contact.state)), _count::text);
      END IF;
      
      IF _contact.scheme IS NOT NULL THEN
        PERFORM redis_command_sync('HINCRBY', 'ureport:counter_buffer',
          CONCAT(_contact.org_id, ':registered_scheme:', DATE(date_trunc('day', _contact.registered_on)::timestamp), ':', LOWER(_contact.scheme)), _count::text);
      END IF;
    END IF;
    
    -- Set expiration on the buffer hash to prevent infinite growth
    PERFORM redis_command_sync('EXPIRE', 'ureport:counter_buffer', '3600');
  END IF;
END;
$$ LANGUAGE plpgsql;

-- Note: This function requires the redis_fdw extension or similar Redis integration
-- Alternatively, this logic could be moved to the Django application layer

-- For immediate implementation without PostgreSQL Redis extension:
-- Keep the existing database counter function but add a Redis cache layer
-- in the Django models to reduce read operations

-- Cache frequently accessed counter totals in Redis
CREATE OR REPLACE FUNCTION ureport_get_cached_counter_total(_org_id INT, _type VARCHAR)
RETURNS INT AS $$
DECLARE
  _cached_total INT;
  _cache_key TEXT;
BEGIN
  _cache_key := CONCAT('counter_total:', _org_id, ':', _type);
  
  -- Try to get from Redis cache first (pseudo-code, requires Redis integration)
  -- _cached_total := redis_get(_cache_key);
  
  -- If not in cache, calculate from database and cache result
  -- IF _cached_total IS NULL THEN
    SELECT COALESCE(SUM(count), 0) INTO _cached_total
    FROM contacts_reporterscounter 
    WHERE org_id = _org_id AND type = _type;
    
    -- Cache for 5 minutes (pseudo-code)
    -- PERFORM redis_setex(_cache_key, 300, _cached_total::text);
  -- END IF;
  
  RETURN _cached_total;
END;
$$ LANGUAGE plpgsql;