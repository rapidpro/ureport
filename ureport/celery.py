# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import *

import os
import celery

from raven import Client
from raven.contrib.celery import register_signal

from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ureport.settings')


class Celery(celery.Celery):
    def on_configure(self):
        import raven
        from raven.contrib.celery import register_signal, register_logger_signal

        client = raven.Client()

        # register a custom filter to filter out duplicate logs
        register_logger_signal(client)

        # hook into the Celery error handler
        register_signal(client)


app = Celery('ureport')


# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

if hasattr(settings, 'RAVEN_CONFIG'):
    # Celery signal registration
    client = Client(dsn=settings.RAVEN_CONFIG['dsn'])
    register_signal(client)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))