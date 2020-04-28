# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import time

import six
from temba_client.exceptions import TembaBadRequestError
from temba_client.v1 import TembaClient

from django.conf import settings
from django.db import migrations

logger = logging.getLogger(__name__)


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
            host = getattr(settings, "SITE_API_HOST", None)
            agent = getattr(settings, "SITE_API_USER_AGENT", None)

            if not host:
                host = settings.API_ENDPOINT

            temba_client = TembaClient(host, org.api_token, user_agent=agent)

            try:
                flow_definition = temba_client.get_flow_definition(poll.flow_uuid)
                base_language = flow_definition.base_language

                poll.base_language = base_language
                poll.save()

                for ruleset in flow_definition.rule_sets:
                    label = ruleset["label"]
                    ruleset_uuid = ruleset["uuid"]
                    ruleset_type = ruleset["ruleset_type"]

                    existing_questions = PollQuestion.objects.filter(ruleset_uuid=ruleset_uuid, poll=poll)
                    if existing_questions:
                        existing_questions.update(ruleset_type=ruleset_type)
                        poll_question = existing_questions.first()
                        logger.info("Updated ruleset - %s" % ruleset_uuid)
                    else:
                        poll_question = PollQuestion.objects.create(
                            poll=poll,
                            ruleset_uuid=ruleset_uuid,
                            title=label,
                            ruleset_type=ruleset_type,
                            is_active=False,
                            created_by=user,
                            modified_by=user,
                        )
                        logger.info("Created ruleset - %s" % ruleset_uuid)

                    for rule in ruleset["rules"]:
                        category = rule["category"][base_language]
                        existing_response_category = PollResponseCategory.objects.filter(
                            question=poll_question, rule_uuid=rule["uuid"]
                        )
                        if existing_response_category:
                            existing_response_category.update(category=category)
                            logger.info("Updated rule - %s" % rule["uuid"])
                        else:
                            PollResponseCategory.objects.create(
                                question=poll_question, rule_uuid=rule["uuid"], category=category
                            )

                            logger.info("Created rule - %s" % rule["uuid"])

                    logger.info("Done ruleset - %s" % ruleset_uuid)

                logger.info("Done poll - %d on org %d" % (poll.pk, org.pk))
                successes += 1

            except TembaBadRequestError:
                poll.is_active = False
                poll.save()

                deactivated_ids.append(poll.pk)
                deactivated += 1
                logger.info("Hidden poll - %d on org %d" % (poll.pk, org.pk))

            except Exception as e:
                raise e

        logger.info("Finished populating %d polls in %ss" % (successes, time.time() - start))
        logger.info("Deactivated %d polls" % deactivated)
        logger.info("Deactivated ids are %s" % ",".join([six.text_type(elt) for elt in deactivated_ids]))

    dependencies = [("polls", "0028_auto_20160202_1026")]

    operations = [migrations.RunPython(populate_response_categories)]
