from django_valkey import get_valkey_connection

from django.db import migrations, models

LOCK_KEY = "org-reporters-counts-squash-lock"
LOCK_TIMEOUT = 60 * 60

# merges each group's squashed rows into one, dropping it if it doesn't sum above zero, as squashing would
MERGE_SQUASHED_SQL = """
WITH groups AS (
    SELECT "org_id", "type" FROM contacts_reporterscounter WHERE "is_squashed"
    GROUP BY "org_id", "type" HAVING COUNT(*) > 1 OR MIN("count") <= 0
), removed AS (
    DELETE FROM contacts_reporterscounter c USING groups g
    WHERE c."is_squashed" AND c."org_id" = g."org_id" AND c."type" = g."type"
    RETURNING c."org_id", c."type", c."count"
)
INSERT INTO contacts_reporterscounter ("org_id", "type", "count", "is_squashed")
SELECT "org_id", "type", SUM("count"), TRUE FROM removed GROUP BY "org_id", "type" HAVING SUM("count") > 0;
"""


def merge_squashed(apps, schema_editor):  # pragma: no cover
    # hold the squash lock so an org's counters can't be rebuilt part way through the merge
    lock = get_valkey_connection().lock(LOCK_KEY, timeout=LOCK_TIMEOUT, blocking_timeout=LOCK_TIMEOUT)
    if not lock.acquire():
        raise Exception("Couldn't acquire the reporters squash lock to merge squashed counters")

    try:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(MERGE_SQUASHED_SQL)
    finally:
        lock.release()


class Migration(migrations.Migration):
    # Squashing upserts each group's single squashed row, which needs a unique index over the squashed rows, so any
    # groups with more than one are merged first. The indexes are built concurrently because the contact triggers
    # write to this table constantly, and each is dropped first so that one left invalid by a failed build doesn't
    # stop the migration being re-run.
    #
    # Installations large enough to care can run the merge and the following ahead of the deploy, and fake this
    # migration:
    #
    #   CREATE UNIQUE INDEX CONCURRENTLY "contacts_rptrscntr_squashed" ON contacts_reporterscounter ("org_id", "type") WHERE "is_squashed";
    #   CREATE INDEX CONCURRENTLY "contacts_rptrscntr_unsquashed" ON contacts_reporterscounter ("org_id", "type") WHERE NOT "is_squashed";
    #
    atomic = False

    dependencies = [
        ("contacts", "0031_reporterscounter_is_squashed"),
    ]

    operations = [
        migrations.RunPython(merge_squashed, migrations.RunPython.noop),
        migrations.RunSQL('DROP INDEX CONCURRENTLY IF EXISTS "contacts_rptrscntr_squashed"'),
        migrations.RunSQL(
            sql=(
                'CREATE UNIQUE INDEX CONCURRENTLY "contacts_rptrscntr_squashed" '
                'ON contacts_reporterscounter ("org_id", "type") WHERE "is_squashed"'
            ),
            reverse_sql='DROP INDEX CONCURRENTLY IF EXISTS "contacts_rptrscntr_squashed"',
            state_operations=[
                migrations.AddConstraint(
                    model_name="reporterscounter",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(("is_squashed", True)),
                        fields=("org", "type"),
                        name="contacts_rptrscntr_squashed",
                    ),
                ),
            ],
        ),
        migrations.RunSQL('DROP INDEX CONCURRENTLY IF EXISTS "contacts_rptrscntr_unsquashed"'),
        migrations.RunSQL(
            sql=(
                'CREATE INDEX CONCURRENTLY "contacts_rptrscntr_unsquashed" '
                'ON contacts_reporterscounter ("org_id", "type") WHERE NOT "is_squashed"'
            ),
            reverse_sql='DROP INDEX CONCURRENTLY IF EXISTS "contacts_rptrscntr_unsquashed"',
            state_operations=[
                migrations.AddIndex(
                    model_name="reporterscounter",
                    index=models.Index(
                        condition=models.Q(("is_squashed", False)),
                        fields=["org", "type"],
                        name="contacts_rptrscntr_unsquashed",
                    ),
                ),
            ],
        ),
    ]
