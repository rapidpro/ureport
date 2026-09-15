import logging

from allauth.account.models import EmailAddress
from allauth.account.signals import email_changed

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

User = get_user_model()


def sync_email_address(user):
    """
    Keeps a single verified, primary allauth email address in step with the user's email field. Accounts are only ever
    created by staff or by accepting an emailed invitation, so the address is trusted without a confirmation round trip.
    """
    email = user.email

    # an address the user no longer has must stop working as a login
    user.emailaddress_set.exclude(email=email).delete()

    if not email:
        return

    if user.emailaddress_set.filter(email=email, verified=True, primary=True).exists():
        return

    if EmailAddress.objects.filter(email=email).exclude(user=user).exists():
        logger.warning("user %s has email %s which already belongs to another account", user.pk, email)
        return

    EmailAddress.objects.update_or_create(user=user, email=email, defaults={"verified": True, "primary": True})


@receiver(pre_save, sender=User)
def on_user_pre_save(sender, instance, raw, **kwargs):
    # allauth stores and looks up emails in lowercase, so keep the user's email that way too
    if not raw and instance.email:
        instance.email = instance.email.strip().lower()


@receiver(post_save, sender=User)
def on_user_saved(sender, instance, raw, **kwargs):
    if not raw:
        sync_email_address(instance)


@receiver(email_changed)
def on_email_changed(sender, request, user, from_email_address, to_email_address, **kwargs):
    # users created through the org invitation flow have their username set to their email so keep that in step
    if from_email_address and user.username == from_email_address.email:
        if User.objects.filter(username=user.email).exclude(pk=user.pk).exists():
            logger.warning("username %s is taken so user %s keeps their previous username", user.email, user.pk)
        else:
            user.username = user.email
            user.save(update_fields=("username",))
