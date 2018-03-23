# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import *

import time
from dash.orgs.tasks import org_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@org_task('contact-pull', 60 * 60 * 3)
def pull_contacts(org, since, until):
    """
    Fetches updated contacts from RapidPro and updates local contacts accordingly
    """
    from ureport.contacts.models import ReportersCounter
    backend = org.get_backend()

    if not since:
        logger.warn("First time run for org #%d. Will sync all contacts" % org.pk)

    start = time.time()

    fields_created, fields_updated, fields_deleted, ignored = backend.pull_fields(org)

    logger.warn("Fetched contact fields for org #%d. "
                "Created %s, Updated %s, Deleted %d, Ignored %d" % (org.pk, fields_created, fields_updated,
                                                                    fields_deleted, ignored))
    logger.warn("Fetch fields for org #%d took %ss" % (org.pk, time.time() - start))

    start_boundaries = time.time()

    boundaries_created, boundaries_updated, boundaries_deleted, ignored = backend.pull_boundaries(org)

    logger.warn("Fetched boundaries for org #%d. "
                "Created %s, Updated %s, Deleted %d, Ignored %d" % (org.pk, boundaries_created, boundaries_updated,
                                                                    boundaries_deleted, ignored))

    logger.warn("Fetch boundaries for org #%d took %ss" % (org.pk, time.time() - start_boundaries))
    start_contacts = time.time()

    contacts_created, contacts_updated, contacts_deleted, ignored = backend.pull_contacts(org, since, until)

    logger.warn("Fetched contacts for org #%d. "
                "Created %s, Updated %s, Deleted %d, Ignored %d" % (org.pk, contacts_created, contacts_updated,
                                                                    contacts_deleted, ignored))

    logger.warn("Fetch contacts for org #%d took %ss" % (org.pk, time.time() - start_contacts))

    # Squash reporters counts
    ReportersCounter.squash_counts()

    return {
        'fields': {'created': fields_created, 'updated': fields_updated, 'deleted': fields_deleted},
        'boundaries': {'created': boundaries_created, 'updated': boundaries_updated, 'deleted': boundaries_deleted},
        'contacts': {'created': contacts_created, 'updated': contacts_updated, 'deleted': contacts_deleted}
    }
