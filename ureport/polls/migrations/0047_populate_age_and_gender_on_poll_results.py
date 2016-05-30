# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import time


class Migration(migrations.Migration):

    def populate_age_and_gender_on_poll_results(apps, schema_editor):
        Org = apps.get_model("orgs", "Org")
        Contact = apps.get_model("contacts", "Contact")
        Poll = apps.get_model("polls", "Poll")
        PollResult = apps.get_model("polls", "PollResult")

        orgs = Org.objects.all()

        for org in orgs:
            start = time.time()
            polls_uuid = Poll.objects.all().distinct('flow_uuid').values_list('flow_uuid', flat=True)
            org_contacts = Contact.objects.filter(org_id=org.id)

            for contact in org_contacts:
                PollResult.objects.filter(org_id=org.id, flow__in=polls_uuid, contact=contact.uuid).update(born=contact.born, gender=contact.gender)

            print "Finished populating born and gender on poll results for org #d in %ss" % (org.id, time.time() - start)

    def noop(apps, schema_editor):
        pass

    dependencies = [
        ('polls', '0046_auto_20160530_0912'),
    ]

    operations = [
        migrations.RunPython(populate_age_and_gender_on_poll_results, noop)
    ]
