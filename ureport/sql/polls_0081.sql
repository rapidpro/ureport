-----------------------------------------------------------------------------
-- Insert missing poll results contact activities
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
    ureport_insert_missing_contact_activities(_poll_result polls_pollresult)
RETURNS VOID AS $$
BEGIN
    INSERT INTO stats_contactactivity(contact, date, org_id, born, gender, state, district, ward, scheme, used) 
    WITH month_days(missing_month) AS (
        SELECT generate_series(
            date_trunc('month', _poll_result.date)::timestamp,
            (date_trunc('month', _poll_result.date)::timestamp + interval '11 months')::date,
            interval '1 month'
        )::date
    )
    SELECT _poll_result.contact, missing_month::date, _poll_result.org_id, _poll_result.born, _poll_result.gender, _poll_result.state, _poll_result.district, _poll_result.ward, _poll_result.scheme, True
    FROM month_days
    LEFT JOIN stats_contactactivity
        ON stats_contactactivity.date = month_days.missing_month
        AND stats_contactactivity.contact = _poll_result.contact
        AND org_id = _poll_result.org_id
    WHERE stats_contactactivity.date IS NULL;
END;
$$ LANGUAGE plpgsql;

-----------------------------------------------------------------------------
-- Generate contact activities for latest poll result
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION generate_contact_activities_for_latest_poll_result(_poll_result polls_pollresult)
RETURNS VOID AS $$
BEGIN
  -- Count only if we have an org and a flow and a ruleset
  IF _poll_result.org_id IS NOT NULL AND _poll_result.flow IS NOT NULL AND _poll_result.ruleset IS NOT NULL AND _poll_result.category IS NOT NULL THEN
    PERFORM ureport_insert_missing_contact_activities(_poll_result);
  END IF;
END;
$$ LANGUAGE plpgsql;


-----------------------------------------------------------------------------
-- Updates our results counters
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ureport_update_contact_activities() RETURNS TRIGGER AS $$
BEGIN
  -- PollResult being created, increment counters for poll_result NEW
  IF TG_OP = 'INSERT' THEN
    PERFORM generate_contact_activities_for_latest_poll_result(NEW);
  ELSIF TG_OP = 'UPDATE' THEN
    PERFORM generate_contact_activities_for_latest_poll_result(NEW);
  -- poll_result is being deleted
  ELSIF TG_OP = 'TRUNCATE' THEN
   -- Clear all contact_activities
   TRUNCATE stats_contactactivity;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Install trigger for INSERT, UPDATE, AND DELETE on polls_pollresult
DROP TRIGGER IF EXISTS ureport_when_poll_result_contact_activities on polls_pollresult;
CREATE TRIGGER ureport_when_poll_result_contact_activities
  AFTER INSERT OR DELETE OR UPDATE ON polls_pollresult
  FOR EACH ROW EXECUTE PROCEDURE ureport_update_contact_activities();

-- Install trigger for TRUNCATE on polls_pollresult
DROP TRIGGER IF EXISTS ureport_when_poll_results_truncate_then_update_contact_activities ON polls_pollresult;
CREATE TRIGGER ureport_when_poll_results_truncate_then_update_contact_activities
  AFTER TRUNCATE ON polls_pollresult
  EXECUTE PROCEDURE ureport_update_contact_activities();