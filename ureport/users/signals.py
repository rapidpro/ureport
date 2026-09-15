from allauth.account.models import EmailAddress
from allauth.account.signals import email_changed

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


def sync_email_address(user):
    """
    Keeps a single verified, primary allauth email address in step with the user's email field. Accounts are only ever
    created by staff or by accepting an emailed invitation, so the address is trusted without a confirmation round trip.
    """
    if not user.email:
        return

    existing = user.emailaddress_set.filter(email__iexact=user.email).first()
    if existing and existing.verified and existing.primary:
        return

    with_email = EmailAddress.objects.filter(email__iexact=user.email).exclude(user=user)
    if with_email.exists():
        return  # another account already owns this address, leave it for staff to sort out

    user.emailaddress_set.exclude(email__iexact=user.email).delete()
    EmailAddress.objects.update_or_create(
        user=user, email__iexact=user.email, defaults={"email": user.email, "verified": True, "primary": True}
    )


@receiver(post_save, sender=User)
def on_user_saved(sender, instance, raw, **kwargs):
    if not raw:
        sync_email_address(instance)


@receiver(email_changed)
def on_email_changed(sender, request, user, from_email_address, to_email_address, **kwargs):
    # users created through the org invitation flow have their username set to their email so keep that in step
    if from_email_address and user.username == from_email_address.email:
        if not User.objects.filter(username=user.email).exclude(pk=user.pk).exists():
            user.username = user.email
            user.save(update_fields=("username",))
