from django.db import migrations, models

from ureport.utils.counts import get_merge_squashed_sql

# (model name, table, constraint name, fields, columns, whether NULLs are distinct, whether to lower fillfactor)
SQUASHED_CONSTRAINTS = (
    (
        "pollstatscounter",
        "stats_pollstatscounter",
        "stats_psc_squashed",
        ("org", "flow_result", "flow_result_category", "scope"),
        ("org_id", "flow_result_id", "flow_result_category_id", "scope"),
        False,
        True,
    ),
    (
        "pollengagementdailycount",
        "stats_pollengagementdailycount",
        "stats_pedc_squashed",
        ("org", "flow_result", "is_responded", "scope", "day"),
        ("org_id", "flow_result_id", "is_responded", "scope", "day"),
        False,
        True,
    ),
    # contact_activitycntr_org_count indexes count, so updates of squashed rows can't be HOT whatever the fillfactor
    (
        "contactactivitycounter",
        "stats_contactactivitycounter",
        "stats_cac_squashed",
        ("org", "date", "type", "value"),
        ("org_id", "date", "type", "value"),
        True,
        False,
    ),
)


def squashed_constraint_operations():
    operations = []
    for model_name, table, name, fields, columns, nulls_distinct, lower_fillfactor in SQUASHED_CONSTRAINTS:
        cols = ", ".join([f'"{col}"' for col in columns])
        nulls = "" if nulls_distinct else " NULLS NOT DISTINCT"

        operations += [
            migrations.RunSQL(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"'),
            migrations.RunSQL(get_merge_squashed_sql(table, columns)),
        ]
        if lower_fillfactor:
            operations.append(migrations.RunSQL(f"ALTER TABLE {table} SET (fillfactor = 85)"))
        operations += [
            migrations.RunSQL(
                sql=f'CREATE UNIQUE INDEX CONCURRENTLY "{name}" ON {table} ({cols}){nulls} WHERE "is_squashed"',
                state_operations=[
                    migrations.AddConstraint(
                        model_name=model_name,
                        constraint=models.UniqueConstraint(
                            condition=models.Q(("is_squashed", True)),
                            fields=fields,
                            name=name,
                            nulls_distinct=None if nulls_distinct else False,
                        ),
                    ),
                ],
            ),
        ]
    return operations


class Migration(migrations.Migration):
    # Squashing upserts the single squashed row of each set of counts, which needs a unique index over the squashed
    # rows - so any sets with more than one are merged first. The index is built concurrently because these tables
    # take constant writes, and fillfactor is lowered on the poll counter tables to leave room on each page for
    # squashed rows to be updated in place. Each index is dropped first, so that one left invalid by a failed build
    # doesn't stop the migration being re-run. The NULLS NOT DISTINCT indexes need PostgreSQL 15 or later.
    #
    # The merge doesn't hold the stats squash lock, so poll syncs should be paused while this runs: a poll's counter
    # rebuild that interleaves with the merge can leave a merged duplicate beside the rebuilt rows, failing the index
    # build, and a re-run would then merge them and double that question's counts until it is next rebuilt.
    #
    # Installations large enough to care can merge duplicates and run the following ahead of the deploy, and fake
    # this migration:
    #
    #   ALTER TABLE stats_pollstatscounter SET (fillfactor = 85);
    #   CREATE UNIQUE INDEX CONCURRENTLY "stats_psc_squashed" ON stats_pollstatscounter ("org_id", "flow_result_id", "flow_result_category_id", "scope") NULLS NOT DISTINCT WHERE "is_squashed";
    #   ALTER TABLE stats_pollengagementdailycount SET (fillfactor = 85);
    #   CREATE UNIQUE INDEX CONCURRENTLY "stats_pedc_squashed" ON stats_pollengagementdailycount ("org_id", "flow_result_id", "is_responded", "scope", "day") NULLS NOT DISTINCT WHERE "is_squashed";
    #   CREATE UNIQUE INDEX CONCURRENTLY "stats_cac_squashed" ON stats_contactactivitycounter ("org_id", "date", "type", "value") WHERE "is_squashed";
    #
    atomic = False

    dependencies = [
        ("stats", "0033_backfill_poll_stats_counters_dedupes"),
    ]

    operations = squashed_constraint_operations()
