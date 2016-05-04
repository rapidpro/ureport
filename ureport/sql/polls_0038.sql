DROP TRIGGER IF EXISTS ureport_when_poll_results_truncate_then_update_results_counters ON polls_pollresult;

DROP TRIGGER IF EXISTS ureport_when_poll_result_update_then_update_results_counters on polls_pollresult;

DROP FUNCTION IF EXISTS ureport_update_results_counters();

DROP FUNCTION IF EXISTS ureport_increment_counter_for_poll_result(_poll_result polls_pollresult, _add BOOLEAN);

DROP FUNCTION IF EXISTS ureport_insert_results_counter(_org_id INT, _ruleset CHAR(36), _type VARCHAR, _count INT);
