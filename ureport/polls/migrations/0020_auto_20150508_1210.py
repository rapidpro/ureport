# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import time

import requests
import six

from django.conf import settings
from django.db import migrations

logger = logging.getLogger(__name__)


def fetch_flows(org, filter=None):
    start = time.time()

    next = "%s/api/v1/flows.json" % settings.SITE_API_HOST
    if filter:
        next += "?" + filter

    flows = []
    while next:
        response = requests.get(
            next,
            headers={
                "Content-type": "application/json",
                "Accept": "application/json",
                "Authorization": "Token %s" % org.api_token,
            },
        )

        response.raise_for_status()
        result = response.json()

        # we only include flows that have one or more rules
        for flow in result["results"]:
            if len(flow["rulesets"]) > 0:
                flows.append(flow)

        if "next" in result:
            next = result["next"]
        else:
            next = None

    if flows:
        logger.info("- got flows in %f" % (time.time() - start))

    return flows


def populate_uuid_fields(apps, schema_editor):
    Poll = apps.get_model("polls", "Poll")
    PollQuestion = apps.get_model("polls", "PollQuestion")
    Org = apps.get_model("orgs", "Org")

    for org in Org.objects.all():
        flow_ids = org.polls.values_list("flow_id", flat=True)
        flows = fetch_flows(org, "flows=%s" % ",".join([six.text_type(elt) for elt in flow_ids]))
        for flow in flows:
            for ruleset in flow["rulesets"]:
                PollQuestion.objects.filter(ruleset_id=ruleset["id"]).update(ruleset_uuid=ruleset["node"])

            Poll.objects.filter(flow_id=int(flow["flow"])).update(flow_uuid=flow["uuid"])


class Migration(migrations.Migration):
    dependencies = [("polls", "0019_auto_20150508_1209")]

    operations = [migrations.RunPython(populate_uuid_fields)]
