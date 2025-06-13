# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

from django.core.cache import cache
from django.db import migrations

logger = logging.getLogger(__name__)

# language=SQL
CLEAR_CONTACT_SQL = """
TRUNCATE contacts_contact;

"""


def remove_cache_and_lock_keys(apps, schema_editor):
    try:
        # clear valkey cache and locks to allow the next task to fetch all the contacts
        cache.delete_pattern("last:fetch_contacts:*")
        cache.delete_pattern("fetch_contacts")
        cache.delete_pattern("fetch_contacts*")

        logger.info("Removed all cache and lock keys for fetch contacts")

    except AttributeError as e:
        logger.info(e)


class Migration(migrations.Migration):
    dependencies = [("contacts", "0005_auto_20150921_0855")]

    operations = [migrations.RunSQL(CLEAR_CONTACT_SQL), migrations.RunPython(remove_cache_and_lock_keys)]
