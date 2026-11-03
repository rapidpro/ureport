from django.db import migrations

# the triggers and functions installed by stats_0028.sql that kept stats_contactactivitycounter in step with
# stats_contactactivity
DROP_SQL = """
DROP TRIGGER IF EXISTS ureport_when_activity_update_then_update_activity_counters ON stats_contactactivity;
DROP TRIGGER IF EXISTS ureport_when_contacts_truncate_then_update_counters ON stats_contactactivity;
DROP FUNCTION IF EXISTS ureport_update_activity_counters();
DROP FUNCTION IF EXISTS ureport_increment_counter_for_activity(stats_contactactivity, BOOLEAN);
DROP FUNCTION IF EXISTS ureport_insert_activity_counter(INT, DATE, VARCHAR, VARCHAR, INT);
"""

# the sync jobs that pruned the activities, rebuilt their counters and backfilled their schemes, which no task runs
# anymore
JOB_TYPES = ("activities-prune", "activities-rebuild", "schemes-activities")


def delete_jobs(apps, schema_editor):
    SyncJob = apps.get_model("syncjobs", "SyncJob")
    SyncJob.objects.filter(job_type__in=JOB_TYPES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("polls", "0084_drop_contact_activity_triggers"),
        ("stats", "0039_drop_unused_contactactivity_indexes"),
        ("syncjobs", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(DROP_SQL, ""),
        migrations.DeleteModel(name="ContactActivityCounter"),
        migrations.DeleteModel(name="ContactActivity"),
        migrations.RunPython(delete_jobs, migrations.RunPython.noop),
    ]
