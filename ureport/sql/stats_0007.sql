-----------------------------------------------------------------------------
-- Squash the poll stats by gathering the stats in one row
-----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION
  ureport_squash_pollstats(_org_id INT, _question_id INT, _category_id INT, _age_segment_id INT, _gender_segment_id INT, _location_id INT, _date TIMESTAMP WITH TIME ZONE)
RETURNS VOID AS $$
BEGIN
  WITH deleted as (
    DELETE FROM stats_pollstats WHERE "id" IN (
      SELECT "id" FROM stats_pollstats
      WHERE "org_id" IS NOT DISTINCT FROM _org_id AND "question_id" IS NOT DISTINCT FROM _question_id AND "category_id" IS NOT DISTINCT FROM _category_id AND "age_segment_id" IS NOT DISTINCT FROM _age_segment_id AND "gender_segment_id" IS NOT DISTINCT FROM _gender_segment_id AND "location_id" IS NOT DISTINCT FROM _location_id AND "date" IS NOT DISTINCT FROM date_trunc('day', _date)::TIMESTAMP
      LIMIT 10000
    ) 
    RETURNING "count" )
    INSERT INTO stats_pollstats("org_id", "question_id", "category_id", "age_segment_id", "gender_segment_id", "location_id", "date", "count")
    VALUES (_org_id, _question_id, _category_id, _age_segment_id, _gender_segment_id, _location_id, date_trunc('day', _date)::TIMESTAMP, GREATEST(0, (SELECT SUM("count") FROM deleted)));
END;
$$ LANGUAGE plpgsql;
