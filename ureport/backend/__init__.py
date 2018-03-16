from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod
from django.conf import settings
from pydoc import locate


def get_backend(backend_slug='rapidpro'):
    """
    Gets the active backend for this casepro instance
    """
    backends_config_dict = getattr(settings, 'DATA_API_BACKENDS_CONFIG', {})
    backend_config = backends_config_dict.get(backend_slug, None)

    if backend_config:
        backend = locate(backend_config['class_type'])(backend=backend_slug)
    else:
        backend = locate(settings.SITE_BACKEND)()

    return backend

class BaseBackend(object):
    __metaclass__ = ABCMeta

    def __init__(self, backend='rapidpro'):
        self.backend = backend

    @abstractmethod
    def pull_fields(self, org):
        """
        Pulls all contact fields
        :param org: the org
        :return: tuple of the number of fields created, updated, deleted and ignored
        """
        pass

    @abstractmethod
    def pull_boundaries(self, org):
        """
        Pulls all location boundaries data
        :param org: the org
        :return: tuple of the number of boundaries created, updated, deleted and ignored
        """
        pass

    @abstractmethod
    def pull_contacts(self, org, modified_after, modified_before, progress_callback=None):
        """
        Pulls contacts modified in the given time window
        :param org: the org
        :param datetime modified_after: pull contacts modified after this
        :param datetime modified_before: pull contacts modified before this
        :param progress_callback: callable that will be called from time to time with number of contacts pulled
        :return: tuple of the number of contacts created, updated, deleted and ignored
        """
        pass
