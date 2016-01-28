# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import models, migrations
from temba_client.v1 import TembaClient

from ureport.utils import datetime_to_json_date, json_date_to_datetime


class Migration(migrations.Migration):

    def populate_poll_poll_date(apps, schema_editor):
        Poll = apps.get_model('polls', "Poll")
        Org = apps.get_model('orgs', "Org")

        agent = getattr(settings, 'SITE_API_USER_AGENT', None)
        host = settings.SITE_API_HOST

        for org in Org.objects.all():
            temba_client = TembaClient(host, org.api_token, user_agent=agent)
            api_flows = temba_client.get_flows()
            flows_date = dict()
            for flow in api_flows:
                flows_date[flow.uuid] = datetime_to_json_date(flow.created_on)

            for poll in Poll.objects.filter(org=org):
                json_date = flows_date.get(poll.flow_uuid, None)
                if json_date:
                    date = json_date_to_datetime(json_date)
                else:
                    print "using created_on for flow_date on poll with id %s" % poll.pk
                    date = poll.created_on

                poll.poll_date = date
                poll.save()

    dependencies = [
        ('polls', '0022_poll_flow_date'),
    ]

    operations = [
        migrations.RunPython(populate_poll_poll_date),
    ]
