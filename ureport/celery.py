# -*- coding: utf-8 -*-

import os

from celery import Celery
from celery.signals import worker_ready, worker_shutting_down

from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ureport.settings")

app = Celery("ureport")


# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@worker_shutting_down.connect
def flag_sync_shutdown(**kwargs):
    """
    The shutdown signal only reaches the worker main process while sync tasks run in pool
    child processes, so flag the shutdown in the shared cache where sync loops can see it
    and pause at their next checkpoint
    """
    from ureport.sync_state import signal_sync_shutdown

    signal_sync_shutdown()


@worker_ready.connect
def reset_sync_shutdown(**kwargs):
    from ureport.sync_state import clear_sync_shutdown

    clear_sync_shutdown()
