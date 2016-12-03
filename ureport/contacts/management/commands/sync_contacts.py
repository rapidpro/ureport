from django.core.management.base import BaseCommand
from django.db.transaction import non_atomic_requests

from django.conf import settings
from temba_client.v2 import TembaClient
from dash.orgs.models import Org

from ureport.contacts.models import Contact


class Command(BaseCommand):
    help = 'Sync contact with RapidPRO for each active organization'

    @non_atomic_requests
    def handle(self, *args, **options):

        orgs = Org.objects.filter(is_active=True).order_by('name')

        for org in orgs:

            contacts_report = org.contacts.filter(is_active=True)
            contacts_ureport_uuid = [contact.uuid for contact in contacts_report]

            api = TembaClient(host=settings.SITE_API_HOST, token='%s' % org.api_token, user_agent=None)
            group = org.get_config(name='reporter_group')
            contacts_rapidpro = api.get_contacts(group=group, deleted=False).all()
            contacts_rapidpro_uuid = [item.uuid for item in contacts_rapidpro]

            deleted = [contact for contact in contacts_ureport_uuid if contact not in contacts_rapidpro_uuid]

            count_deleted = 0
            if deleted:
                for item_deleted in deleted:
                    try:
                        c = Contact.objects.get(uuid=item_deleted)
                        c.is_active = False
                        c.save()
                        count_deleted += 1
                    except Exception as e:
                        print(e.args)

            added = [result for result in contacts_rapidpro_uuid if result not in contacts_ureport_uuid]

            count_added = 0
            if added:
                for item_add in added:
                    try:
                        exists = Contact.objects.filter(uuid=item_add).first()
                        if exists:
                            exists.is_active = True
                            exists.save()
                        else:
                            new_contact = Contact(uuid=item_add, org_id=org.pk, is_active=True)
                            new_contact.save()
                        count_added += 1
                    except Exception as e:
                        print(e.args)

            print('Org: %s (Added: %s | Inactivated: %s)' % (org.subdomain, count_added, count_deleted))
