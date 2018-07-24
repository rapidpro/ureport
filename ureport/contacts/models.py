# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals


import time
import logging
from dash.orgs.models import Org, OrgBackend
from django.db import models, connection
from django.db.models import Sum, Count
from django.utils.translation import ugettext_lazy as _

from django_redis import get_redis_connection


CONTACT_LOCK_KEY = 'lock:contact:%d:%s'
CONTACT_FIELD_LOCK_KEY = 'lock:contact-field:%d:%s'


logger = logging.getLogger(__name__)


class ContactField(models.Model):
    """
    Corresponds to a RapidPro contact field
    """

    TYPE_TEXT = 'T'
    TYPE_DECIMAL = 'N'
    TYPE_DATETIME = 'D'
    TYPE_STATE = 'S'
    TYPE_DISTRICT = 'I'
    TYPE_WARD = 'W'

    TEMBA_TYPES = {'text': TYPE_TEXT,
                   'numeric': TYPE_DECIMAL,
                   'datetime': TYPE_DATETIME,
                   'state': TYPE_STATE,
                   'district': TYPE_DISTRICT,
                   'ward': TYPE_WARD}

    CONTACT_FIELDS_CACHE_TIMEOUT = 60 * 60 * 24 * 15
    CONTACT_FIELDS_CACHE_KEY = 'org:%d:contact_fields'

    is_active = models.BooleanField(default=True)

    backend = models.ForeignKey(OrgBackend, null=True)

    org = models.ForeignKey(Org, verbose_name=_("Org"), related_name="contactfields")

    label = models.CharField(verbose_name=_("Label"), max_length=36)

    key = models.CharField(verbose_name=_("Key"), max_length=36)

    value_type = models.CharField(max_length=1, verbose_name="Field Type")

    @classmethod
    def lock(cls, org, key):
        return get_redis_connection().lock(CONTACT_FIELD_LOCK_KEY % (org.pk, key), timeout=60)

    def release(self):
        self.delete()


class Contact(models.Model):
    """
    Corresponds to a RapidPro contact
    """

    CONTACT_LAST_FETCHED_CACHE_KEY = 'last:fetch_contacts:%d:backend:%s'
    CONTACT_LAST_FETCHED_CACHE_TIMEOUT = 60 * 60 * 24 * 30

    MALE = 'M'
    FEMALE = 'F'
    GENDER_CHOICES = ((MALE, _("Male")), (FEMALE, _("Female")))

    is_active = models.BooleanField(default=True)

    backend = models.ForeignKey(OrgBackend, null=True)

    uuid = models.CharField(max_length=36, unique=True)

    org = models.ForeignKey(Org, verbose_name=_("Organization"), related_name="contacts")

    gender = models.CharField(max_length=1, verbose_name=_("Gender"), choices=GENDER_CHOICES, null=True, blank=True,
                              help_text=_("Gender of the contact"))

    born = models.IntegerField(verbose_name=_("Born Field"), null=True, blank=True)

    occupation = models.CharField(max_length=255, verbose_name=_("Occupation Field"), null=True, blank=True)

    registered_on = models.DateTimeField(verbose_name=_("Registration Date"), null=True, blank=True)

    state = models.CharField(max_length=255, verbose_name=_("State Field"), null=True)

    district = models.CharField(max_length=255, verbose_name=_("District Field"), null=True)

    ward = models.CharField(max_length=255, verbose_name=_("Ward Field"), null=True)

    @classmethod
    def get_or_create(cls, org, uuid):

        existing = cls.objects.filter(org=org, uuid=uuid)

        if existing:
            return existing.first()
        return cls.objects.create(org=org, uuid=uuid)

    @classmethod
    def lock(cls, org, uuid):
        return get_redis_connection().lock(CONTACT_LOCK_KEY % (org.pk, uuid), timeout=60)

    class Meta:
        unique_together = ('org', 'uuid')


class ReportersCounter(models.Model):

    COUNTS_SQUASH_LOCK = 'org-reporters-counts-squash-lock'
    LAST_SQUASHED_ID_KEY = 'org-reporters-last-squashed-id'

    org = models.ForeignKey(Org, related_name='reporters_counters')

    type = models.CharField(max_length=255)

    count = models.IntegerField(default=0, help_text=_("Number of items with this counter"))

    @classmethod
    def squash_counts(cls):
        # get the id of the last count we squashed
        r = get_redis_connection()
        key = ReportersCounter.COUNTS_SQUASH_LOCK
        if r.get(key):
            logger.info("Squash reporters counts already running.")
        else:
            with r.lock(key):

                last_squash = r.get(ReportersCounter.LAST_SQUASHED_ID_KEY)
                if not last_squash:
                    last_squash = 0

                last_squash = int(last_squash)

                start = time.time()
                squash_count = 0

                if last_squash < 1:
                    counters = ReportersCounter.objects.values('org_id', 'type').annotate(Count('id')).filter(id__count__gt=1).order_by('org_id', 'type')

                else:
                    counters = ReportersCounter.objects.filter(id__gt=last_squash).values('org_id', 'type').order_by('org_id', 'type').distinct('org_id', 'type')

                total_counters = len(counters)

                # get all the new added counters
                for counter in counters:

                    # perform our atomic squash in SQL by calling our squash method
                    with connection.cursor() as c:
                        c.execute("SELECT ureport_squash_reporterscounters(%s, %s);", (counter['org_id'], counter['type']))

                    squash_count += 1

                    if squash_count % 100 == 0:
                        logger.info("Squashing progress ... %0.2f/100 in in %0.3fs" % (squash_count * 100 / total_counters, time.time() - start))

                # insert our new top squashed id
                max_id = ReportersCounter.objects.all().order_by('-id').first()
                if max_id:
                    r.set(ReportersCounter.LAST_SQUASHED_ID_KEY, max_id.id)

                logger.info("Squashed poll results counts for %d types in %0.3fs" % (squash_count, time.time() - start))

    @classmethod
    def get_counts(cls, org, types=None):
        """
        Gets all reporters counts by counter type for the given org
        """
        counters = cls.objects.filter(org=org)
        if types:
            counters = counters.filter(type__in=types)
        counter_counts = counters.values('type').order_by('type').annotate(count_sum=Sum('count'))

        return {c['type']: c['count_sum'] for c in counter_counts}

    class Meta:
        index_together = ('org', 'type')
