-----------------------------------------------------------------------------
-- Insert missing PollContactResult's ContactEngagementActivity rows
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
    ureport_insert_missing_contact_engagement_activities(_poll_contact_result stats_pollcontactresult)
RETURNS VOID AS $$
BEGIN
    INSERT INTO stats_contactengagementactivity(contact, date, org_id) WITH month_days(missing_month) AS (
        SELECT generate_series(date_trunc('month', _poll_contact_result.date)::timestamp,(date_trunc('month', _poll_contact_result.date)::timestamp+ interval '11 months')::date,interval '1 month')::date
    ), curr_activity AS (
    SELECT * FROM stats_contactengagementactivity WHERE org_id = _poll_contact_result.org_id and contact = _poll_contact_result.contact
    ) SELECT _poll_contact_result.contact, missing_month::date, _poll_contact_result.org_id  FROM month_days LEFT JOIN stats_contactengagementactivity ON stats_contactengagementactivity.date = month_days.missing_month AND stats_contactengagementactivity.contact = _poll_contact_result.contact AND org_id = _poll_contact_result.org_id
    WHERE stats_contactengagementactivity.date IS NULL;
    UPDATE stats_contactengagementactivity SET age_segment_id = _poll_contact_result.age_segment_id, gender_segment_id = _poll_contact_result.gender_segment_id, location_id = _poll_contact_result.location_id, scheme_segment_id = _poll_contact_result.scheme_segment_id, used = TRUE WHERE org_id = _poll_contact_result.org_id and contact = _poll_contact_result.contact and date > date_trunc('month', CURRENT_DATE) - INTERVAL '1 year';
END;
$$ LANGUAGE plpgsql;

-----------------------------------------------------------------------------
-- Generate ContactEngagementActivity rows for latest PollContactResult
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION generate_contact_engagement_activities_for_latest_poll_contact_result(_poll_contact_result stats_pollcontactresult)
RETURNS VOID AS $$
BEGIN
  -- Count only if we have an org and a flow and a flow_result
  IF _poll_contact_result.org_id IS NOT NULL AND _poll_contact_result.flow IS NOT NULL AND _poll_contact_result.flow_result_id IS NOT NULL AND _poll_contact_result.flow_result_category_id IS NOT NULL THEN
    PERFORM ureport_insert_missing_contact_engagement_activities(_poll_contact_result);
  END IF;
END;
$$ LANGUAGE plpgsql;

-----------------------------------------------------------------------------
-- Updates our results counters
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ureport_update_contact_engagement_activities() RETURNS TRIGGER AS $$
BEGIN
  -- PollContactResult row being created, increment counters for PollContactResult NEW
  IF TG_OP = 'INSERT' THEN
    PERFORM generate_contact_engagement_activities_for_latest_poll_contact_result(NEW);
  ELSIF TG_OP = 'UPDATE' THEN
    PERFORM generate_contact_engagement_activities_for_latest_poll_contact_result(NEW);
  -- PollContactResult row is being deleted
  ELSIF TG_OP = 'TRUNCATE' THEN
   -- Clear all ContactEngagementActivity rows
   TRUNCATE stats_contactengagementactivity;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;


-- Install trigger for INSERT, UPDATE, AND DELETE on stats_pollcontactresult
DROP TRIGGER IF EXISTS ureport_when_poll_contact_result_contact_engagement_activities on stats_pollcontactresult;
CREATE TRIGGER ureport_when_poll_contact_result_contact_engagement_activities
  AFTER INSERT OR DELETE OR UPDATE ON stats_pollcontactresult
  FOR EACH ROW EXECUTE PROCEDURE ureport_update_contact_engagement_activities();

-- Install trigger for TRUNCATE on stats_pollcontactresult
DROP TRIGGER IF EXISTS ureport_when_poll_contact_results_truncate_then_update_contact_engagement_activities ON stats_pollcontactresult;
CREATE TRIGGER ureport_when_poll_contact_results_truncate_then_update_contact_engagement_activities
  AFTER TRUNCATE ON stats_pollcontactresult
  EXECUTE PROCEDURE ureport_update_contact_engagement_activities();