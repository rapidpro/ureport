from __future__ import unicode_literals

import json
from dash.orgs.models import Org
from django.db import models
from django.db.models import Sum
from django.utils.translation import ugettext_lazy as _
import regex
from ureport.locations.models import Boundary
from ureport.utils import json_date_to_datetime


class Contact(models.Model):
    """
    Corresponds to a RapidPro contact
    """
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
    def make_key(cls, label):
        key = regex.sub(r'([^a-z0-9]+)', ' ', label.lower(), regex.V0)
        return regex.sub(r'([^a-z0-9]+)', '_', key.strip(), regex.V0)

    @classmethod
    def kwargs_from_temba(cls, org, temba_contact):

        state = ''
        district = ''

        state_field = org.get_config('state_label')
        if state_field:
            state_name = temba_contact.fields.get(cls.make_key(state_field), None)
            state_boundary = Boundary.objects.filter(org=org, level=1, name__iexact=state_name).first()
            if state_boundary:
                state = state_boundary.osm_id

            district_field = org.get_config('district_label')
            if district_field:
                district_name = temba_contact.fields.get(cls.make_key(district_field), None)
                district_boundary = Boundary.objects.filter(org=org, level=2, name__iexact=district_name,
                                                            parent=state_boundary).first()
                if district_boundary:
                    district = district_boundary.osm_id

        registered_on = None
        registration_field = org.get_config('registration_label')
        if registration_field:
            registered_on = temba_contact.fields.get(cls.make_key(registration_field), None)
            if registered_on:
                registered_on = json_date_to_datetime(registered_on)

        occupation = ''
        occupation_field = org.get_config('occupation_label')
        if occupation_field:
            occupation = temba_contact.fields.get(cls.make_key(occupation_field), '')
            if not occupation:
                occupation = ''

        born = 0
        born_field = org.get_config('born_label')
        if born_field:
            try:
                born = int(temba_contact.fields.get(cls.make_key(born_field), 0))
            except ValueError:
                pass
            except TypeError:
                pass

        gender = ''
        gender_field = org.get_config('gender_label')
        female_label = org.get_config('female_label')
        male_label = org.get_config('male_label')

        if gender_field:
            gender = temba_contact.fields.get(cls.make_key(gender_field), '')

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
        kwargs = cls.kwargs_from_temba(org, temba_contact)

        existing = cls.objects.filter(org=org, uuid=kwargs['uuid'])
        if existing:
            existing.update(**kwargs)
            return existing.first()
        else:
            return cls.objects.create(**kwargs)

    @classmethod
    def fetch_contacts(cls, org):
        reporter_group = org.get_config('reporter_group')

        temba_client = org.get_temba_client()
        api_groups = temba_client.get_groups(name=reporter_group)

        if not api_groups:
            return

        seen_uuids = []

        api_contacts = temba_client.get_contacts(groups=[api_groups[0]])
        for contact in api_contacts:
            cls.update_or_create_from_temba(org, contact)
            seen_uuids.append(contact.uuid)

        # remove any contact that's no longer a ureporter
        cls.objects.filter(org=org).exclude(uuid__in=seen_uuids).delete()


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
