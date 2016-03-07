from __future__ import unicode_literals

from dash.orgs.tasks import org_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@org_task('contact-pull')
def pull_contacts(org, since, until):
    """
    Fetches updated contacts from RapidPro and updates local contacts accordingly
    """
    from ureport.backend import get_backend
    backend = get_backend()

    if not since:
        logger.warn("First time run for org #%d. Will sync all contacts" % org.pk)

    fields_created, fields_updated, fields_deleted, ignored = backend.pull_fields(org)

    boundaries_created, boundaries_updated, boundaries_deleted, ignored = backend.pull_boundaries(org)

    contacts_created, contacts_updated, contacts_deleted, ignored = backend.pull_contacts(org, since, until)

    return {
        'fields': {'created': fields_created, 'updated': fields_updated, 'deleted': fields_deleted},
        'boundaries': {'created': boundaries_created, 'updated': boundaries_updated, 'deleted': boundaries_deleted},
        'contacts': {'created': contacts_created, 'updated': contacts_updated, 'deleted': contacts_deleted}
    }