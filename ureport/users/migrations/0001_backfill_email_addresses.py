import logging

from django.db import migrations
from django.db.models import F

logger = logging.getLogger(__name__)


def backfill_email_addresses(apps, schema_editor):
    """
    Existing users have been logging in with the email on their user record so treat it as verified. Where several
    users share an address only the one who logged in most recently gets it and the others are reported.
    """
    User = apps.get_model("auth", "User")
    EmailAddress = apps.get_model("account", "EmailAddress")

    taken = {e.lower() for e in EmailAddress.objects.values_list("email", flat=True)}
    users_with_address = set(EmailAddress.objects.values_list("user_id", flat=True))

    users = (
        User.objects.exclude(email="")
        .exclude(id__in=users_with_address)
        .order_by(F("last_login").desc(nulls_last=True), "id")
    )
    for user in users:
        email = user.email.strip().lower()
        if email in taken:
            logger.warning("skipping user %s (%s) as that email already belongs to another account", user.pk, email)
            continue

        EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
        taken.add(email)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("account", "0009_emailaddress_unique_primary_email"),
    ]

    operations = [migrations.RunPython(backfill_email_addresses, migrations.RunPython.noop)]
