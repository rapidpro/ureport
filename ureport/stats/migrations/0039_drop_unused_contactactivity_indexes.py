from django.db import migrations

UNUSED_INDEXES = (
    "stats_contactactivity_org_id_age_date_not_null_used",
    "stats_contactactivity_org_id_date_gender_not_null_used",
    "stats_contactactivity_org_id_date_scheme_not_null_used",
    "stats_contactactivity_org_id_date_state_not_null_used",
    "stats_contactactivity_org_id_date_usedb",
)


class Migration(migrations.Migration):
    # These partial indexes were added by raw SQL in 0022, 0024 and 0025 for aggregating activity by age, gender,
    # scheme and state, which ContactActivityCounter has since taken over, so nothing queries them anymore. They're
    # dropped concurrently because the table takes constant writes.
    atomic = False

    dependencies = [
        ("stats", "0038_pollengagementdailycount_org_scope_day"),
    ]

    operations = [migrations.RunSQL(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"', "") for name in UNUSED_INDEXES]
