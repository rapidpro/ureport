from __future__ import unicode_literals

import json

import pytz
import time
from dash.utils import is_dict_equal
from dash.utils.sync import BaseSyncer, sync_local_to_set, sync_local_to_changes
from django.core.cache import cache
from django.utils import timezone

from ureport.contacts.models import ContactField, Contact
from ureport.locations.models import Boundary
from ureport.polls.models import PollResult
from ureport.utils import datetime_to_json_date
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

    def delete_locale(self, local):
        local.release()

class BoundarySyncer(BaseSyncer):
    """
    syncer for location boundaries
    """
    model = Boundary
    local_id_attr = 'osm_id'
    remote_id_attr = 'boundary'

    def local_kwargs(self, org, remote):
        geometry = json.dumps(dict(type=remote.geometry.type, coordinates=remote.geometry.coordinates))

        parent = Boundary.objects.filter(osm_id__iexact=remote.parent, org=org).first()

        return {
            'org': org,
            'geometry': geometry,
            'parent': parent,
            'level': remote.level,
            'name': remote.name,
            'osm_id': remote.boundary
        }

    def update_required(self, local, remote, local_kwargs):
        if local.name != remote.name:
            return True

        if local.level != remote.level:
            return True

        if remote.parent:
            if not local.parent:
                return True
            elif local.parent.osm_id != remote.parent:
                return True

        return not is_dict_equal(json.loads(local.geometry),
                                 dict(type=remote.geometry.type, coordinates=remote.geometry.coordinates))

    def delete_locale(self, local):
        local.release()


class ContactSyncer(BaseSyncer):
    model = Contact

    def get_boundaries_data(self, org):

        cache_attr = '__boundaries__%d' % org.pk
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)

        org_state_boundaries_data = dict()
        org_district_boundaries_data = dict()
        state_boundaries = Boundary.objects.filter(org=org, level=1)
        for state in state_boundaries:
            org_state_boundaries_data[state.name.lower()] = state.osm_id
            state_district_data = dict()
            district_boundaries = Boundary.objects.filter(org=org, level=2, parent=state)
            for district in district_boundaries:
                state_district_data[district.name.lower()] = district.osm_id

            org_district_boundaries_data[state.osm_id] = state_district_data

        setattr(self, cache_attr, (org_state_boundaries_data, org_district_boundaries_data))
        return org_state_boundaries_data, org_district_boundaries_data

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

        org_state_boundaries_data, org_district_boundaries_data = self.get_boundaries_data(org)
        contact_fields = self.get_contact_fields(org)

        state = ''
        district = ''

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
            'district': district
        }

    def update_required(self, local, remote, local_kwargs):
        if not local_kwargs:
            return True

        update = local.gender != local_kwargs['gender'] or local.born != local_kwargs['born']
        update = update or local.occupation != local_kwargs['occupation']
        update = update or local.registered_on != local_kwargs['registered_on']
        update = update or local.state != local_kwargs['state'] or local.district != local_kwargs['district']
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
            client = self._get_client(org, 1)
            incoming_objects = client.get_boundaries()

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
        client = self._get_client(org, 2)

        start = time.time()
        print "Start fetching runs for org #%d" % org.pk

        # ignore the TaskState time and use the time we stored in redis
        now = timezone.now()
        after = cache.get(PollResult.POLL_RESULTS_LAST_PULL_CACHE_KEY % (org.pk, poll.pk), None)

        poll_runs_query = client.get_runs(flow=poll.flow_uuid, responded=True, after=after, before=now)
        fetches = poll_runs_query.iterfetches(retry_on_rate_exceed=True)

        num_created = 0
        num_updated = 0
        num_ignored = 0
        num_synced = 0

        fetch_start = time.time()
        for fetch in fetches:

            print "RapidPro API fetch org #%d %d - %d took %ds" % (org.pk, num_synced, num_synced + len(fetch), time.time() - fetch_start)

            local_sync_start = time.time()

            for temba_run in fetch:
                flow_uuid = temba_run.flow.uuid
                contact_uuid = temba_run.contact.uuid
                completed = temba_run.exit_type == 'completed'

                contact_obj = Contact.get_or_create(org, contact_uuid)
                state = contact_obj.state
                district = contact_obj.district

                for temba_step in temba_run.steps:
                    ruleset_uuid = temba_step.node
                    category = temba_step.category
                    text = temba_step.text

                    if PollResult.objects.filter(org=org, flow=flow_uuid,
                                                 ruleset=ruleset_uuid, contact=contact_uuid).exists():

                        if not PollResult.objects.filter(org=org, flow=flow_uuid, ruleset=ruleset_uuid,
                                                         contact=contact_uuid,category=category, text=text,
                                                         state=state, district=district, completed=completed).exists():

                            PollResult.objects.filter(org=org, flow=flow_uuid,
                                                      ruleset=ruleset_uuid,
                                                      contact=contact_uuid).update(category=category, text=text,
                                                                                   state=state, district=district,
                                                                                   completed=completed)

                            num_updated += 1
                        else:
                            num_ignored += 1

                    else:
                        PollResult.objects.create(org=org, flow=flow_uuid, ruleset=ruleset_uuid, contact=contact_uuid,
                                                  category=category, text=text, state=state, date=temba_step.arrived_on,
                                                  district=district, completed=completed)

                        num_created += 1

            num_synced += len(fetch)
            if progress_callback:
                progress_callback(num_synced)

            print "Local sync ops org #%d %d - %d took %ds" % (org.pk, num_synced - len(fetch), num_synced, time.time() - local_sync_start)
            print "Total synced org #%d %d runs in %ds" % (org.pk, num_synced, time.time() - start)
            fetch_start = time.time()
            print "=" * 40

        # update the time for this poll from which we fetch next time
        cache.set(PollResult.POLL_RESULTS_LAST_PULL_CACHE_KEY % (org.pk, poll.pk),
                  datetime_to_json_date(now.replace(tzinfo=pytz.utc)))

        # from django.db import connection as db_connection, reset_queries
        # print "=" * 60
        # for query in db_connection.queries:
        #     print "%s - %s" % (query['time'], query['sql'][:1000])
        # print "-" * 60
        # print "took: %f" % (time.time() - start)
        # print "=" * 60
        # # reset_queries()

        print "Finished pulling results org #%d runs in %ds, created %d, updated %d, ignored %d" % (org.pk, time.time() - start, num_created, num_updated, num_ignored)
        return num_created, num_updated, num_ignored