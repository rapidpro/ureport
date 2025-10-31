# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import gzip
import io
import json
import logging
import time
from collections import defaultdict
from datetime import timedelta, timezone as tzone

import requests
from django_valkey import get_valkey_connection
from temba_client.exceptions import TembaRateExceededError
from temba_client.v2.types import Run

from django.core.cache import cache
from django.utils import timezone

from dash.utils import is_dict_equal
from dash.utils.sync import BaseSyncer, sync_local_to_changes, sync_local_to_set
from ureport.contacts.models import Contact, ContactField
from ureport.flows.models import FlowResultCategory
from ureport.locations.models import Boundary
from ureport.polls.models import Poll, PollQuestion, PollResponseCategory, PollResult
from ureport.polls.tasks import pull_refresh_from_archives
from ureport.stats.models import ContactActivity
from ureport.utils import chunk_list, datetime_to_json_date, json_date_to_datetime

from . import BaseBackend

logger = logging.getLogger(__name__)


class FieldSyncer(BaseSyncer):
    """
    Syncer for contact fields
    """

    model = ContactField
    local_id_attr = "key"
    remote_id_attr = "key"
    prefetch_related = ("backend",)
    local_backend_attr = "backend"

    def local_kwargs(self, org, remote):
        return {
            "backend": self.backend,
            "org": org,
            "key": remote.key,
            "label": remote.name,
            "value_type": self.model.TEMBA_TYPES.get(remote.type, self.model.TYPE_TEXT),
        }

    def update_required(self, local, remote, local_kwargs):
        if local_kwargs and local_kwargs["backend"] != local.backend:
            return False
        return any([local.label != remote.name, local.value_type != self.model.TEMBA_TYPES.get(remote.type)])

    def delete_local(self, local):
        local.release()


class BoundarySyncer(BaseSyncer):
    """
    syncer for location boundaries
    """

    model = Boundary
    local_id_attr = "osm_id"
    remote_id_attr = "osm_id"
    prefetch_related = ("backend",)
    local_backend_attr = "backend"

    def fetch_all(self, org):
        qs = self.model.objects.filter(org=org, backend=self.backend).order_by("-level")
        return qs

    def local_kwargs(self, org, remote):
        geometry = json.dumps(dict())
        if remote.geometry:
            geometry = json.dumps(dict(type=remote.geometry.type, coordinates=remote.geometry.coordinates))

        parent = None
        if remote.parent:
            parent = Boundary.objects.filter(osm_id__iexact=remote.parent.osm_id, org=org).first()

        return {
            "backend": self.backend,
            "org": org,
            "geometry": geometry,
            "parent": parent,
            "level": remote.level,
            "name": remote.name,
            "osm_id": remote.osm_id,
        }

    def update_required(self, local, remote, local_kwargs):
        if local_kwargs and local_kwargs["backend"] != local.backend:
            return False

        if local.name != remote.name:
            return True

        if local.level != remote.level:
            return True

        if remote.parent:
            if not local.parent:
                return True
            elif local.parent.osm_id != remote.parent.osm_id:
                return True

        geometry_dict = dict()
        if remote.geometry:
            geometry_dict = dict(type=remote.geometry.type, coordinates=remote.geometry.coordinates)

        return not is_dict_equal(json.loads(local.geometry), geometry_dict)

    def delete_local(self, local):
        local.release()


class ContactSyncer(BaseSyncer):
    model = Contact
    prefetch_related = ("backend",)
    local_backend_attr = "backend"

    def get_boundaries_data(self, org):
        cache_attr = "__boundaries__%d:%s" % (org.pk, self.backend.slug)
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)

        org_state_boundaries_data = dict()
        org_district_boundaries_data = dict()
        org_ward_boundaries_data = dict()
        state_boundaries = Boundary.objects.filter(org=org, level=Boundary.STATE_LEVEL, backend=self.backend)
        for state in state_boundaries:
            org_state_boundaries_data[state.name.lower()] = state.osm_id
            state_district_data = dict()
            district_boundaries = Boundary.objects.filter(
                org=org, level=Boundary.DISTRICT_LEVEL, parent=state, backend=self.backend
            )
            for district in district_boundaries:
                state_district_data[district.name.lower()] = district.osm_id
                district_ward_data = dict()
                ward_boundaries = Boundary.objects.filter(
                    org=org, level=Boundary.WARD_LEVEL, parent=district, backend=self.backend
                )
                for ward in ward_boundaries:
                    district_ward_data[ward.name.lower()] = ward.osm_id
                org_ward_boundaries_data[district.osm_id] = district_ward_data

            org_district_boundaries_data[state.osm_id] = state_district_data

        setattr(self, cache_attr, (org_state_boundaries_data, org_district_boundaries_data, org_ward_boundaries_data))
        return org_state_boundaries_data, org_district_boundaries_data, org_ward_boundaries_data

    def get_contact_fields(self, org):
        cache_attr = "__contact_fields__%d:%s" % (org.pk, self.backend.slug)
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)
        contact_fields = ContactField.objects.filter(org=org, backend=self.backend)
        contact_fields_data = {elt.label.lower(): elt.key for elt in contact_fields}

        setattr(self, cache_attr, contact_fields_data)
        return contact_fields_data

    def local_kwargs(self, org, remote):
        from ureport.utils import json_date_to_datetime

        reporter_group = org.get_config("%s.reporter_group" % self.backend.slug, default="")
        contact_groups_names = [group.name.lower() for group in remote.groups]

        # Only sync contact in the configured reporters group, skip others
        if reporter_group.lower() not in contact_groups_names:
            return None

        # Ignore empty contacts, without URNs set
        if not remote.urns:
            return None

        org_state_boundaries_data, org_district_boundaries_data, org_ward_boundaries_data = self.get_boundaries_data(
            org
        )
        contact_fields = self.get_contact_fields(org)

        state = ""
        district = ""
        ward = ""

        state_field = org.get_config("%s.state_label" % self.backend.slug, default="")
        if state_field:
            state_field = state_field.lower()
            if org.get_config("common.is_global"):
                state_name = remote.fields.get(contact_fields.get(state_field), None)
                if state_name:
                    state = state_name

            else:
                state_path = remote.fields.get(contact_fields.get(state_field), None)
                if state_path:
                    state_name = state_path.split(" > ")[-1]
                    state_name = state_name.lower()
                    state = org_state_boundaries_data.get(state_name, "")

                district_field = org.get_config("%s.district_label" % self.backend.slug, default="")
                if district_field:
                    district_field = district_field.lower()
                    district_path = remote.fields.get(contact_fields.get(district_field), None)
                    if district_path:
                        district_name = district_path.split(" > ")[-1]
                        district_name = district_name.lower()
                        district = org_district_boundaries_data.get(state, dict()).get(district_name, "")

                ward_field = org.get_config("%s.ward_label" % self.backend.slug, default="")
                if ward_field:
                    ward_field = ward_field.lower()
                    ward_path = remote.fields.get(contact_fields.get(ward_field), None)
                    if ward_path:
                        ward_name = ward_path.split(" > ")[-1]
                        ward_name = ward_name.lower()
                        ward = org_ward_boundaries_data.get(district, dict()).get(ward_name, "")

        registered_on = None
        registration_field = org.get_config("%s.registration_label" % self.backend.slug, default="")
        if registration_field:
            registration_field = registration_field.lower()
            registered_on = remote.fields.get(contact_fields.get(registration_field), None)
            if registered_on:
                registered_on = json_date_to_datetime(registered_on)

        if not registered_on:
            # default to created_on to avoid null in the PG triggers
            registered_on = remote.created_on

        occupation = ""
        occupation_field = org.get_config("%s.occupation_label" % self.backend.slug, default="")
        if occupation_field:
            occupation_field = occupation_field.lower()
            occupation = remote.fields.get(contact_fields.get(occupation_field), "")
            if not occupation:
                occupation = ""

        born = 0
        born_field = org.get_config("%s.born_label" % self.backend.slug, default="")
        if born_field:
            born_field = born_field.lower()
            try:
                born = int(remote.fields.get(contact_fields.get(born_field), 0))

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
        extra_gender = org.get_config("common.has_extra_gender", default=False)

        if gender_field:
            gender_field = gender_field.lower()
            gender = remote.fields.get(contact_fields.get(gender_field), "")

            if gender and gender.lower() == female_label.lower():
                gender = self.model.FEMALE
            elif gender and gender.lower() == male_label.lower():
                gender = self.model.MALE
            elif gender and extra_gender:
                gender = self.model.OTHER
            else:
                gender = ""

        scheme, path = remote.urns[0].split(":", 1)

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
            "scheme": scheme,
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
                local.scheme != local_kwargs["scheme"],
            ]
        )

    def update_local(self, local, remote_as_kwargs):
        local = super().update_local(local, remote_as_kwargs)

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ContactActivity.objects.filter(org_id=local.org_id, contact=local.uuid, date__gte=start_of_month).update(
            gender=local.gender,
            born=local.born,
            state=local.state,
            district=local.district,
            ward=local.ward,
            scheme=local.scheme,
            used=True,
        )

        return local


class RapidProBackend(BaseBackend):
    """
    RapidPro instance as a backend
    """

    @staticmethod
    def _get_client(org, api_version):
        from temba_client.v2.types import Field

        def convert_old_fields(clazz, item):
            if clazz == Field:
                item["name"] = item.get("name") or item.get("label")
                item["type"] = (
                    "number" if item.get("value_type") == "numeric" else item.get("type") or item.get("value_type")
                )
            return item

        return org.get_temba_client(api_version=api_version, transformer=convert_old_fields)

    def fetch_flows(self, org):
        client = self._get_client(org, 2)
        flows = client.get_flows().all()

        all_flows = dict()
        for flow in flows:
            flow_json = dict()
            flow_json["uuid"] = flow.uuid
            flow_json["date_hint"] = flow.created_on.strftime("%Y-%m-%d")
            flow_json["created_on"] = datetime_to_json_date(flow.created_on)
            flow_json["name"] = flow.name
            flow_json["archived"] = flow.archived
            flow_json["runs"] = flow.runs.active + flow.runs.expired + flow.runs.completed + flow.runs.interrupted
            flow_json["completed_runs"] = flow.runs.completed
            flow_json["results"] = [
                {"key": elt.key, "name": elt.name, "categories": elt.categories, "node_uuids": elt.node_uuids}
                for elt in flow.results
            ]

            all_flows[flow.uuid] = flow_json
        return all_flows

    def get_definition(self, org, flow_uuid):
        client = self._get_client(org, 2)
        export_definition = client.get_definitions(flows=(flow_uuid,))

        flow_definition = None

        for flow_def in export_definition.flows:
            def_flow_uuid = flow_def.get("metadata", dict()).get("uuid", None)

            if def_flow_uuid and def_flow_uuid == flow_uuid:
                flow_definition = flow_def
                break
        return flow_definition

    def update_poll_questions(self, org, poll, user):
        api_flow = poll.get_flow()

        flow_results = api_flow["results"]

        for result in flow_results:
            label = result["name"]
            ruleset_uuid = result["node_uuids"][-1]
            ruleset_type = "wait_message"

            question = PollQuestion.update_or_create(user, poll, label, ruleset_uuid, ruleset_type)

            for category in result["categories"]:
                PollResponseCategory.update_or_create(question, None, category)

            # deactivate if corresponding rules are removed
            PollResponseCategory.objects.filter(question=question).exclude(category__in=result["categories"]).update(
                is_active=False
            )
            FlowResultCategory.objects.filter(flow_result=question.flow_result).exclude(
                category__in=result["categories"]
            ).update(is_active=False)

    def pull_fields(self, org):
        client = self._get_client(org, 2)
        incoming_objects = client.get_fields().all(retry_on_rate_exceed=True)

        return sync_local_to_set(org, FieldSyncer(backend=self.backend), incoming_objects)

    def pull_boundaries(self, org):
        if org.get_config("common.is_global"):
            incoming_objects = Boundary.build_global_boundaries()
        else:
            client = self._get_client(org, 2)
            incoming_objects = client.get_boundaries(geometry=True).all()

        return sync_local_to_set(org, BoundarySyncer(backend=self.backend), incoming_objects)

    def pull_contacts(self, org, modified_after, modified_before, progress_callback=None):
        client = self._get_client(org, 2)

        # all contacts created or modified in RapidPro in the time window
        active_query = client.get_contacts(after=modified_after, before=modified_before)
        fetches = active_query.iterfetches(retry_on_rate_exceed=True)

        # all contacts deleted in RapidPro in the same time window
        deleted_query = client.get_contacts(deleted=True, after=modified_after, before=modified_before)
        deleted_fetches = deleted_query.iterfetches(retry_on_rate_exceed=True)

        return sync_local_to_changes(
            org, ContactSyncer(backend=self.backend), fetches, deleted_fetches, progress_callback
        )

    def _iter_archive_records(self, archive, flow_uuid):
        r = requests.get(archive.download_url, stream=True)
        stream = gzip.GzipFile(fileobj=io.BytesIO(r.content))

        while True:
            line = stream.readline()
            if not line:
                break
            line_decoded = line.decode("utf-8")
            if line_decoded.find(flow_uuid) > 0:
                yield json.loads(line_decoded)

    def _iter_poll_record_runs(self, archive, poll_flow_uuid):
        for record_batch in chunk_list(self._iter_archive_records(archive, poll_flow_uuid), 1000):
            matching = []
            for record in record_batch:
                if record["flow"]["uuid"] == poll_flow_uuid:
                    record.update(start=None)
                    matching.append(record)
            yield Run.deserialize_list(matching)

    def pull_results_from_archives(self, poll):
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

        if poll.stopped_syncing:
            return (
                stats_dict["num_val_created"],
                stats_dict["num_val_updated"],
                stats_dict["num_val_ignored"],
                stats_dict["num_path_created"],
                stats_dict["num_path_updated"],
                stats_dict["num_path_ignored"],
            )

        with r.lock(key):
            flow_date_json = poll.get_flow_date()
            first = (
                json_date_to_datetime(flow_date_json).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if flow_date_json
                else None
            )

            client = self._get_client(org, 2)

            questions_uuids = poll.get_question_uuids()
            archives_query = client.get_archives(type="run", after=first)
            archives_fetches = archives_query.iterfetches(retry_on_rate_exceed=True)

            i = 0
            for archives in archives_fetches:
                for archive in archives:
                    i += 1
                    logger.info("Archive %d with %d records, size %d" % (i, archive.record_count, archive.size))

                    try:
                        start_archive = time.time()
                        logger.info("Archive %d has %d records" % (i, archive.record_count))

                        if archive.record_count <= 0:
                            continue

                        flow_uuid = poll.flow_uuid

                        for fetch in self._iter_poll_record_runs(archive, flow_uuid):
                            fetch_start = time.time()

                            (contacts_map, poll_results_map, poll_results_to_save_map) = self._initiate_lookup_maps(
                                fetch, org, poll
                            )

                            for temba_run in fetch:
                                contact_obj = contacts_map.get(temba_run.contact.uuid, None)
                                self._process_run_poll_results(
                                    org,
                                    questions_uuids,
                                    temba_run,
                                    contact_obj,
                                    poll_results_map,
                                    poll_results_to_save_map,
                                    stats_dict,
                                )

                            stats_dict["num_synced"] += len(fetch)

                            self._save_new_poll_results_to_database(poll_results_to_save_map)

                            logger.info(
                                "Processing archive %d took %ds for fetch of %d"
                                % (i, time.time() - fetch_start, len(fetch))
                            )

                        logger.info("Full poll process archive in %ds" % (time.time() - start_archive))
                    except Exception as e:
                        logger.info(e)
                        import traceback

                        traceback.print_exc()

        return (
            stats_dict["num_val_created"],
            stats_dict["num_val_updated"],
            stats_dict["num_val_ignored"],
            stats_dict["num_path_created"],
            stats_dict["num_path_updated"],
            stats_dict["num_path_ignored"],
        )

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

        if poll.stopped_syncing:
            return (
                stats_dict["num_val_created"],
                stats_dict["num_val_updated"],
                stats_dict["num_val_ignored"],
                stats_dict["num_path_created"],
                stats_dict["num_path_updated"],
                stats_dict["num_path_ignored"],
            )

        if r.get(key):
            logger.info("Skipping pulling results for poll #%d on org #%d as it is still running" % (poll.pk, org.pk))
        else:
            with r.lock(key, timeout=Poll.POLL_SYNC_LOCK_TIMEOUT):
                lock_expiration = time.time() + 0.8 * Poll.POLL_SYNC_LOCK_TIMEOUT
                client = self._get_client(org, 2)

                questions_uuids = poll.get_question_uuids()

                # ignore the TaskState time and use the time we stored in valkey
                (
                    latest_synced_obj_time,
                    pull_after_delete,
                ) = poll.get_pull_cached_params()

                if pull_after_delete is not None:
                    latest_synced_obj_time = None
                    poll.delete_poll_results()
                    pull_refresh_from_archives.apply_async((poll.pk,), queue="sync")

                start = time.time()
                logger.info("Start fetching runs for poll #%d on org #%d" % (poll.pk, org.pk))

                # fetch runs from API, respecting rate limits
                poll_runs_query = client.get_runs(
                    flow=poll.flow_uuid, after=latest_synced_obj_time, reverse=True, paths=True
                )
                fetches = poll_runs_query.iterfetches(retry_on_rate_exceed=True)

                try:
                    fetch_start = time.time()

                    for fetch in fetches:
                        logger.info(
                            "RapidPro API fetch for poll #%d "
                            "on org #%d %d - %d took %ds"
                            % (
                                poll.pk,
                                org.pk,
                                stats_dict["num_synced"],
                                stats_dict["num_synced"] + len(fetch),
                                time.time() - fetch_start,
                            )
                        )

                        # for each API page fetched, initiate the maps for quick lookups and as cache for the sync task
                        (contacts_map, poll_results_map, poll_results_to_save_map) = self._initiate_lookup_maps(
                            fetch, org, poll
                        )

                        for temba_run in fetch:
                            if latest_synced_obj_time is None or temba_run.modified_on > json_date_to_datetime(
                                latest_synced_obj_time
                            ):
                                latest_synced_obj_time = datetime_to_json_date(
                                    temba_run.modified_on.replace(tzinfo=tzone.utc)
                                )

                            contact_obj = contacts_map.get(temba_run.contact.uuid, None)
                            # for each run process, the results we can for the values and path for not yet responded
                            self._process_run_poll_results(
                                org,
                                questions_uuids,
                                temba_run,
                                contact_obj,
                                poll_results_map,
                                poll_results_to_save_map,
                                stats_dict,
                            )

                        stats_dict["num_synced"] += len(fetch)
                        if progress_callback:
                            progress_callback(stats_dict["num_synced"])

                        # Save the objects to the DB for new objects in the respective map
                        self._save_new_poll_results_to_database(poll_results_to_save_map)

                        logger.info(
                            "Processed fetch of %d - %d "
                            "runs for poll #%d on org #%d"
                            % (stats_dict["num_synced"] - len(fetch), stats_dict["num_synced"], poll.pk, org.pk)
                        )
                        fetch_start = time.time()
                        logger.info("=" * 40)

                        # Pause the sync for this poll when we have synced Poll.POLL_RESULTS_MAX_SYNC_RUNS runs this time
                        if (
                            stats_dict["num_synced"] >= Poll.POLL_RESULTS_MAX_SYNC_RUNS
                            or time.time() > lock_expiration
                        ):
                            # rebuild the aggregated counts
                            poll.rebuild_poll_results_counts()

                            # mark this poll as paused, so we can resume from the proper time later
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
                except TembaRateExceededError:
                    # rebuild the aggregated counts
                    poll.rebuild_poll_results_counts()

                    # mark this poll as paused, so we can resume from the proper time later
                    self._mark_poll_results_sync_paused(org, poll, latest_synced_obj_time)

                    logger.info(
                        "Break pull results for poll #%d on org #%d in %ds, "
                        "Times: sync_latest= %s,"
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

                # mark this poll as completed, so we can fetch from the proper time for future results from that time
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
                    "Times: sync_latest= %s, "
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
        """
        - Lookup existing contact from the contact uuid in the runs batch
        - Build look up maps (existing contacts, existing results) by contact UUID for quick finding the existing objects
        - Make maps for new results object to add to the DB in bulk (by bulk_create).
        """

        contact_uuids = [run.contact.uuid for run in fetch]
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
        questions_uuids,
        temba_run,
        contact_obj,
        existing_db_poll_results_map,
        poll_results_to_save_map,
        stats_dict,
    ):
        """
        This method is to extract results from the run, we fetch from the RapidPro API.
        If uses the maps intiated by each API page request to reduce the DB queries.
        - First look on values for results set on the run and save them
        - Second loop on the path to save the path for which the contact is waiting for a response/result to be set
        - For each case we only update the lookup maps
        """

        flow_uuid = temba_run.flow.uuid
        contact_uuid = temba_run.contact.uuid
        completed = temba_run.exit_type == "completed"

        state = ""
        district = ""
        ward = ""
        born = None
        gender = None
        scheme = ""
        if contact_obj is not None:
            state = contact_obj.state
            district = contact_obj.district
            ward = contact_obj.ward
            born = contact_obj.born
            gender = contact_obj.gender
            scheme = contact_obj.scheme

        # Loop on values set for the run to save the results responses,
        # used to get the number of responded reporters for a question
        for temba_value in sorted(temba_run.values.values(), key=lambda val: val.time):
            ruleset_uuid = temba_value.node
            category = temba_value.category
            text = temba_value.value[:1600] if temba_value.value is not None else temba_value.value
            value_date = temba_value.time

            existing_poll_result = existing_db_poll_results_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

            poll_result_to_save = poll_results_to_save_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

            if existing_poll_result is not None:
                # exising obj in the DB, check whether that needs update and update both the DB and the maps obj fields
                update_required = self._check_update_required(
                    existing_poll_result,
                    category,
                    text,
                    state,
                    district,
                    ward,
                    born,
                    gender,
                    scheme,
                    completed,
                    value_date,
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
                        scheme=scheme,
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
                    existing_poll_result.scheme = scheme
                    existing_poll_result.completed = completed

                    existing_db_poll_results_map[contact_uuid][ruleset_uuid] = existing_poll_result

                    stats_dict["num_val_updated"] += 1
                else:
                    stats_dict["num_val_ignored"] += 1

            elif poll_result_to_save is not None:
                # exising obj in the maps, check whether that needs to be replaced in the maps, that will be saved later in bulk to the DB
                replace_save_map = self._check_update_required(
                    poll_result_to_save,
                    category,
                    text,
                    state,
                    district,
                    ward,
                    born,
                    gender,
                    scheme,
                    completed,
                    value_date,
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
                        scheme=scheme,
                        date=value_date,
                        completed=completed,
                    )

                    poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

                stats_dict["num_val_ignored"] += 1
            else:
                # completely new results to save to the DB, add that to the maps now to be saved in DB later in bulk
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
                    scheme=scheme,
                    date=value_date,
                    completed=completed,
                )

                poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

                stats_dict["num_val_created"] += 1

        # Loop on paths to save the results without responses,
        # used to get the number of polled reporters for a question
        for temba_path in temba_run.path:
            ruleset_uuid = temba_path.node
            category = None
            text = ""
            value_date = temba_run.created_on

            if ruleset_uuid in questions_uuids:
                existing_poll_result = existing_db_poll_results_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

                poll_result_to_save = poll_results_to_save_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

                if existing_poll_result is not None:
                    # exiting obj in the DB, check whether that need to be updated when the non response happened after 5 seconds
                    # sometimes the path is the same or close time as the value(result) time
                    if existing_poll_result.date is None or value_date > (
                        existing_poll_result.date + timedelta(seconds=5)
                    ):
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
                            scheme=scheme,
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
                        existing_poll_result.scheme = scheme
                        existing_poll_result.completed = completed

                        existing_db_poll_results_map[contact_uuid][ruleset_uuid] = existing_poll_result

                        stats_dict["num_path_updated"] += 1
                    else:
                        stats_dict["num_path_ignored"] += 1

                elif poll_result_to_save is not None:
                    # Only replace existing results in maps when the non response happened after 5 seconds
                    # sometimes the path is the same or close time as the value(result) time
                    if value_date > (poll_result_to_save.date + timedelta(seconds=5)):
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
                            scheme=scheme,
                            date=value_date,
                            completed=completed,
                        )

                        poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

                    stats_dict["num_path_ignored"] += 1

                else:
                    # new obj to add, add in the maps first to save to DB later
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
                        scheme=scheme,
                        date=value_date,
                        completed=completed,
                    )

                    poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

                    stats_dict["num_path_created"] += 1

            else:
                stats_dict["num_path_ignored"] += 1

    @staticmethod
    def _check_update_required(
        poll_obj, category, text, state, district, ward, born, gender, scheme, completed, value_date
    ):
        """
        To check whether any value need to be updated in the DB,
        if the syncing data is newer/changed to what we have in the DB
        """
        update_required = poll_obj.category != category or poll_obj.text != text
        update_required = update_required or poll_obj.state != state
        update_required = update_required or poll_obj.district != district
        update_required = update_required or poll_obj.ward != ward
        update_required = update_required or poll_obj.born != born
        update_required = update_required or poll_obj.gender != gender
        update_required = update_required or poll_obj.scheme != scheme
        update_required = update_required or poll_obj.completed != completed
        # if the reporter answered the step, check if this is a newer run
        if poll_obj.date is not None:
            update_required = update_required and (value_date > poll_obj.date)
        else:
            update_required = True
        return update_required

    @staticmethod
    def _save_new_poll_results_to_database(poll_results_to_save_map):
        """
        Save all the new objects to create to the DB in bulk, by bulk_create
        """
        new_poll_results = []
        for c_key in poll_results_to_save_map.keys():
            for r_key in poll_results_to_save_map.get(c_key, dict()):
                obj_to_create = poll_results_to_save_map.get(c_key, dict()).get(r_key, None)
                if obj_to_create is not None:
                    new_poll_results.append(obj_to_create)
        PollResult.objects.bulk_create(new_poll_results, batch_size=1000)

    @staticmethod
    def _mark_poll_results_sync_paused(org, poll, latest_synced_obj_time):
        """
        Use valkey to set the time when we paused, where we will resume from.
        This is a way to allow sharing the API throttle rate to multiple polls, to allow each to progress
        """
        # update the time for this poll from which we fetch next time
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (org.pk, poll.flow_uuid), latest_synced_obj_time, None)

        from ureport.polls.tasks import pull_refresh

        pull_refresh.apply_async((poll.pk,), countdown=300, queue="sync")

    @staticmethod
    def _mark_poll_results_sync_completed(poll, org, latest_synced_obj_time):
        """
        Use Valkey key to mark we finished to sync existing results.
        And future sync will only look for newer results that the time in Valkey.
        """

        # update the time for this poll from which we fetch next time
        cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (org.pk, poll.flow_uuid), latest_synced_obj_time, None)

        # update the last time the sync happened, for displaying in polls list on admin page
        now = timezone.now()
        cache.set(
            Poll.POLL_RESULTS_LAST_SYNC_TIME_CACHE_KEY % (org.pk, poll.flow_uuid),
            datetime_to_json_date(now),
            None,
        )

        # Use valkey cache with expiring(in 48 hrs) key to allow other polls task
        # to sync all polls without hitting the API rate limit
        cache.set(
            Poll.POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_KEY % (org.id, poll.flow_uuid),
            datetime_to_json_date(now),
            Poll.POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_TIMEOUT,
        )

        Poll.objects.filter(id=poll.pk).update(modified_on=now)
