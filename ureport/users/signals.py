import logging

from allauth.account.signals import email_changed

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(pre_save, sender=User)
def on_user_pre_save(sender, instance, raw, **kwargs):
    # allauth stores and looks up emails in lowercase, so keep the user's email that way too
    if not raw and instance.email:
        instance.email = instance.email.strip().lower()


@receiver(post_save, sender=User)
def on_user_saved(sender, instance, raw, **kwargs):
    # an address the user no longer has must stop working as a login. Their current address is verified by allauth
    # the next time they log in.
    if not raw:
        instance.emailaddress_set.exclude(email=instance.email).delete()


@receiver(email_changed)
def on_email_changed(sender, request, user, from_email_address, to_email_address, **kwargs):
    # users created through the org invitation flow have their username set to their email so keep that in step
    if from_email_address and user.username == from_email_address.email:
        if User.objects.filter(username=user.email).exclude(pk=user.pk).exists():
            logger.warning("username %s is taken so user %s keeps their previous username", user.email, user.pk)
        else:
            user.username = user.email
            user.save(update_fields=("username",))
