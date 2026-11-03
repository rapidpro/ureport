from django.db import migrations


class Migration(migrations.Migration):
    # A pattern-matching index on uuid left over from when the field was unique on its own: it predates Django's
    # current index naming, so the drop in 0023 missed it, and it only exists on databases created back then.
    # Contacts are only looked up by exact uuid within an org, which the org/uuid unique constraint covers. It's
    # dropped concurrently because the table takes constant writes.
    atomic = False

    dependencies = [
        ("contacts", "0032_reporterscounter_squashed_unique"),
    ]

    operations = [
        migrations.RunSQL('DROP INDEX CONCURRENTLY IF EXISTS "contacts_contact_uuid_1615f91d2f7b8c6_like"', ""),
    ]
