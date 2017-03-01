from __future__ import unicode_literals

from collections import defaultdict
import json

import pytz
import time
from dash.utils import is_dict_equal
from dash.utils.sync import BaseSyncer, sync_local_to_set, sync_local_to_changes
from django.core.cache import cache
from django.utils import timezone

from django_redis import get_redis_connection

from ureport.contacts.models import ContactField, Contact
from ureport.locations.models import Boundary
from ureport.polls.models import PollResult, Poll, PollResultsCounter
from ureport.utils import datetime_to_json_date, json_date_to_datetime
from . import BaseBackend


class FieldSyncer(BaseSyncer):
    """
    Syncer for contact fields
    """
    model = ContactField
    local_id_attr = 'key'
    remote_id_attr = 'key'

    def local_kwargs(self, org, remote):
        return {
            'org': org,
            'key': remote.key,
            'label': remote.label,
            'value_type': self.model.TEMBA_TYPES.get(remote.value_type, self.model.TYPE_TEXT)
        }

    def update_required(self, local, remote, local_kwags):
        return local.label != remote.label or local.value_type != self.model.TEMBA_TYPES.get(remote.value_type)

    def delete_local(self, local):
        local.release()


class BoundarySyncer(BaseSyncer):
    """
    syncer for location boundaries
    """
    model = Boundary
    local_id_attr = 'osm_id'
    remote_id_attr = 'osm_id'

    def local_kwargs(self, org, remote):
        geometry = json.dumps(dict(type=remote.geometry.type, coordinates=remote.geometry.coordinates))

        parent = None
        if remote.parent:
            parent = Boundary.objects.filter(osm_id__iexact=remote.parent.osm_id, org=org).first()

        return {
            'org': org,
            'geometry': geometry,
            'parent': parent,
            'level': remote.level,
            'name': remote.name,
            'osm_id': remote.osm_id
        }

    def update_required(self, local, remote, local_kwargs):
        if local.name != remote.name:
            return True

        if local.level != remote.level:
            return True

        if remote.parent:
            if not local.parent:
                return True
            elif local.parent.osm_id != remote.parent.osm_id:
                return True

        return not is_dict_equal(json.loads(local.geometry),
                                 dict(type=remote.geometry.type, coordinates=remote.geometry.coordinates))

    def delete_local(self, local):
        local.release()


class ContactSyncer(BaseSyncer):
    model = Contact

    def get_boundaries_data(self, org):

        cache_attr = '__boundaries__%d' % org.pk
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

    def get_contact_fields(self, org):
        cache_attr = '__contact_fields__%d' % org.pk
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)
        contact_fields = ContactField.objects.filter(org=org)
        contact_fields_data = {elt.label.lower(): elt.key for elt in contact_fields}

        setattr(self, cache_attr, contact_fields_data)
        return contact_fields_data

    def local_kwargs(self, org, remote):
        from ureport.utils import json_date_to_datetime

        reporter_group = org.get_config('reporter_group')
        contact_groups_names = [group.name.lower() for group in remote.groups]

        if not reporter_group.lower() in contact_groups_names:
            return None

        org_state_boundaries_data, org_district_boundaries_data, org_ward_boundaries_data = self.get_boundaries_data(org)
        contact_fields = self.get_contact_fields(org)

        state = ''
        district = ''
        ward = ''

        state_field = org.get_config('state_label')
        if state_field:
            state_field = state_field.lower()
            if org.get_config('is_global'):
                state_name = remote.fields.get(contact_fields.get(state_field), None)
                if state_name:
                    state = state_name

            else:
                state_name = remote.fields.get(contact_fields.get(state_field), None)
                if state_name:
                    state_name = state_name.lower()
                    state = org_state_boundaries_data.get(state_name, '')

                district_field = org.get_config('district_label')
                if district_field:
                    district_field = district_field.lower()
                    district_name = remote.fields.get(contact_fields.get(district_field), None)
                    if district_name:
                        district_name = district_name.lower()
                        district = org_district_boundaries_data.get(state, dict()).get(district_name, '')

                ward_field = org.get_config('ward_label')
                if ward_field:
                    ward_field = ward_field.lower()
                    ward_name = remote.fields.get(contact_fields.get(ward_field), None)
                    if ward_name:
                        ward_name = ward_name.lower()
                        ward = org_ward_boundaries_data.get(district, dict()).get(ward_name, '')

        registered_on = None
        registration_field = org.get_config('registration_label')
        if registration_field:
            registration_field = registration_field.lower()
            registered_on = remote.fields.get(contact_fields.get(registration_field), None)
            if registered_on:
                registered_on = json_date_to_datetime(registered_on)

        occupation = ''
        occupation_field = org.get_config('occupation_label')
        if occupation_field:
            occupation_field = occupation_field.lower()
            occupation = remote.fields.get(contact_fields.get(occupation_field), '')
            if not occupation:
                occupation = ''

        born = 0
        born_field = org.get_config('born_label')
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

        gender = ''
        gender_field = org.get_config('gender_label')
        female_label = org.get_config('female_label')
        male_label = org.get_config('male_label')

        if gender_field:
            gender_field = gender_field.lower()
            gender = remote.fields.get(contact_fields.get(gender_field), '')

            if gender and gender.lower() == female_label.lower():
                gender = self.model.FEMALE
            elif gender and gender.lower() == male_label.lower():
                gender = self.model.MALE
            else:
                gender = ''

        return {
            'org': org,
            'uuid': remote.uuid,
            'gender': gender,
            'born': born,
            'occupation': occupation,
            'registered_on': registered_on,
            'state': state,
            'district': district,
            'ward': ward
        }

    def update_required(self, local, remote, local_kwargs):
        if not local_kwargs:
            return True

        update = local.gender != local_kwargs['gender'] or local.born != local_kwargs['born']
        update = update or local.occupation != local_kwargs['occupation']
        update = update or local.registered_on != local_kwargs['registered_on']
        update = update or local.state != local_kwargs['state'] or local.district != local_kwargs['district']
        update = update or local.ward != local_kwargs['ward']

        return update


class RapidProBackend(BaseBackend):
    """
    RapidPro instance as a backend
    """
    @staticmethod
    def _get_client(org, api_version):
        return org.get_temba_client(api_version=api_version)

    def pull_fields(self, org):
        client = self._get_client(org, 2)
        incoming_objects = client.get_fields().all(retry_on_rate_exceed=True)

        return sync_local_to_set(org, FieldSyncer(), incoming_objects)

    def pull_boundaries(self, org):

        if org.get_config('is_global'):
            incoming_objects = Boundary.build_global_boundaries()
        else:
            client = self._get_client(org, 2)
            incoming_objects = client.get_boundaries().all()

        return sync_local_to_set(org, BoundarySyncer(), incoming_objects)

    def pull_contacts(self, org, modified_after, modified_before, progress_callback=None):
        client = self._get_client(org, 2)

        # all contacts created or modified in RapidPro in the time window
        active_query = client.get_contacts(after=modified_after, before=modified_before)
        fetches = active_query.iterfetches(retry_on_rate_exceed=True)

        # all contacts deleted in RapidPro in the same time window
        deleted_query = client.get_contacts(deleted=True, after=modified_after, before=modified_before)
        deleted_fetches = deleted_query.iterfetches(retry_on_rate_exceed=True)

        return sync_local_to_changes(org, ContactSyncer(), fetches, deleted_fetches, progress_callback)

    def pull_results(self, poll, modified_after, modified_before, progress_callback=None):
        org = poll.org
        r = get_redis_connection()
        key = Poll.POLL_PULL_RESULTS_TASK_LOCK % (org.pk, poll.flow_uuid)

        num_val_created = 0
        num_val_updated = 0
        num_val_ignored = 0

        num_path_created = 0
        num_path_updated = 0
        num_path_ignored = 0

        num_synced = 0

        if r.get(key):
            print "Skipping pulling results for poll #%d on org #%d as it is still running" % (poll.pk, org.pk)
        else:
            with r.lock(key, timeout=Poll.POLL_SYNC_LOCK_TIMEOUT):
                client = self._get_client(org, 2)

                questions_uuids = poll.get_question_uuids()

                # ignore the TaskState time and use the time we stored in redis
                (after, before, latest_synced_obj_time,
                 batches_latest, resume_cursor, pull_after_delete) = poll.get_pull_cached_params()

                if resume_cursor is None:
                    before = datetime_to_json_date(timezone.now())
                    after = latest_synced_obj_time

                if pull_after_delete is not None:
                    after = None
                    poll.delete_poll_results()

                start = time.time()
                print "Start fetching runs for poll #%d on org #%d" % (poll.pk, org.pk)

                poll_runs_query = client.get_runs(flow=poll.flow_uuid, after=after, before=before)
                fetches = poll_runs_query.iterfetches(retry_on_rate_exceed=True, resume_cursor=resume_cursor)

                fetch_start = time.time()
                for fetch in fetches:

                    print "RapidPro API fetch for poll #%d on org #%d %d - %d took %ds" % (poll.pk, org.pk, num_synced,
                                                                                           num_synced + len(fetch),
                                                                                           time.time() - fetch_start)

                    contact_uuids = [run.contact.uuid for run in fetch]
                    contacts = Contact.objects.filter(org=org, uuid__in=contact_uuids)
                    contacts_map = {c.uuid: c for c in contacts}

                    existing_poll_results = PollResult.objects.filter(flow=poll.flow_uuid, org=poll.org_id, contact__in=contact_uuids)

                    poll_results_map = defaultdict(dict)
                    for res in existing_poll_results:
                        poll_results_map[res.contact][res.ruleset] = res

                    poll_results_to_save_map = defaultdict(dict)

                    for temba_run in fetch:

                        if batches_latest is None or temba_run.modified_on > json_date_to_datetime(batches_latest):
                            batches_latest = datetime_to_json_date(temba_run.modified_on.replace(tzinfo=pytz.utc))

                        flow_uuid = temba_run.flow.uuid
                        contact_uuid = temba_run.contact.uuid
                        completed = temba_run.exit_type == 'completed'

                        contact_obj = contacts_map.get(contact_uuid, None)

                        state = ''
                        district = ''
                        ward = ''
                        born = None
                        gender = None
                        if contact_obj is not None:
                            state = contact_obj.state
                            district = contact_obj.district
                            ward = contact_obj.ward
                            born = contact_obj.born
                            gender = contact_obj.gender

                        temba_values = temba_run.values.values()
                        temba_values.sort(key=lambda val: val.time)

                        for temba_value in temba_values:
                            ruleset_uuid = temba_value.node
                            category = temba_value.category
                            text = temba_value.value
                            value_date = temba_value.time

                            existing_poll_result = poll_results_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

                            poll_result_to_save = poll_results_to_save_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

                            if existing_poll_result is not None:

                                update_required = existing_poll_result.category != category or existing_poll_result.text != text
                                update_required = update_required or existing_poll_result.state != state
                                update_required = update_required or existing_poll_result.district != district
                                update_required = update_required or existing_poll_result.ward != ward
                                update_required = update_required or existing_poll_result.born != born
                                update_required = update_required or existing_poll_result.gender != gender
                                update_required = update_required or existing_poll_result.completed != completed

                                # if the reporter answered the step, check if this is a newer run
                                if existing_poll_result.date is not None:
                                     update_required = update_required and (value_date > existing_poll_result.date)
                                else:
                                    update_required = True

                                if update_required:
                                    # update the db object
                                    PollResult.objects.filter(pk=existing_poll_result.pk).update(category=category, text=text,
                                                                                                 state=state, district=district,
                                                                                                 ward=ward, date=value_date,
                                                                                                 born=born, gender=gender,
                                                                                                 completed=completed)

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

                                    poll_results_map[contact_uuid][ruleset_uuid] = existing_poll_result

                                    num_val_updated += 1
                                else:
                                    num_val_ignored += 1

                            elif poll_result_to_save is not None:

                                replace_save_map = poll_result_to_save.category != category or poll_result_to_save.text != text
                                replace_save_map = replace_save_map or poll_result_to_save.state != state
                                replace_save_map = replace_save_map or poll_result_to_save.district != district
                                replace_save_map = replace_save_map or poll_result_to_save.ward != ward
                                replace_save_map = replace_save_map or poll_result_to_save.born != born
                                replace_save_map = replace_save_map or poll_result_to_save.gender != gender
                                replace_save_map = replace_save_map or poll_result_to_save.completed != completed

                                # replace if the step is newer
                                if poll_result_to_save.date is not None:
                                    replace_save_map = replace_save_map and (value_date > poll_result_to_save.date)

                                if replace_save_map:
                                    result_obj = PollResult(org=org, flow=flow_uuid, ruleset=ruleset_uuid,
                                                            contact=contact_uuid, category=category, text=text,
                                                            state=state, district=district, ward=ward,
                                                            born=born, gender=gender,
                                                            date=value_date, completed=completed)

                                    poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

                                num_val_ignored += 1
                            else:

                                result_obj = PollResult(org=org, flow=flow_uuid, ruleset=ruleset_uuid,
                                                        contact=contact_uuid, category=category, text=text,
                                                        state=state, district=district, ward=ward, born=born,
                                                        gender=gender, date=value_date, completed=completed)

                                poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

                                num_val_created += 1

                        for temba_path in temba_run.path:
                            ruleset_uuid = temba_path.node
                            category = None
                            text = ""
                            value_date = temba_path.time

                            if ruleset_uuid in questions_uuids:
                                existing_poll_result = poll_results_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

                                poll_result_to_save = poll_results_to_save_map.get(contact_uuid, dict()).get(ruleset_uuid, None)

                                if existing_poll_result is not None:
                                    if existing_poll_result.date is None or value_date > existing_poll_result.date:
                                        # update the db object
                                        PollResult.objects.filter(pk=existing_poll_result.pk).update(category=category,
                                                                                                     text=text,
                                                                                                     state=state,
                                                                                                     district=district,
                                                                                                     ward=ward,
                                                                                                     date=value_date,
                                                                                                     born=born,
                                                                                                     gender=gender,
                                                                                                     completed=completed)

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

                                        poll_results_map[contact_uuid][ruleset_uuid] = existing_poll_result

                                        num_path_updated += 1
                                    else:
                                        num_path_ignored += 1

                                elif poll_result_to_save is not None:
                                    if value_date > poll_result_to_save.date:
                                        result_obj = PollResult(org=org, flow=flow_uuid, ruleset=ruleset_uuid,
                                                                contact=contact_uuid, category=category, text=text,
                                                                state=state, district=district, ward=ward,
                                                                born=born, gender=gender,
                                                                date=value_date, completed=completed)

                                        poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

                                    num_path_ignored += 1

                                else:

                                    result_obj = PollResult(org=org, flow=flow_uuid, ruleset=ruleset_uuid,
                                                            contact=contact_uuid, category=category, text=text,
                                                            state=state, district=district, ward=ward, born=born,
                                                            gender=gender, date=value_date, completed=completed)

                                    poll_results_to_save_map[contact_uuid][ruleset_uuid] = result_obj

                                    num_path_created += 1

                            else:
                                num_path_ignored += 1

                    num_synced += len(fetch)
                    if progress_callback:
                        progress_callback(num_synced)

                    new_poll_results = []

                    for c_key in poll_results_to_save_map.keys():
                        for r_key in poll_results_to_save_map.get(c_key, dict()):
                            obj_to_create = poll_results_to_save_map.get(c_key, dict()).get(r_key, None)
                            if obj_to_create is not None:
                                new_poll_results.append(obj_to_create)

                    PollResult.objects.bulk_create(new_poll_results)

                    print "Processed fetch of %d - %d runs for poll #%d on org #%d" % (num_synced - len(fetch),
                                                                                       num_synced,
                                                                                       poll.pk,
                                                                                       org.pk)
                    fetch_start = time.time()
                    print "=" * 40

                    if num_synced >= Poll.POLL_RESULTS_MAX_SYNC_RUNS:
                        poll.rebuild_poll_results_counts()
                        cursor = fetches.get_cursor()

                        cache.set(Poll.POLL_RESULTS_LAST_PULL_CURSOR % (org.pk, poll.flow_uuid), cursor, None)

                        cache.set(Poll.POLL_RESULTS_CURSOR_AFTER_CACHE_KEY % (org.pk, poll.flow_uuid),
                                  after, None)

                        cache.set(Poll.POLL_RESULTS_CURSOR_BEFORE_CACHE_KEY % (org.pk, poll.flow_uuid),
                                  before, None)

                        cache.set(Poll.POLL_RESULTS_BATCHES_LATEST_CACHE_KEY % (org.pk, poll.flow_uuid),
                                  batches_latest, None)

                        print "Break pull results for poll #%d on org #%d in %ds, "\
                              " Times: after= %s, before= %s, batch_latest= %s, sync_latest= %s"\
                              " Objects: created %d, updated %d, ignored %d. " \
                              "Before cursor %s" % (poll.pk, org.pk, time.time() - start, after, before, batches_latest,
                                                    latest_synced_obj_time, num_val_created, num_val_updated,
                                                    num_val_ignored, cursor)

                        return (num_val_created, num_val_updated, num_val_ignored,
                                num_path_created, num_path_updated, num_path_ignored)

                if batches_latest is not None and (latest_synced_obj_time is None or json_date_to_datetime(latest_synced_obj_time) <= json_date_to_datetime(batches_latest)):
                    latest_synced_obj_time = batches_latest

                # update the time for this poll from which we fetch next time
                cache.set(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (org.pk, poll.flow_uuid),
                          latest_synced_obj_time, None)

                # clear the saved cursor
                cache.delete(Poll.POLL_RESULTS_LAST_PULL_CURSOR % (org.pk, poll.flow_uuid))

                # from django.db import connection as db_connection, reset_queries
                # slowest_queries = sorted(db_connection.queries, key=lambda q: q['time'], reverse=True)[:10]
                # for q in slowest_queries:
                #     print "=" * 60
                #     print "\n\n\n"
                #     print "%s -- %s" % (q['time'], q['sql'])
                # reset_queries()

                print "Finished pulling results for poll #%d on org #%d runs in %ds, " \
                      "Times: sync_latest= %s," \
                      "Objects: created %d, updated %d, ignored %d" % (poll.pk, org.pk, time.time() - start,
                                                                       latest_synced_obj_time,
                                                                       num_val_created, num_val_updated,
                                                                       num_val_ignored)
        return num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored