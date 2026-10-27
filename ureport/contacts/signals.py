from django.db.models.signals import post_save
from django.dispatch import receiver

from dash.orgs.models import Org
from ureport.contacts.sync import clear_boundaries_synced


@receiver(post_save, sender=Org)
def on_org_saved(sender, instance, raw, update_fields=None, **kwargs):
    # contact syncs only pull boundaries once a day, so saving an org's config has the next sync pull them again:
    # it picks up a change to where they come from (whether the org is global), and gives admins a way to have
    # boundaries changed on the backend reach contacts sooner
    if not raw and (update_fields is None or "config" in update_fields):
        clear_boundaries_synced(instance)
