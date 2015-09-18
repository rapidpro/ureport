import logging
import time
from datetime import datetime
from django.core.cache import cache
from dash.orgs.models import Org
from django_redis import get_redis_connection
from djcelery.app import app
import pytz
from ureport.contacts.models import ContactField, Contact
from ureport.locations.models import Boundary
from ureport.utils import datetime_to_json_date, json_date_to_datetime

logger = logging.getLogger(__name__)


@app.task(name='contacts.fetch_contacts_task')
def fetch_contacts_task(org_id=None, fetch_all=False):

    r = get_redis_connection()

    key = 'fetch_contacts'
    lock_timeout = 3600

    if org_id:
        key = 'fetch_contacts:%d' % org_id
        lock_timeout = 300

    if not r.get(key):
        with r.lock(key, timeout=lock_timeout):
            active_orgs = Org.objects.filter(is_active=True)
            if org_id:
                active_orgs = Org.objects.filter(pk=org_id)

            for org in active_orgs:

                start = time.time()

                last_fetched_key = Contact.CONTACT_LAST_FETCHED_CACHE_KEY % org.id

                after = cache.get(last_fetched_key, None)
                if after:
                    after = json_date_to_datetime(after)

                if fetch_all:
                    after = None

                try:
                    Boundary.get_boundaries(org)
                    ContactField.get_contact_fields(org)
                    Contact.fetch_contacts(org, after=after)

                    cache.set(last_fetched_key, datetime_to_json_date(datetime.now().replace(tzinfo=pytz.utc)),
                              Contact.CONTACT_LAST_FETCHED_CACHE_TIMEOUT)

                    print "Task: fetch_contacts for %s took %ss" % (org.name, time.time() - start)

                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    logger.exception("Error fetching contacts: %s" % str(e))


