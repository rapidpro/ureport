from __future__ import unicode_literals

import json
from dash.orgs.models import Org
from django.db import models
from django.utils.translation import ugettext_lazy as _
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
    def import_contacts(cls, org):

        org_config = json.loads(org.config)

        reporter_group = org_config.get('reporter_group', '').lower()

        gender_label = org_config.get('gender_label', '').lower()
        born_label = org_config.get('born_label', '').lower()
        registration_label = org_config.get('registration_label', '').lower()
        occupation_label = org_config.get('occupation_label', '').lower()
        state_label = org_config.get('state_label', '').lower()
        district_label = org_config.get('district_label', '').lower()
        female_label = org_config.get('female_label', '').lower()
        male_label = org_config.get('male_label', '').lower()

        temba_client = org.get_temba_client()
        api_groups = temba_client.get_groups(name=reporter_group)

        if not api_groups:
            return

        api_contacts = temba_client.get_contacts(groups=[api_groups[0]])
        for contact in api_contacts:
            existing = cls.objects.filter(org=org, uuid=contact.uuid)
            fields = contact.fields

            gender = fields.get(gender_label, None)
            if gender.lower() == female_label:
                gender = cls.FEMALE
            elif gender.lower() == male_label:
                gender = cls.MALE
            else:
                gender = None

            born = (fields.get(born_label, 0))

            try:
                born = int(born)
            except ValueError:
                born = 0

            registered_on = fields.get(registration_label, None)
            if registered_on:
                registered_on = json_date_to_datetime(registered_on)

            occupation = fields.get(occupation_label, None)
            state = fields.get(state_label.lower(), None)
            district = fields.get(district_label, None)

            kwargs = dict(uuid=contact.uuid, org=org, gender=gender, registered_on=registered_on, born=born,
                          occupation=occupation, state=state, district=district)

            if existing:
                existing.update(**kwargs)
            else:
                cls.objects.create(**kwargs)
