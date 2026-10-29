from django.db import migrations, models


class Migration(migrations.Migration):
    # Existing rows are all counted as squashed, by adding the column with a default of true, which doesn't rewrite
    # the table, and then switching the default to false for the deltas the contact triggers insert from now on.
    # Groups left with more than one squashed row are merged by the next migration. The old squash function is
    # dropped, as squashing is now done by ReportersCounter.squash.

    dependencies = [
        ("contacts", "0030_install_triggers"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                'ALTER TABLE "contacts_reporterscounter" ADD COLUMN "is_squashed" boolean NOT NULL DEFAULT true, '
                'ALTER COLUMN "is_squashed" SET DEFAULT false'
            ),
            reverse_sql='ALTER TABLE "contacts_reporterscounter" DROP COLUMN "is_squashed"',
            state_operations=[
                migrations.AddField(
                    model_name="reporterscounter",
                    name="is_squashed",
                    field=models.BooleanField(db_default=False, default=False),
                ),
            ],
        ),
        migrations.RunSQL("DROP FUNCTION IF EXISTS ureport_squash_reporterscounters(INT, VARCHAR)", migrations.RunSQL.noop),
    ]
