# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import time
from ureport.utils import chunk_list


class Migration(migrations.Migration):

    def populate_age_and_gender_on_poll_results(apps, schema_editor):
        Contact = apps.get_model("contacts", "Contact")
        PollResult = apps.get_model("polls", "PollResult")

        all_contacts = Contact.objects.all().values_list('id', flat=True)
        start = time.time()
        i = 0

        for contact_id_batch in chunk_list(all_contacts, 1000):
            contacts = Contact.objects.filter(id__in=contact_id_batch)
            for contact in contacts:
                i += 1
                results_ids = PollResult.objects.filter(contact=contact.uuid).values_list('id', flat=True)
                PollResult.objects.filter(id__in=results_ids).update(born=contact.born, gender=contact.gender)

            print "Processed poll results update %d / %d contacts in %ds" % (i, len(all_contacts), time.time() - start)

    def noop(apps, schema_editor):
        pass

    dependencies = [
        ('polls', '0047_auto_20160531_0753'),
    ]

    operations = [
        migrations.RunPython(populate_age_and_gender_on_poll_results, noop)
    ]
