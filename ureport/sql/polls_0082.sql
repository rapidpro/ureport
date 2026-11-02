-----------------------------------------------------------------------------
-- Insert missing poll results contact activities
--
-- Two transactions saving results for the same contact can both find a month
-- missing and both insert it, so the month is left to whichever inserts it
-- first, rather than the other failing on the unique constraint and rolling
-- back every result it is saving.
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
    -- the join keeps the conflicts to rows that race, as each one attempted still takes an id from the sequence
    LEFT JOIN stats_contactactivity
        ON stats_contactactivity.date = month_days.missing_month
        AND stats_contactactivity.contact = _poll_result.contact
        AND org_id = _poll_result.org_id
    WHERE stats_contactactivity.date IS NULL
    ON CONFLICT (org_id, contact, date) DO NOTHING;
END;
$$ LANGUAGE plpgsql;
