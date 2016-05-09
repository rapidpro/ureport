# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations

from ureport.utils import chunk_list


class Migration(migrations.Migration):

    def remove_poll_results_without_poll_question(apps, schema_editor):
        PollQuestion = apps.get_model('polls', "PollQuestion")
        PollResult = apps.get_model('polls', "PollResult")

        valid_rulesets = PollQuestion.objects.all().values_list('ruleset_uuid', flat=True)

        invalid_results_ids = PollResult.objects.exclude(ruleset__in=valid_rulesets).values_list('pk', flat=True)

        invalid_results_count = len(invalid_results_ids)

        deleted_count = 0
        for batch in chunk_list(invalid_results_ids, 1000):
            ids = list(batch)
            PollResult.objects.filter(pk__in=ids).delete()
            deleted_count += len(ids)
            print "Removed %d of %d invalid results objects" % (deleted_count, invalid_results_count)

    dependencies = [
        ('polls', '0039_pollresult_ward'),
    ]

    operations = [
        migrations.RunPython(remove_poll_results_without_poll_question)
    ]
