from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    # Built concurrently because this table takes constant writes. Installations large enough to care can run the
    # following ahead of the deploy, and fake this migration:
    #
    #   CREATE INDEX CONCURRENTLY "stats_pedc_org_scope_day" ON stats_pollengagementdailycount ("org_id", "scope", "day") INCLUDE ("flow_result_id", "is_responded", "count");
    #
    atomic = False

    dependencies = [
        ("stats", "0037_activeuserscheckpoint_history"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="pollengagementdailycount",
            index=models.Index(
                fields=["org", "scope", "day"],
                include=("flow_result", "is_responded", "count"),
                name="stats_pedc_org_scope_day",
            ),
        ),
    ]
