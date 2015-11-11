# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import time
from django.conf import settings

from django.db import models, migrations
from temba_client.base import TembaAPIError
from temba_client.client import TembaClient


class Migration(migrations.Migration):

    def populate_response_categories(apps, schema_editor):
        Poll = apps.get_model("polls", "Poll")
        PollQuestion = apps.get_model("polls", "PollQuestion")
        PollResponseCategory = apps.get_model("polls", "PollResponseCategory")

        deactivated = 0
        successes = 0
        deactivated_ids = []

        start = time.time()

        for poll in Poll.objects.filter(is_active=True):
            org = poll.org
            user = poll.created_by
            host = getattr(settings, 'SITE_API_HOST', None)
            agent = getattr(settings, 'SITE_API_USER_AGENT', None)

            if not host:
                host = '%s/api/v1' % settings.API_ENDPOINT  # UReport sites use this

            temba_client = TembaClient(host, org.api_token, user_agent=agent)

            try:
                flow_definition = temba_client.get_flow_definition(poll.flow_uuid)

                for ruleset in flow_definition.rule_sets:
                    label = ruleset['label']
                    ruleset_uuid = ruleset['uuid']
                    ruleset_type = ruleset['ruleset_type']

                    existing_questions = PollQuestion.objects.filter(ruleset_uuid=ruleset_uuid, poll=poll)
                    if existing_questions:
                        existing_questions.update(ruleset_type=ruleset_type)
                        poll_question = existing_questions.first()
                        print "Updated ruleset - %s" % ruleset_uuid
                    else:
                        poll_question = PollQuestion.objects.create(poll=poll, ruleset_uuid=ruleset_uuid, title=label,
                                                                    ruleset_type=ruleset_type, is_active=False,
                                                                    created_by=user, modified_by=user)
                        print "Created ruleset - %s" % ruleset_uuid

                    for rule in ruleset['rules']:
                        category = json.dumps(rule['category'])
                        existing_response_category = PollResponseCategory.objects.filter(question=poll_question,
                                                                                         rule_uuid=rule['uuid'])
                        if existing_response_category:
                            existing_response_category.update(category=category)
                            print "Updated rule - %s" % rule['uuid']
                        else:
                            PollResponseCategory.objects.create(question=poll_question, rule_uuid=rule['uuid'],
                                                                category=category)

                            print "Created rule - %s" % rule['uuid']

                    print "Done ruleset - %s" % ruleset_uuid

                print "Done poll - %s - %d - %s" % (org.name, poll.pk, poll.title)
                successes += 1

            except TembaAPIError:
                poll.is_active = False
                poll.save()

                deactivated_ids.append(poll.pk)
                deactivated += 1
                print "Hidden poll - %s - %d - %s" % (org.name, poll.pk, poll.title)

            except Exception as e:
                raise e

        print "Finished populating %d polls in %ss" % (successes, time.time() - start)
        print "Deactivated %d polls" % deactivated
        print "Deactivated ids are %s" % ",".join([str(elt) for elt in deactivated_ids])


    dependencies = [
        ('polls', '0023_auto_20151110_1333'),
    ]

    operations = [
        migrations.RunPython(populate_response_categories),
    ]
