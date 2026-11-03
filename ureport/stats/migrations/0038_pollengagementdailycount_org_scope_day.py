from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    # Built concurrently because this table takes writes whenever polls sync. The index is dropped first, so that one
    # left invalid by a failed build doesn't stop the migration being re-run. Installations large enough to care can
    # run the following ahead of the deploy, and fake this migration:
    #
    #   CREATE INDEX CONCURRENTLY "stats_pedc_org_scope_day" ON stats_pollengagementdailycount ("org_id", "scope", "day") INCLUDE ("flow_result_id", "is_responded", "count");
    #
    atomic = False

    dependencies = [
        ("stats", "0037_activeuserscheckpoint_history"),
    ]

    operations = [
        migrations.RunSQL('DROP INDEX CONCURRENTLY IF EXISTS "stats_pedc_org_scope_day"', migrations.RunSQL.noop),
        AddIndexConcurrently(
            model_name="pollengagementdailycount",
            index=models.Index(
                fields=["org", "scope", "day"],
                include=("flow_result", "is_responded", "count"),
                name="stats_pedc_org_scope_day",
            ),
        ),
    ]
