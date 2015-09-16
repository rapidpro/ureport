from dash.orgs.models import Org
from django.core.cache import cache
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Create your models here.


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
