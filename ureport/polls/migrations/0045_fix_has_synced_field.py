# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    def fix_populate_poll_has_synced(apps, schema_editor):
        Poll = apps.get_model("polls", "Poll")
        PollQuestion = apps.get_model("polls", "PollQuestion")
        PollResultsCounter = apps.get_model("polls", "PollResultsCounter")

        synced_flows = []

        for question in PollQuestion.objects.all():
            if PollResultsCounter.objects.filter(org=question.poll.org, ruleset=question.ruleset_uuid).exists():
                synced_flows.append(question.poll.flow_uuid)

        Poll.objects.filter(flow_uuid__in=synced_flows).update(has_synced=True)

    dependencies = [("polls", "0044_populate_poll_has_synced")]

    operations = [migrations.RunPython(fix_populate_poll_has_synced)]
