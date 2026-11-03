from django.db import migrations

# the triggers and functions installed by polls_0081.sql and polls_0082.sql that wrote every result into
# stats_contactactivity, which is dropped by stats 0040
DROP_SQL = """
DROP TRIGGER IF EXISTS ureport_when_poll_result_contact_activities ON polls_pollresult;
DROP TRIGGER IF EXISTS ureport_when_poll_results_truncate_then_update_contact_activities ON polls_pollresult;
DROP FUNCTION IF EXISTS ureport_update_contact_activities();
DROP FUNCTION IF EXISTS generate_contact_activities_for_latest_poll_result(polls_pollresult);
DROP FUNCTION IF EXISTS ureport_insert_missing_contact_activities(polls_pollresult);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("polls", "0083_flowsyncstate"),
    ]

    operations = [migrations.RunSQL(DROP_SQL, "")]
