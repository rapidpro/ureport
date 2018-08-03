# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    def populate_poll_has_synced(apps, schema_editor):
        Poll = apps.get_model("polls", "Poll")
        PollQuestion = apps.get_model("polls", "PollQuestion")
        PollResultsCounter = apps.get_model("polls", "PollResultsCounter")

        synced_polls = []

        for question in PollQuestion.objects.all():
            if PollResultsCounter.objects.filter(org=question.poll.org, ruleset=question.ruleset_uuid).exists():
                synced_polls.append(question.poll_id)

        Poll.objects.filter(pk__in=synced_polls).update(has_synced=True)

    dependencies = [("polls", "0043_poll_has_synced")]

    operations = [migrations.RunPython(populate_poll_has_synced)]
