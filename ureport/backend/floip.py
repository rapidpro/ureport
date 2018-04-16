from __future__ import unicode_literals

import requests
from uuid import uuid4
from ureport.polls.models import PollQuestion, PollResponseCategory
from . import BaseBackend


class FLOIPBackend(BaseBackend):
    """
    FLOIP instance as a backend
    """

    def pull_fields(self, org):
        # Not yet implemented
        return 0, 0, 0, 0

    def pull_boundaries(self, org):
        # Not yet implemented
        return 0, 0, 0, 0

    def pull_contacts(self, org, modified_after, modified_before, progress_callback=None):
        # Not yet implemented
        return 0, 0, 0, 0

    def fetch_flows(self, org):

        flow_url = "https://go.votomobile.org/flow-results/packages/"

        headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json',
            'Authorization': 'Token %s' % "9b3100024df07f8ed126af2d0"
        }

        flows = []

        while flow_url:
            response = requests.request('GET', flow_url, headers=headers)
            response_json = response.json()

            flows += response_json['data']
            flow_url = response_json['links']['next']

        all_flows = dict()
        for flow in flows:
            flow_attributes = flow['attributes']

            flow_json = dict()
            flow_json['uuid'] = flow['id']
            flow_json['date_hint'] = flow_attributes['created']
            flow_json['created_on'] = flow_attributes['created']
            flow_json['name'] = flow_attributes['name']
            flow_json['archived'] = False
            flow_json['runs'] = 0
            flow_json['completed_runs'] = 0

            all_flows[flow['id']] = flow_json
        return all_flows

    def get_definition(self, org, flow_uuid):

        flow_url = "https://go.votomobile.org/flow-results/packages/" + flow_uuid

        headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json',
            'Authorization': 'Token %s' % "9b3100024df07f8ed126af2d0"
        }

        response = requests.request('GET', flow_url, headers=headers)
        response_json = response.json()

        flow_definition = None
        try:
            flow_definition = response_json['data']['attributes']
        except KeyError:
            pass
        return flow_definition

    def update_poll_questions(self, org, poll, user):
        flow_definition = self.get_definition(org, poll.flow_uuid)

        if flow_definition is None:
            return

        package_schema = flow_definition['resources'][0]['schema']

        base_language = package_schema['language']

        poll.base_language = base_language
        poll.save()

        package_questions = package_schema['questions']

        for key, val in package_questions.items():
            label = val['label']
            ruleset_uuid = key
            ruleset_type = val['type']

            question = PollQuestion.update_or_create(user, poll, label, ruleset_uuid, ruleset_type)

            for category in val.get('type_options', dict()).get('choices', []):
                PollResponseCategory.update_or_create(question, uuid4(), category)

    def pull_results(self, poll, modified_after, modified_before, progress_callback=None):
        # Not yet implemented
        return 0, 0, 0, 0, 0, 0
