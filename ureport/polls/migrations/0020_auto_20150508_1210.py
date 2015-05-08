# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from dash.api import API

def populate_uuid_fields(apps, schema_editor):
    Poll = apps.get_model('polls', "Poll")
    PollQuestion = apps.get_model('polls', "PollQuestion")
    Org = apps.get_model('orgs', "Org")

    for org in Org.objects.all():
        flow_ids = org.polls.values_list('flow_id', flat=True)
        flows = API(org).get_flows("flows=%s" % ",".join([str(elt) for elt in flow_ids]))
        for flow in flows:
            for ruleset in flow['rulesets']:
                PollQuestion.objects.filter(ruleset_id=ruleset['id']).update(ruleset_uuid=ruleset['node'])

            Poll.objects.filter(flow_id=int(flow['flow'])).update(flow_uuid=flow['uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('polls', '0019_auto_20150508_1209'),
    ]

    operations = [
        migrations.RunPython(populate_uuid_fields)
    ]
