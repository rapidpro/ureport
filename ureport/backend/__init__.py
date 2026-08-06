# -*- coding: utf-8 -*-

from abc import ABCMeta, abstractmethod


class BaseBackend(object):
    __metaclass__ = ABCMeta

    def __init__(self, backend):
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
    def pull_contacts(
        self, org, modified_after, modified_before, progress_callback=None, resume_cursor=None, time_limit=None
    ):
        """
        Pulls contacts modified in the given time window
        :param org: the org
        :param datetime modified_after: pull contacts modified after this
        :param datetime modified_before: pull contacts modified before this
        :param progress_callback: callable that will be called from time to time with number of contacts pulled
        :param resume_cursor: optional API cursor from a previous incomplete pull of the same time window
        :param time_limit: optional number of seconds after which the pull pauses and returns a resume cursor
        :return: tuple of a dict of counts of created, updated, deleted and ignored contacts, and a resume cursor
                 if the pull didn't complete
        """
        pass
