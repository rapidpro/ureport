# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import time
from collections import defaultdict

import requests
from django_valkey import get_valkey_connection
from temba_client.v2 import TembaClient

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from dash.utils.sync import BaseSyncer, SyncOutcome, sync_local_to_changes
from ureport.contacts.models import Contact
from ureport.locations.models import Boundary
from ureport.polls.models import Poll, PollQuestion, PollResponseCategory, PollResult
from ureport.utils import datetime_to_json_date, json_date_to_datetime

from . import BaseBackend

logger = logging.getLogger(__name__)


class ContactSyncer(BaseSyncer):
    model = Contact
    prefetch_related = ("backend",)

    def get_boundaries_data(self, org):
        cache_attr = "__boundaries__%d:%s" % (org.pk, self.backend.slug)
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)

        org_state_boundaries_data = dict()
        org_district_boundaries_data = dict()
        org_ward_boundaries_data = dict()
        state_boundaries = Boundary.objects.filter(org=org, level=Boundary.STATE_LEVEL)
        for state in state_boundaries:
            org_state_boundaries_data[state.name.lower()] = state.osm_id
            state_district_data = dict()
            district_boundaries = Boundary.objects.filter(org=org, level=Boundary.DISTRICT_LEVEL, parent=state)
            for district in district_boundaries:
                state_district_data[district.name.lower()] = district.osm_id
                district_ward_data = dict()
                ward_boundaries = Boundary.objects.filter(org=org, level=Boundary.WARD_LEVEL, parent=district)
                for ward in ward_boundaries:
                    district_ward_data[ward.name.lower()] = ward.osm_id
                org_ward_boundaries_data[district.osm_id] = district_ward_data

            org_district_boundaries_data[state.osm_id] = state_district_data

        setattr(self, cache_attr, (org_state_boundaries_data, org_district_boundaries_data, org_ward_boundaries_data))
        return org_state_boundaries_data, org_district_boundaries_data, org_ward_boundaries_data

    def local_kwargs(self, org, remote):
        from ureport.utils import json_date_to_datetime

        org_state_boundaries_data, org_district_boundaries_data, org_ward_boundaries_data = self.get_boundaries_data(
            org
        )

        state = ""
        district = ""
        ward = ""

        state_field = org.get_config("%s.state_label" % self.backend.slug, default="")
        if state_field:
            state_field = state_field.lower()
            if org.get_config("common.is_global"):
                state_name = remote.fields.get(state_field, None)
                if state_name:
                    state = state_name

            else:
                state_path = remote.fields.get(state_field, None)
                if state_path:
                    state_name = state_path.split(" > ")[-1]
                    state_name = state_name.lower()
                    state = org_state_boundaries_data.get(state_name, "")

                district_field = org.get_config("%s.district_label" % self.backend.slug, default="")
                if district_field:
                    district_field = district_field.lower()
                    district_path = remote.fields.get(district_field, None)
                    if district_path:
                        district_name = district_path.split(" > ")[-1]
                        district_name = district_name.lower()
                        district = org_district_boundaries_data.get(state, dict()).get(district_name, "")

                ward_field = org.get_config("%s.ward_label" % self.backend.slug, default="")
                if ward_field:
                    ward_field = ward_field.lower()
                    ward_path = remote.fields.get(ward_field, None)
                    if ward_path:
                        ward_name = ward_path.split(" > ")[-1]
                        ward_name = ward_name.lower()
                        ward = org_ward_boundaries_data.get(district, dict()).get(ward_name, "")

        registered_on = None
        registration_field = org.get_config("%s.registration_label" % self.backend.slug, default="")
        if registration_field:
            registration_field = registration_field.lower()
            registered_on = remote.fields.get(registration_field, None)
            if registered_on:
                registered_on = json_date_to_datetime(registered_on)

        occupation = ""
        occupation_field = org.get_config("%s.occupation_label" % self.backend.slug, default="")
        if occupation_field:
            occupation_field = occupation_field.lower()
            occupation = remote.fields.get(occupation_field, "")
            if not occupation:
                occupation = ""

        born = 0
        born_field = org.get_config("%s.born_label" % self.backend.slug, default="")
        if born_field:
            born_field = born_field.lower()
            try:
                born = int(remote.fields.get(born_field, 0))

                # support only positive django integer field valid values
                if born < 0 or born > 2147483647:
                    born = 0

            except ValueError:
                pass
            except TypeError:
                pass

        gender = ""
        gender_field = org.get_config("%s.gender_label" % self.backend.slug, default="")
        female_label = org.get_config("%s.female_label" % self.backend.slug, default="")
        male_label = org.get_config("%s.male_label" % self.backend.slug, default="")

        if gender_field:
            gender_field = gender_field.lower()
            gender = remote.fields.get(gender_field, "")

            if gender and gender.lower() == female_label.lower():
                gender = self.model.FEMALE
            elif gender and gender.lower() == male_label.lower():
                gender = self.model.MALE
            else:
                gender = ""

        return {
            "backend": self.backend,
            "org": org,
            "uuid": remote.uuid,
            "gender": gender,
            "born": born,
            "occupation": occupation,
            "registered_on": registered_on,
            "state": state,
            "district": district,
            "ward": ward,
        }

    def update_required(self, local, remote, local_kwargs):
        if local_kwargs and local_kwargs["backend"] != local.backend:
            return False

        if not local_kwargs:
            return True

        return any(
            [
                local.gender != local_kwargs["gender"],
                local.born != local_kwargs["born"],
                local.occupation != local_kwargs["occupation"],
                local.registered_on != local_kwargs["registered_on"],
                local.state != local_kwargs["state"],
                local.district != local_kwargs["district"],
                local.ward != local_kwargs["ward"],
            ]
        )


class FLOIPBackend(BaseBackend):
    """
    FLOIP instance as a backend
    """

    def _get_client(self, org):
        agent = getattr(settings, "SITE_API_USER_AGENT", None)
        return TembaClient(self.backend.host, self.backend.api_token, user_agent=agent)

    def pull_fields(self, org):
        # Not needed
        return {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0}

    def pull_boundaries(self, org):
        # Not needed
        return {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0}

    def pull_contacts(self, org, modified_after, modified_before, progress_callback=None):
        client = self._get_client(org)

        # all contacts created or modified in the time window
        active_query = client.get_contacts(after=modified_after, before=modified_before)
        fetches = active_query.iterfetches(retry_on_rate_exceed=True)

        # all contacts deleted in the same time window
        deleted_query = client.get_contacts(deleted=True, after=modified_after, before=modified_before)
        deleted_fetches = deleted_query.iterfetches(retry_on_rate_exceed=True)

        return sync_local_to_changes(
            org, ContactSyncer(backend=self.backend), fetches, deleted_fetches, progress_callback
        )

    def fetch_flows(self, org):
        flow_url = "https://go.votomobile.org/flow-results/packages/"

        headers = {
            "Content-type": "application/json",
            "Accept": "application/json",
            "Authorization": "Token %s" % self.backend.api_token,
        }

        flows = []

        while flow_url:
            response = requests.request("GET", flow_url, headers=headers)
            response_json = response.json()

            flows += response_json["data"]
            flow_url = response_json["links"]["next"]

        all_flows = dict()
        for flow in flows:
            flow_attributes = flow["attributes"]

            flow_json = dict()
            flow_json["uuid"] = flow["id"]
            flow_json["date_hint"] = flow_attributes["created"]
            flow_json["created_on"] = flow_attributes["created"]
            flow_json["name"] = flow_attributes["title"]
            flow_json["archived"] = False
            flow_json["runs"] = 0
            flow_json["completed_runs"] = 0

            all_flows[flow["id"]] = flow_json
        return all_flows

    def get_definition(self, org, flow_uuid):
        flow_url = "https://go.votomobile.org/flow-results/packages/" + flow_uuid

        headers = {
            "Content-type": "application/json",
            "Accept": "application/json",
            "Authorization": "Token %s" % self.backend.api_token,
        }

        response = requests.request("GET", flow_url, headers=headers)
        response_json = response.json()

        flow_definition = None
        try:
            flow_definition = response_json["data"]["attributes"]
        except KeyError:
            pass
        return flow_definition

    def update_poll_questions(self, org, poll, user):
        flow_definition = self.get_definition(org, poll.flow_uuid)

        if flow_definition is None:
            return

        package_schema = flow_definition["resources"][0]["schema"]

        base_language = package_schema["language"]

        poll.base_language = base_language
        poll.save()

        package_questions = package_schema["questions"]

        for key, val in package_questions.items():
            label = val["label"]
            ruleset_uuid = key
            ruleset_type = val["type"]

            question = PollQuestion.update_or_create(user, poll, label, ruleset_uuid, ruleset_type)

            choices = val.get("type_options", dict()).get("choices", [])
            if choices == []:
                # create an ignored category for open ended questions
                PollResponseCategory.update_or_create(question, None, "other")

            for category in choices:
                PollResponseCategory.update_or_create(question, None, category)

    def pull_results(self, poll, modified_after, modified_before, progress_callback=None):
        org = poll.org
        r = get_valkey_connection()
        key = Poll.POLL_PULL_RESULTS_TASK_LOCK % (org.pk, poll.flow_uuid)

        stats_dict = dict(
            num_val_created=0,
            num_val_updated=0,
            num_val_ignored=0,
            num_path_created=0,
            num_path_updated=0,
            num_path_ignored=0,
            num_synced=0,
        )

        if r.get(key):
            logger.info("Skipping pulling results for poll #%d on org #%d as it is still running" % (poll.pk, org.pk))
        else:
            with r.lock(key, timeout=Poll.POLL_SYNC_LOCK_TIMEOUT):
                lock_expiration = time.time() + 0.8 * Poll.POLL_SYNC_LOCK_TIMEOUT

                poll_results_url = "https://go.votomobile.org/flow-results/packages/%s/responses" % poll.flow_uuid

                headers = {
                    "Content-type": "application/json",
                    "Accept": "application/json",
                    "Authorization": "Token %s" % self.backend.api_token,
                }

                results = []

                questions_uuids = poll.get_question_uuids()

                # ignore the TaskState time and use the time we stored in valkey
                (
                    latest_synced_obj_time,
                    pull_after_delete,
                ) = poll.get_pull_cached_params()

                if pull_after_delete is not None:
                    latest_synced_obj_time = None
                    poll.delete_poll_results()

                start = time.time()
                logger.info("Start fetching runs for poll #%d on org #%d" % (poll.pk, org.pk))

                params = dict(
                    filter={"start-timestamp": latest_synced_obj_time},
                )

                while poll_results_url:
                    response = requests.request("GET", poll_results_url, headers=headers, params=params)
                    response_json = response.json()

                    results = response_json["data"]["attributes"]["responses"]
                    poll_results_url = response_json["data"]["relationships"]["links"]["next"]

                    (contacts_map, poll_results_map, poll_results_to_save_map) = self._initiate_lookup_maps(
                        results, org, poll
                    )

                    for result in results:
                        if latest_synced_obj_time is None or json_date_to_datetime(result[0]) > json_date_to_datetime(
                            latest_synced_obj_time
                        ):
                            latest_synced_obj_time = result[0]

                        contact_obj = contacts_map.get(result[2], None)
                        self._process_run_poll_results(
                            org,
                            poll.flow_uuid,
                            questions_uuids,
                            result,
                            contact_obj,
                            poll_results_map,
                            poll_results_to_save_map,
                            stats_dict,
                        )

                        stats_dict["num_synced"] += len(results)
                        if progress_callback:
                            progress_callback(stats_dict["num_synced"])

                    self._save_new_poll_results_to_database(poll_results_to_save_map)

                    logger.info(
                        "Processed fetch of %d - %d "
                        "runs for poll #%d on org #%d"
                        % (stats_dict["num_synced"] - len(results), stats_dict["num_synced"], poll.pk, org.pk)
                    )
                    # fetch_start = time.time()
                    logger.info("=" * 40)

                    if stats_dict["num_synced"] >= Poll.POLL_RESULTS_MAX_SYNC_RUNS or time.time() > lock_expiration:
                        poll.rebuild_poll_results_counts()

                        self._mark_poll_results_sync_paused(org, poll, latest_synced_obj_time)

                        logger.info(
                            "Break pull results for poll #%d on org #%d in %ds, "
                            "Times: sync_latest= %s, "
                            "Objects: created %d, updated %d, ignored %d. "
                            % (
                                poll.pk,
                                org.pk,
                                time.time() - start,
                                latest_synced_obj_time,
                                stats_dict["num_val_created"],
                                stats_dict["num_val_updated"],
                                stats_dict["num_val_ignored"],
                            )
                        )

                        return (
                            stats_dict["num_val_created"],
                            stats_dict["num_val_updated"],
                            stats_dict["num_val_ignored"],
                            stats_dict["num_path_created"],
                            stats_dict["num_path_updated"],
                            stats_dict["num_path_ignored"],
                        )

                self._mark_poll_results_sync_completed(poll, org, latest_synced_obj_time)

                # from django.db import connection as db_connection, reset_queries
                # slowest_queries = sorted(db_connection.queries, key=lambda q: q['time'], reverse=True)[:10]
                # for q in slowest_queries:
                #     print "=" * 60
                #     print "\n\n\n"
                #     print "%s -- %s" % (q['time'], q['sql'])
                # reset_queries()

                logger.info(
                    "Finished pulling results for poll #%d on org #%d runs in %ds, "
                    "Times: sync_latest= %s,"
                    "Objects: created %d, updated %d, ignored %d"
                    % (
                        poll.pk,
                        org.pk,
                        time.time() - start,
                        latest_synced_obj_time,
                        stats_dict["num_val_created"],
                        stats_dict["num_val_updated"],
                        stats_dict["num_val_ignored"],
                    )
                )
        return (
            stats_dict["num_val_created"],
            stats_dict["num_val_updated"],
            stats_dict["num_val_ignored"],
            stats_dict["num_path_created"],
            stats_dict["num_path_updated"],
            stats_dict["num_path_ignored"],
        )

    def _initiate_lookup_maps(self, fetch, org, poll):
        contact_uuids = [run[2] for run in fetch]
        contacts = Contact.objects.filter(org=org, uuid__in=contact_uuids)
        contacts_map = {c.uuid: c for c in contacts}
        existing_poll_results = PollResult.objects.filter(
            flow=poll.flow_uuid, org=poll.org_id, contact__in=contact_uuids
        )
        poll_results_map = defaultdict(dict)
        for res in existing_poll_results:
            poll_results_map[res.contact][res.ruleset] = res

        poll_results_to_save_map = defaultdict(dict)
        return contacts_map, poll_results_map, poll_results_to_save_map

    def _process_run_poll_results(
        self,
        org,
        flow_uuid,
        questions_uuids,
        result,
        contact_obj,
        existing_db_poll_results_map,
        poll_results_to_save_map,
        stats_dict,
    ):
        contact_uuid = result[2]
        completed = True

        state = ""
        district = ""
        ward = ""
        born = None
        gender = None
        if contact_obj is not None:
            state = contact_obj.state
            district = contact_obj.district
            ward = contact_obj.ward
            born = contact_obj.born
            gender = contact_obj.gender

        value_date = json_date_to_datetime(result[0])
        ruleset_uuid = result[4]
        category = result[5]
        text = result[5]

        existing_poll_result = existing_db_poll_results_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

        poll_result_to_save = poll_results_to_save_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

        if existing_poll_result is not None:
            update_required = self._check_update_required(
                existing_poll_result, category, text, state, district, ward, born, gender, completed, value_date
            )

            if update_required:
                # update the db object
                PollResult.objects.filter(pk=existing_poll_result.pk).update(
                    category=category,
                    text=text,
                    state=state,
                    district=district,
                    ward=ward,
                    date=value_date,
                    born=born,
                    gender=gender,
                    completed=completed,
                )

                # update the map object as well
                existing_poll_result.category = category
                existing_poll_result.text = text
                existing_poll_result.state = state
                existing_poll_result.district = district
                existing_poll_result.ward = ward
                existing_poll_result.date = value_date
                existing_poll_result.born = born
                existing_poll_result.gender = gender
                existing_poll_result.completed = completed

                existing_db_poll_results_map[contact_uuid][ruleset_uuid] = existing_poll_result

                stats_dict["num_val_updated"] += 1
            else:
                stats_dict["num_val_ignored"] += 1

        elif poll_result_to_save is not None:
            replace_save_map = self._check_update_required(
                poll_result_to_save, category, text, state, district, ward, born, gender, completed, value_date
            )

            if replace_save_map:
                result_obj = PollResult(
                    org=org,
                    flow=flow_uuid,
                    ruleset=ruleset_uuid,
                    contact=contact_uuid,
                    category=category,
                    text=text,
                    state=state,
                    district=district,
                    ward=ward,
                    born=born,
                    gender=gender,
                    date=value_date,
                    completed=completed,
                )

                poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

            stats_dict["num_val_ignored"] += 1
        else:
            result_obj = PollResult(
                org=org,
                flow=flow_uuid,
                ruleset=ruleset_uuid,
                contact=contact_uuid,
                category=category,
                text=text,
                state=state,
                district=district,
                ward=ward,
                born=born,
                gender=gender,
                date=value_date,
                completed=completed,
            )

            poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

            stats_dict["num_val_created"] += 1

    @staticmethod
    def _check_update_required(poll_obj, category, text, state, district, ward, born, gender, completed, value_date):
        update_required = any(
            [
                poll_obj.category != category,
                poll_obj.text != text,
                poll_obj.state != state,
                poll_obj.district != district,
                poll_obj.ward != ward,
                poll_obj.born != born,
                poll_obj.gender != gender,
                poll_obj.completed != completed,
            ]
        )

        # if the reporter answered the step, check if this is a newer run
        if poll_obj.date is not None:
            update_required = update_required and (value_date > poll_obj.date)
        else:
            update_required = True
        return update_required

    @staticmethod
    def _save_new_poll_results_to_database(poll_results_to_save_map):
        new_poll_results = []
        for c_key in poll_results_to_save_map.keys():
            for r_key in poll_results_to_save_map.get(c_key, dict()):
                obj_to_create = poll_results_to_save_map.get(c_key, dict()).get(r_key, None)
                if obj_to_create is not None:
                    new_poll_results.append(obj_to_create)
        PollResult.objects.bulk_create(new_poll_results)

    @staticmethod
    def _mark_poll_results_sync_paused(org, poll, latest_synced_obj_time):
        # update the time for this poll from which we fetch next time
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (org.pk, poll.flow_uuid), latest_synced_obj_time, None)

        from ureport.polls.tasks import pull_refresh

        pull_refresh.apply_async((poll.pk,), countdown=300, queue="sync")

    @staticmethod
    def _mark_poll_results_sync_completed(poll, org, latest_synced_obj_time):
        # update the time for this poll from which we fetch next time
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (org.pk, poll.flow_uuid), latest_synced_obj_time, None)

        # update the last time the sync happened, for displaying in polls list on admin page
        now = timezone.now()
        cache.set(
            Poll.POLL_RESULTS_LAST_SYNC_TIME_CACHE_KEY % (org.pk, poll.flow_uuid),
            datetime_to_json_date(now),
            None,
        )

        # Use Valkey cache with expiring(in 48 hrs) key to allow other polls task
        # to sync all polls without hitting the API rate limit
        cache.set(
            Poll.POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_KEY % (org.id, poll.flow_uuid),
            datetime_to_json_date(now),
            Poll.POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_TIMEOUT,
        )

        Poll.objects.filter(id=poll.pk).update(modified_on=now)
