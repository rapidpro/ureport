# -*- coding: utf-8 -*-

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field

from dash.utils.sync import SyncOutcome


@dataclass
class ChunkResult:
    """
    The outcome of one bounded chunk of a pull. Both counts and cursor are JSON
    serializable; the cursor is an opaque resume position that yields no missed data when
    passed to the next chunk call (duplicate work is acceptable - writes are upserts);
    done is True when the pull has no work left; rate_limited is True when the chunk
    stopped early because the API rate limit was exhausted and the caller should back off
    before the next chunk.
    """

    counts: dict = field(default_factory=dict)
    cursor: dict = field(default_factory=dict)
    done: bool = False
    rate_limited: bool = False


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

    # ------------------------------------------------------------------------------
    # Chunked pulls - bounded, resumable units of the pulls above. These defaults do
    # the entire pull as a single chunk; backends that support real pagination should
    # override them to do a bounded amount of work per call and return a cursor.
    # ------------------------------------------------------------------------------

    def pull_contacts_chunk(self, org, modified_after, modified_before, cursor, time_budget=None):
        """
        Pulls one bounded chunk of contacts modified in the given time window. The window
        must stay fixed for the life of a cursor: a resumed page cursor is only valid
        against the exact query it came from, so callers freeze (after, before) when a
        traversal starts and roll the window only after done.
        :param cursor: the resume position returned by the previous chunk, or {} to start
        :return: a ChunkResult whose counts dict has the created/updated/deleted/ignored keys
        """
        counts, _ = self.pull_contacts(org, modified_after, modified_before)
        return ChunkResult(counts=self._outcome_counts_dict(counts), cursor={}, done=True)

    def pull_results_chunk(self, poll, cursor, page_budget=None):
        """
        Pulls one bounded chunk of results for the given poll.
        :param cursor: the resume position returned by the previous chunk, or {} to start
        :return: a ChunkResult whose counts dict has the num_val_* / num_path_* / num_synced keys
        """
        counts = self.pull_results(poll, None, None)
        return ChunkResult(counts=self._results_counts_dict(counts), cursor=dict(cursor), done=True)

    def pull_results_from_archives_chunk(self, poll, cursor, archive_budget=None):
        """
        Pulls one bounded chunk of archived results for the given poll. Backends without
        archives complete immediately.
        :param cursor: the resume position returned by the previous chunk, or {} to start
        :return: a ChunkResult whose counts dict has the num_val_* / num_path_* / num_synced keys
        """
        return ChunkResult(counts=self._results_counts_dict(()), cursor=dict(cursor), done=True)

    @staticmethod
    def _results_counts_dict(counts_tuple):
        keys = (
            "num_val_created",
            "num_val_updated",
            "num_val_ignored",
            "num_path_created",
            "num_path_updated",
            "num_path_ignored",
            "num_synced",
        )
        counts = dict(zip(keys, counts_tuple))
        return {key: counts.get(key, 0) for key in keys}

    @staticmethod
    def _outcome_counts_dict(outcome_counts):
        return {
            "created": outcome_counts.get(SyncOutcome.created, 0),
            "updated": outcome_counts.get(SyncOutcome.updated, 0),
            "deleted": outcome_counts.get(SyncOutcome.deleted, 0),
            "ignored": outcome_counts.get(SyncOutcome.ignored, 0),
        }
