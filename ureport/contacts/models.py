# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import time
from collections import defaultdict

from django_valkey import get_valkey_connection

from django.db import connection, models
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from dash.orgs.models import Org, OrgBackend

CONTACT_LOCK_KEY = "lock:contact:%d:%s"
CONTACT_FIELD_LOCK_KEY = "lock:contact-field:%d:%s"


logger = logging.getLogger(__name__)


class ContactField(models.Model):
    """
    Corresponds to a RapidPro contact field
    """

    TYPE_TEXT = "T"
    TYPE_DECIMAL = "N"
    TYPE_DATETIME = "D"
    TYPE_STATE = "S"
    TYPE_DISTRICT = "I"
    TYPE_WARD = "W"

    TEMBA_TYPES = {
        "text": TYPE_TEXT,
        "numeric": TYPE_DECIMAL,
        "datetime": TYPE_DATETIME,
        "state": TYPE_STATE,
        "district": TYPE_DISTRICT,
        "ward": TYPE_WARD,
    }

    CONTACT_FIELDS_CACHE_TIMEOUT = 60 * 60 * 24 * 15
    CONTACT_FIELDS_CACHE_KEY = "org:%d:contact_fields"

    is_active = models.BooleanField(default=True)

    backend = models.ForeignKey(OrgBackend, on_delete=models.PROTECT, null=True)

    org = models.ForeignKey(Org, on_delete=models.PROTECT, verbose_name=_("Org"), related_name="contactfields")

    label = models.CharField(verbose_name=_("Label"), max_length=36)

    key = models.CharField(verbose_name=_("Key"), max_length=36)

    value_type = models.CharField(max_length=1, verbose_name="Field Type")

    @classmethod
    def lock(cls, org, key):
        return get_valkey_connection().lock(CONTACT_FIELD_LOCK_KEY % (org.pk, key), timeout=60)

    def release(self):
        self.delete()


class Contact(models.Model):
    """
    Corresponds to a RapidPro contact
    """

    CONTACT_LAST_FETCHED_CACHE_KEY = "last:fetch_contacts:%d:backend:%s"
    CONTACT_LAST_FETCHED_CACHE_TIMEOUT = 60 * 60 * 24 * 30

    MALE = "M"
    FEMALE = "F"
    OTHER = "O"
    GENDER_CHOICES = ((MALE, _("Male")), (FEMALE, _("Female")), (OTHER, _("Other")))

    is_active = models.BooleanField(default=True)

    backend = models.ForeignKey(OrgBackend, on_delete=models.PROTECT, null=True)

    uuid = models.CharField(max_length=36)

    org = models.ForeignKey(Org, on_delete=models.PROTECT, verbose_name=_("Organization"), related_name="contacts")

    gender = models.CharField(
        max_length=1,
        verbose_name=_("Gender"),
        choices=GENDER_CHOICES,
        null=True,
        blank=True,
        help_text=_("Gender of the contact"),
    )

    born = models.IntegerField(verbose_name=_("Born Field"), null=True, blank=True)

    occupation = models.CharField(max_length=255, verbose_name=_("Occupation Field"), null=True, blank=True)

    registered_on = models.DateTimeField(verbose_name=_("Registration Date"), null=True, blank=True)

    state = models.CharField(max_length=255, verbose_name=_("State Field"), null=True)

    district = models.CharField(max_length=255, verbose_name=_("District Field"), null=True)

    ward = models.CharField(max_length=255, verbose_name=_("Ward Field"), null=True)

    scheme = models.CharField(max_length=16, null=True)

    @classmethod
    def get_or_create(cls, org, uuid):
        existing = cls.objects.filter(org=org, uuid=uuid)

        if existing:
            return existing.first()
        return cls.objects.create(org=org, uuid=uuid)

    @classmethod
    def lock(cls, org, uuid):
        return get_valkey_connection().lock(CONTACT_LOCK_KEY % (org.pk, uuid), timeout=60)

    @classmethod
    def recalculate_reporters_stats(cls, org):
        ReportersCounter.objects.filter(org_id=org.id).delete()

        all_contacts = Contact.objects.filter(org=org).order_by("id").iterator(chunk_size=1000)
        start = time.time()

        all_contacts_count = 0

        counters_dict = defaultdict(int)

        for contact in all_contacts:
            all_contacts_count += 1
            gen_counters = contact.generate_counters()
            for dict_key in gen_counters.keys():
                counters_dict[(org.id, dict_key)] += gen_counters[dict_key]

        counters_to_insert = []
        for counter_tuple in counters_dict.keys():
            org_id, counter_type = counter_tuple
            count = counters_dict[counter_tuple]
            counters_to_insert.append(ReportersCounter(org_id=org_id, type=counter_type, count=count))

        ReportersCounter.objects.bulk_create(counters_to_insert, batch_size=1000)

        logger.info(
            "Finished rebuilding contacts reporters counters (aggregated statistics for contacts) for org #%d in %ds, inserted %d counter objects for %s contacts"
            % (org.id, time.time() - start, len(counters_to_insert), all_contacts_count)
        )

        return counters_dict

    def generate_counters(self):
        generated_counters = dict()
        if not self.org_id or not self.is_active:
            return generated_counters

        gender = ""
        born = ""
        occupation = ""
        registered_on = ""

        state = ""
        district = ""
        ward = ""

        scheme = ""

        if self.gender:
            gender = self.gender.lower()

        if self.state:
            state = self.state.upper()

        if self.district:
            district = self.district.upper()

        if self.ward:
            ward = self.ward.upper()

        if self.scheme:
            scheme = self.scheme.lower()

        if self.born:
            born = self.born

        if self.occupation:
            occupation = self.occupation.lower()

        if self.registered_on:
            registered_on = self.registered_on.date()

        generated_counters["total-reporters"] = 1
        if gender:
            generated_counters[f"gender:{gender}"] = 1

        if born:
            generated_counters[f"born:{born}"] = 1

        if occupation:
            generated_counters[f"occupation:{occupation}"] = 1

        if registered_on:
            generated_counters[f"registered_on:{str(registered_on)}"] = 1
            if gender:
                generated_counters[f"registered_gender:{str(registered_on)}:{gender}"] = 1
            if born:
                generated_counters[f"registered_born:{str(registered_on)}:{born}"] = 1
            if state:
                generated_counters[f"registered_state:{str(registered_on)}:{state}"] = 1
            if scheme:
                generated_counters[f"registered_scheme:{str(registered_on)}:{scheme}"] = 1

        if state:
            generated_counters[f"state:{state}"] = 1
        if district:
            generated_counters[f"district:{district}"] = 1
        if ward:
            generated_counters[f"ward:{ward}"] = 1

        if scheme:
            generated_counters[f"scheme:{scheme}"] = 1

        return generated_counters

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org", "uuid"], name="contacts_contact_org_id_563dcefdcba190b9_uniq")
        ]


class ReportersCounter(models.Model):
    COUNTS_SQUASH_LOCK = "org-reporters-counts-squash-lock"
    LAST_SQUASHED_ID_KEY = "org-reporters-last-squashed-id"

    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="reporters_counters")

    type = models.CharField(max_length=255)

    count = models.IntegerField(default=0, help_text=_("Number of items with this counter"))

    @classmethod
    def squash_counts(cls):
        # get the id of the last count we squashed
        r = get_valkey_connection()
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
                    counters = (
                        ReportersCounter.objects.values("org_id", "type")
                        .annotate(Count("id"))
                        .filter(id__count__gt=1)
                        .order_by("org_id", "type")
                    )

                else:
                    counters = (
                        ReportersCounter.objects.filter(id__gt=last_squash)
                        .values("org_id", "type")
                        .order_by("org_id", "type")
                        .distinct("org_id", "type")
                    )

                total_counters = len(counters)

                # get all the new added counters
                for counter in counters:
                    # perform our atomic squash in SQL by calling our squash method
                    with connection.cursor() as c:
                        c.execute(
                            "SELECT ureport_squash_reporterscounters(%s, %s);", (counter["org_id"], counter["type"])
                        )

                    squash_count += 1

                    if squash_count % 100 == 0:
                        logger.info(
                            "Squashing progress ... %0.2f/100 in in %0.3fs"
                            % (squash_count * 100 / total_counters, time.time() - start)
                        )

                # insert our new top squashed id
                max_id = ReportersCounter.objects.all().order_by("-id").first()
                if max_id:
                    r.set(ReportersCounter.LAST_SQUASHED_ID_KEY, max_id.id)

                logger.info(
                    "Squashed poll results counts for %d types in %0.3fs" % (squash_count, time.time() - start)
                )

    @classmethod
    def get_counts(cls, org, types=None):
        """
        Gets all reporters counts by counter type for the given org
        """
        counters = cls.objects.filter(org=org)
        if types:
            counters = counters.filter(type__in=types)

        counter_counts = counters.iterator(chunk_size=1000)

        counts = defaultdict(int)
        for c in counter_counts:
            counts[c.type] += c.count

        return counts

    class Meta:
        indexes = [
            models.Index(name="contacts_rptrscntr_org_id_idx", fields=["org", "type"]),
            models.Index(name="contacts_rptrscntr_org_typ_cnt", fields=["org", "type", "count"]),
        ]
