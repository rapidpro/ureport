from dash.orgs.models import Org
from django.core.cache import cache
from django.db import models, DataError
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

# Create your models here.
import pytz
from ureport.locations.models import Boundary
from ureport.utils import json_date_to_datetime, datetime_to_json_date


class ContactField(models.Model):
    """
    Corresponds to a RapidPro contact field
    """

    CONTACT_FIELDS_CACHE_TIMEOUT = 60 * 60 * 24 * 15
    CONTACT_FIELDS_CACHE_KEY = 'org:%d:contact_fields'

    org = models.ForeignKey(Org, verbose_name=_("Org"), related_name="contactfields")

    label = models.CharField(verbose_name=_("Label"), max_length=36)

    key = models.CharField(verbose_name=_("Key"), max_length=36)

    value_type = models.CharField(max_length=1, verbose_name="Field Type")

    @classmethod
    def update_or_create_from_temba(cls, org, temba_contact_field):
        kwargs = cls.kwargs_from_temba(org, temba_contact_field)

        existing = cls.objects.filter(org=org, key=kwargs['key'])
        if existing:
            existing.update(**kwargs)
            return existing.first()
        else:
            return cls.objects.create(**kwargs)

    @classmethod
    def kwargs_from_temba(cls, org, temba_contact_field):
        return dict(org=org, label=temba_contact_field.label, key=temba_contact_field.key,
                    value_type=temba_contact_field.value_type)

    @classmethod
    def fetch_contact_fields(cls, org):

        temba_client = org.get_temba_client()
        api_contact_fields = temba_client.get_fields()

        seen_keys = []

        for contact_field in api_contact_fields:
            cls.update_or_create_from_temba(org, contact_field)
            seen_keys.append(contact_field.key)

        # remove any contact field that's no longer return on the API
        cls.objects.filter(org=org).exclude(key__in=seen_keys).delete()

        key = cls.CONTACT_FIELDS_CACHE_KEY % org.id
        cache.set(key, seen_keys, cls.CONTACT_FIELDS_CACHE_TIMEOUT)

        return seen_keys

    @classmethod
    def get_contact_fields(cls, org):
        key = cls.CONTACT_FIELDS_CACHE_KEY % org.id

        fields_keys = cache.get(key, None)
        if fields_keys:
            return fields_keys

        fields_keys = cls.fetch_contact_fields(org)
        return fields_keys


class Contact(models.Model):
    """
    Corresponds to a RapidPro contact
    """

    CONTACT_LAST_FETCHED_CACHE_KEY = 'last:fetch_contacts:%d'
    CONTACT_LAST_FETCHED_CACHE_TIMEOUT = 60 * 60 * 24 * 30

    MALE = 'M'
    FEMALE = 'F'
    GENDER_CHOICES = ((MALE, _("Male")), (FEMALE, _("Female")))

    uuid = models.CharField(max_length=36, unique=True)

    org = models.ForeignKey(Org, verbose_name=_("Organization"), related_name="contacts")

    gender = models.CharField(max_length=1, verbose_name=_("Gender"), choices=GENDER_CHOICES, null=True, blank=True,
                              help_text=_("Gender of the contact"))

    born = models.IntegerField(verbose_name=_("Born Field"), null=True, blank=True)

    occupation = models.CharField(max_length=255, verbose_name=_("Occupation Field"), null=True, blank=True)

    registered_on = models.DateTimeField(verbose_name=_("Registration Date"), null=True, blank=True)

    state = models.CharField(max_length=255, verbose_name=_("State Field"), null=True)

    district = models.CharField(max_length=255, verbose_name=_("District Field"), null=True)

    @classmethod
    def find_contact_field_key(cls, org, label):
        contact_field = ContactField.objects.filter(org=org, label__iexact=label).first()
        if contact_field:
            return contact_field.key

    @classmethod
    def kwargs_from_temba(cls, org, temba_contact):
        from ureport.utils import json_date_to_datetime

        state = ''
        district = ''

        state_field = org.get_config('state_label')
        if state_field:
            if org.get_config('is_global'):
                state_name = temba_contact.fields.get(cls.find_contact_field_key(org, state_field), None)
                if state_name:
                    state = state_name

            else:
                state_name = temba_contact.fields.get(cls.find_contact_field_key(org, state_field), None)
                state_boundary = Boundary.objects.filter(org=org, level=1, name__iexact=state_name).first()
                if state_boundary:
                    state = state_boundary.osm_id

                district_field = org.get_config('district_label')
                if district_field:
                    district_name = temba_contact.fields.get(cls.find_contact_field_key(org, district_field), None)
                    district_boundary = Boundary.objects.filter(org=org, level=2, name__iexact=district_name,
                                                            parent=state_boundary).first()
                    if district_boundary:
                        district = district_boundary.osm_id

        registered_on = None
        registration_field = org.get_config('registration_label')
        if registration_field:
            registered_on = temba_contact.fields.get(cls.find_contact_field_key(org, registration_field), None)
            if registered_on:
                registered_on = json_date_to_datetime(registered_on)

        occupation = ''
        occupation_field = org.get_config('occupation_label')
        if occupation_field:
            occupation = temba_contact.fields.get(cls.find_contact_field_key(org, occupation_field), '')
            if not occupation:
                occupation = ''

        born = 0
        born_field = org.get_config('born_label')
        if born_field:
            try:
                born = int(temba_contact.fields.get(cls.find_contact_field_key(org, born_field), 0))
            except ValueError:
                pass
            except TypeError:
                pass

        gender = ''
        gender_field = org.get_config('gender_label')
        female_label = org.get_config('female_label')
        male_label = org.get_config('male_label')

        if gender_field:
            gender = temba_contact.fields.get(cls.find_contact_field_key(org, gender_field), '')

            if gender and gender.lower() == female_label.lower():
                gender = cls.FEMALE
            elif gender and gender.lower() == male_label.lower():
                gender = cls.MALE
            else:
                gender = ''

        return dict(org=org, uuid=temba_contact.uuid, gender=gender, born=born, occupation=occupation,
                    registered_on=registered_on, district=district, state=state)

    @classmethod
    def update_or_create_from_temba(cls, org, temba_contact):
        from raven.contrib.django.raven_compat.models import client

        kwargs = cls.kwargs_from_temba(org, temba_contact)

        try:
            existing = cls.objects.filter(org=org, uuid=kwargs['uuid'])
            if existing:
                existing.update(**kwargs)
                return existing.first()
            else:
                return cls.objects.create(**kwargs)
        except DataError as e:  # pragma: no cover
            client.captureException()
            import traceback
            traceback.print_exc()

    @classmethod
    def fetch_contacts(cls, org, after=None):

        print "START== Fetching contacts for %s" % org.name

        reporter_group = org.get_config('reporter_group')

        temba_client = org.get_temba_client()
        api_groups = temba_client.get_groups(name=reporter_group)

        if not api_groups:
            return

        seen_uuids = []

        group_uuid = None

        for grp in api_groups:
            if grp.name.lower() == reporter_group.lower():
                group_uuid = grp.uuid
                break

        now = timezone.now().replace(tzinfo=pytz.utc)
        before = now

        if not after:
            # consider the after year 2013
            after = json_date_to_datetime("2013-01-01T00:00:00.000")

        while before > after:
            pager = temba_client.pager()
            api_contacts = temba_client.get_contacts(before=before, after=after, pager=pager)

            last_contact_index = len(api_contacts) - 1

            for i, contact in enumerate(api_contacts):
                if i == last_contact_index:
                    before = contact.modified_on

                if group_uuid in contact.groups:
                    cls.update_or_create_from_temba(org, contact)
                    seen_uuids.append(contact.uuid)

            if not pager.has_more():
                cache.set(cls.CONTACT_LAST_FETCHED_CACHE_KEY % org.pk,
                          datetime_to_json_date(now.replace(tzinfo=pytz.utc)),
                          cls.CONTACT_LAST_FETCHED_CACHE_TIMEOUT)
                break

        return seen_uuids


class ReportersCounter(models.Model):

    org = models.ForeignKey(Org, related_name='reporters_counters')

    type = models.CharField(max_length=255)

    count = models.IntegerField(default=0, help_text=_("Number of items with this counter"))

    @classmethod
    def get_counts(cls, org, types=None):
        """
        Gets all reporters counts by counter type for the given org
        """
        counters = cls.objects.filter(org=org)
        if types:
            counters = counters.filter(counter_type__in=types)
        counter_counts = counters.values('type').order_by('type').annotate(count_sum=Sum('count'))

        return {c['type']: c['count_sum'] for c in counter_counts}

    class Meta:
        index_together = ('org', 'type')