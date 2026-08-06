# -*- coding: utf-8 -*-

import logging
import socket

from django.core.cache import cache

logger = logging.getLogger(__name__)

# the flag is keyed by machine hostname because the worker main process receives the shutdown
# signal while sync loops run in forked pool children - the cache is their shared channel
SYNC_SHUTDOWN_CACHE_KEY = "sync_worker_shutdown:%s"

# generously outlives any shutdown grace period while still self-clearing if the worker is
# replaced by one with the same hostname that missed the startup cleanup
SYNC_SHUTDOWN_CACHE_TIMEOUT = 60 * 10


def signal_sync_shutdown():
    """
    Marks this host's worker as shutting down so sync loops pause at their next checkpoint
    """
    cache.set(SYNC_SHUTDOWN_CACHE_KEY % socket.gethostname(), True, SYNC_SHUTDOWN_CACHE_TIMEOUT)
    logger.info("Flagged sync shutdown for host %s" % socket.gethostname())


def clear_sync_shutdown():
    """
    Clears the shutdown flag, called when a worker starts on this host
    """
    cache.delete(SYNC_SHUTDOWN_CACHE_KEY % socket.gethostname())


def is_sync_shutting_down():
    """
    Whether the worker on this host is shutting down and sync loops should pause
    """
    return bool(cache.get(SYNC_SHUTDOWN_CACHE_KEY % socket.gethostname()))
