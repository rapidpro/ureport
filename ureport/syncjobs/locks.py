import logging
from contextlib import contextmanager

from django_valkey import get_valkey_connection
from valkey.exceptions import LockError

logger = logging.getLogger(__name__)


@contextmanager
def chunk_lock(key, timeout):
    """
    Takes a lock for the duration of one chunk, yielding whether it was taken. Never blocks -
    a chunk that can't have the lock backs off and comes back rather than tying up a worker
    waiting - and the timeout must comfortably outlive the chunk, as the work it guards
    carries on regardless once it lapses.
    """
    lock = get_valkey_connection().lock(key, timeout=timeout)
    acquired = lock.acquire(blocking=False)

    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except LockError:
                # the chunk outlived the lock's timeout - don't let that fail an otherwise
                # successful chunk or mask an in-flight exception
                logger.warning("Unable to release lock %s as it is no longer owned", key)
