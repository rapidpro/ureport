# -*- coding: utf-8 -*-

import json
from datetime import timedelta

from django_valkey import get_valkey_connection
from mock import patch

from django.core.cache import cache
from django.utils import timezone

from dash.orgs.models import TaskState
from dash.utils.sync import SyncOutcome
from ureport.backend import ChunkResult
from ureport.contacts.models import Contact
from ureport.contacts.sync import (
    JOB_TYPE,
    LEASE_SECONDS,
    LOCK_BACKOFF,
    RATE_LIMIT_BACKOFF,
    enqueue_org_syncs,
    finalize_contacts_sync,
    sync_contacts,
    sync_contacts_dispatch,
)
from ureport.syncjobs.models import ABORTED, SyncJob
from ureport.syncjobs.testing import SyncJobTestMixin, drop_lease, held_lock, make_stale, run_task
from ureport.tests import UreportTest

RAPIDPRO_BACKEND = "ureport.backend.rapidpro.RapidProBackend"


def outcome_counts(created=0, updated=0, deleted=0, ignored=0):
    return {
        SyncOutcome.created: created,
        SyncOutcome.updated: updated,
        SyncOutcome.deleted: deleted,
        SyncOutcome.ignored: ignored,
    }


def chunk_counts(created=0, updated=0, deleted=0, ignored=0):
    return {"created": created, "updated": updated, "deleted": deleted, "ignored": ignored}


class SyncContactsTest(SyncJobTestMixin, UreportTest):
    def setUp(self):
        super().setUp()

        self.nigeria.backends.exclude(slug="rapidpro").delete()
        self.job = SyncJob.get_or_create_job(self.nigeria, JOB_TYPE, scope="rapidpro")
        self.last_fetched_key = Contact.CONTACT_LAST_FETCHED_CACHE_KEY % (self.nigeria.pk, "rapidpro")
        cache.delete(self.last_fetched_key)

        # everything a chunk reaches out of the process for, and the org counts refresh
        # finalization does
        self.mock_pull_fields = self.start_patch(patch(f"{RAPIDPRO_BACKEND}.pull_fields"))
        self.mock_pull_boundaries = self.start_patch(patch(f"{RAPIDPRO_BACKEND}.pull_boundaries"))
        self.mock_pull_contacts_chunk = self.start_patch(patch(f"{RAPIDPRO_BACKEND}.pull_contacts_chunk"))
        self.mock_update_counts = self.start_patch(patch("ureport.contacts.sync.update_cache_org_contact_counts"))

    def _run(self, times=1):
        return run_task(sync_contacts, self.job.id, times=times)

    def _task_state(self):
        return TaskState.objects.filter(org=self.nigeria, task_key=JOB_TYPE).first()

    def test_stages_run_in_order_across_chunks(self):
        self.mock_pull_fields.return_value = outcome_counts(created=1, updated=2, deleted=3, ignored=4)
        self.mock_pull_boundaries.return_value = outcome_counts(created=5, updated=6, deleted=7, ignored=8)
        self.mock_pull_contacts_chunk.side_effect = [
            ChunkResult(counts=chunk_counts(created=9, updated=10), cursor={"stage": "active", "resume": "c1"}),
            ChunkResult(counts=chunk_counts(deleted=11, ignored=12), cursor={}, done=True),
        ]

        # fields
        mock_continue = self._run()
        job = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(job.cursor["stage"], "boundaries")
        self.assertIsNone(job.cursor["since"])
        until = job.cursor["until"]
        mock_continue.assert_called_once_with((self.job.id,), queue="celery", countdown=None)
        self.mock_pull_boundaries.assert_not_called()

        # boundaries
        self._run()
        job = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(job.cursor["stage"], "contacts")
        self.assertEqual(job.cursor["until"], until)
        self.mock_pull_contacts_chunk.assert_not_called()

        # first chunk of contacts, resuming from the backend's own sub-cursor on the next
        self._run()
        job = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(job.cursor["stage"], "contacts")
        self.assertEqual(job.cursor["resume"], {"stage": "active", "resume": "c1"})
        self.assertEqual(job.status, SyncJob.STATUS_RUNNING)

        # last chunk of contacts
        self._run()
        job = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.cursor, {"last_until": until})
        self.assertEqual(
            job.progress,
            {
                "chunks": 4,
                "fields_created": 1,
                "fields_updated": 2,
                "fields_deleted": 3,
                "fields_ignored": 4,
                "boundaries_created": 5,
                "boundaries_updated": 6,
                "boundaries_deleted": 7,
                "boundaries_ignored": 8,
                "contacts_created": 9,
                "contacts_updated": 10,
                "contacts_deleted": 11,
                "contacts_ignored": 12,
            },
        )

        self.assertEqual(self.mock_pull_contacts_chunk.call_args_list[0][0], (self.nigeria, None, until, {}))
        self.assertEqual(
            self.mock_pull_contacts_chunk.call_args_list[1][0],
            (self.nigeria, None, until, {"stage": "active", "resume": "c1"}),
        )

        # each chunk holds the lock the ad-hoc contact tasks coordinate through, and leaves
        # it released
        self.assertIsNone(get_valkey_connection().get(TaskState.get_lock_key(self.nigeria, JOB_TYPE)))

    def test_window_frozen_until_run_completes(self):
        self.mock_pull_fields.return_value = outcome_counts()
        self.mock_pull_boundaries.return_value = outcome_counts()
        self.mock_pull_contacts_chunk.side_effect = [
            ChunkResult(counts=chunk_counts(), cursor={"stage": "deleted"}),
            ChunkResult(counts=chunk_counts(), cursor={}, done=True),
            ChunkResult(counts=chunk_counts(), cursor={}, done=True),
        ]

        first_run = timezone.now()
        with patch("ureport.contacts.sync.timezone.now", return_value=first_run):
            self._run(times=2)  # fields, boundaries

        # time moves on but the window the run started with is what every chunk sees
        with patch("ureport.contacts.sync.timezone.now", return_value=first_run + timedelta(minutes=30)):
            self._run(times=2)

        first_until = SyncJob.objects.get(id=self.job.id).cursor["last_until"]
        windows = [call[0][1:3] for call in self.mock_pull_contacts_chunk.call_args_list]
        self.assertEqual(windows, [(None, first_until), (None, first_until)])

        # the next run picks up where this one ended and freezes a new window
        second_run = first_run + timedelta(hours=1)
        with patch("ureport.contacts.sync.timezone.now", return_value=second_run):
            self._run(times=3)

        job = SyncJob.objects.get(id=self.job.id)
        self.assertNotEqual(job.cursor["last_until"], first_until)
        self.assertEqual(
            self.mock_pull_contacts_chunk.call_args_list[-1][0][1:3], (first_until, job.cursor["last_until"])
        )

    def test_failed_run_resumes_with_the_same_window(self):
        self.mock_pull_fields.return_value = outcome_counts()
        self.mock_pull_boundaries.return_value = outcome_counts()
        self.mock_pull_contacts_chunk.side_effect = ValueError("boom")

        self._run(times=2)  # fields, boundaries
        until = SyncJob.objects.get(id=self.job.id).cursor["until"]

        with self.assertRaises(ValueError):
            self._run()

        job = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(job.status, SyncJob.STATUS_FAILED)
        self.assertEqual(job.cursor["until"], until)

        # the failure is reported where the pre-chunking task reported it
        self.assertTrue(self._task_state().is_failing)

        # the retry resumes the interrupted run against its frozen window
        self.mock_pull_contacts_chunk.side_effect = None
        self.mock_pull_contacts_chunk.return_value = ChunkResult(counts=chunk_counts(), cursor={}, done=True)
        self._run()

        self.assertEqual(self.mock_pull_contacts_chunk.call_args[0][1:3], (None, until))
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={"last_until": until})
        self.assertFalse(self._task_state().is_failing)

        # the fields and boundaries stages aren't redone by the retry
        self.assertEqual(self.mock_pull_fields.call_count, 1)
        self.assertEqual(self.mock_pull_boundaries.call_count, 1)

    def test_lost_lease_discards_the_chunk(self):
        def steal_lease(org):
            SyncJob.objects.filter(id=self.job.id).update(lease_owner="thief")
            return outcome_counts()

        self.mock_pull_fields.side_effect = steal_lease
        self.mock_pull_boundaries.return_value = outcome_counts()

        self._run()

        # the stage advance went down with the chunk - nothing was written
        self.assertJobState(self.job, cursor={}, status=SyncJob.STATUS_RUNNING)
        self.assertIsNone(self._task_state())  # a lost lease isn't this worker's failure

        # so the run that takes over pulls the fields stage again
        self.mock_pull_fields.side_effect = None
        self.mock_pull_fields.return_value = outcome_counts()
        drop_lease(self.job)

        self._run()

        self.assertEqual(self.mock_pull_fields.call_count, 2)
        self.assertEqual(SyncJob.objects.get(id=self.job.id).cursor["stage"], "boundaries")

    def test_first_run_seeds_since_from_legacy_cache_key(self):
        cache.set(self.last_fetched_key, "2026-08-10T10:00:00.000Z", None)
        self.mock_pull_fields.return_value = outcome_counts()
        self.mock_pull_boundaries.return_value = outcome_counts()
        self.mock_pull_contacts_chunk.return_value = ChunkResult(counts=chunk_counts(), cursor={}, done=True)

        self._run(times=3)

        self.assertEqual(self.mock_pull_contacts_chunk.call_args[0][1], "2026-08-10T10:00:00.000Z")

    def test_rate_limited_chunk_delays_continuation(self):
        self.mock_pull_fields.return_value = outcome_counts()
        self.mock_pull_boundaries.return_value = outcome_counts()
        self.mock_pull_contacts_chunk.return_value = ChunkResult(
            counts=chunk_counts(created=3), cursor={"stage": "active", "resume": "c1"}, rate_limited=True
        )

        self._run(times=2)  # fields, boundaries
        mock_continue = self._run()

        mock_continue.assert_called_once_with((self.job.id,), queue="celery", countdown=RATE_LIMIT_BACKOFF)

        # the chunk's progress is kept so the backoff costs nothing
        job = SyncJob.objects.get(id=self.job.id)
        self.assertEqual(job.progress["contacts_created"], 3)
        self.assertEqual(job.cursor["resume"], {"stage": "active", "resume": "c1"})

    def test_backs_off_while_another_contact_task_holds_the_lock(self):
        with held_lock(TaskState.get_lock_key(self.nigeria, JOB_TYPE)):
            mock_continue = self._run()

        mock_continue.assert_called_once_with((self.job.id,), queue="celery", countdown=LOCK_BACKOFF)
        self.mock_pull_fields.assert_not_called()
        self.assertJobState(self.job, cursor={})

    def test_completion_finalizes(self):
        self.mock_pull_fields.return_value = outcome_counts()
        self.mock_pull_boundaries.return_value = outcome_counts()
        self.mock_pull_contacts_chunk.return_value = ChunkResult(counts=chunk_counts(), cursor={}, done=True)

        self._run(times=3)

        job = SyncJob.objects.get(id=self.job.id)
        self.mock_update_counts.assert_called_once_with(self.nigeria)
        self.assertFalse(job.needs_finalize)

        # the pre-chunking task's resume point is kept up to date so a rollback resumes here
        self.assertEqual(cache.get(self.last_fetched_key), job.cursor["last_until"])

        # as is the org task state the task status endpoint reports contact syncing from
        state = self._task_state()
        self.assertEqual(state.last_successfully_started_on, job.ended_on)
        self.assertEqual(state.ended_on, job.ended_on)
        self.assertFalse(state.is_failing)
        self.assertEqual(json.loads(state.last_results), {"rapidpro": job.progress})

        # finalization is retried after crashes and takeovers, so it must stay idempotent
        finalize_contacts_sync(SyncJob.objects.get(id=self.job.id))

        self.assertEqual(cache.get(self.last_fetched_key), job.cursor["last_until"])
        self.assertEqual(json.loads(self._task_state().last_results), {"rapidpro": job.progress})

    def test_finalize_keeps_the_other_backends_results(self):
        self.nigeria.backends.create(
            slug="floip",
            backend_type=RAPIDPRO_BACKEND,
            api_token="token",
            host="http://localhost:8001",
            created_by=self.admin,
            modified_by=self.admin,
        )
        self.mock_pull_fields.return_value = outcome_counts()
        self.mock_pull_boundaries.return_value = outcome_counts()
        self.mock_pull_contacts_chunk.return_value = ChunkResult(counts=chunk_counts(created=1), cursor={}, done=True)

        self._run(times=3)
        rapidpro_progress = SyncJob.objects.get(id=self.job.id).progress

        self.job = SyncJob.get_or_create_job(self.nigeria, JOB_TYPE, scope="floip")
        self._run(times=3)
        floip_progress = SyncJob.objects.get(id=self.job.id).progress

        self.assertEqual(
            json.loads(self._task_state().last_results),
            {"rapidpro": rapidpro_progress, "floip": floip_progress},
        )

    def test_deactivated_backend_aborts_the_run(self):
        cache.set(self.last_fetched_key, "2026-08-10T10:00:00.000Z", None)
        self.mock_pull_fields.return_value = outcome_counts()
        self.mock_pull_boundaries.return_value = outcome_counts()

        self._run(times=2)  # fields, boundaries - a run with a window in flight
        self.nigeria.backends.filter(slug="rapidpro").update(is_active=False)

        self._run()

        self.mock_pull_contacts_chunk.assert_not_called()

        # the window this run never covered is left for the next one to pull again, and the
        # page cursor it was resuming from is dropped with it
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={"last_until": "2026-08-10T10:00:00.000Z"})

        # a run that didn't sync anything isn't reported as one that did
        self.assertEqual(cache.get(self.last_fetched_key), "2026-08-10T10:00:00.000Z")
        self.assertIsNone(self._task_state())
        self.mock_update_counts.assert_not_called()

    def test_deactivated_backend_leaves_an_idle_job_alone(self):
        SyncJob.objects.filter(id=self.job.id).update(cursor={"last_until": "2026-08-10T10:00:00.000Z"})
        self.nigeria.backends.filter(slug="rapidpro").update(is_active=False)

        self._run()

        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={"last_until": "2026-08-10T10:00:00.000Z"})
        self.mock_pull_fields.assert_not_called()

    def test_disabling_the_pull_aborts_the_run(self):
        self.mock_pull_fields.return_value = outcome_counts()
        self.mock_pull_boundaries.return_value = outcome_counts()

        self._run(times=2)  # fields, boundaries
        TaskState.objects.update_or_create(org=self.nigeria, task_key=JOB_TYPE, defaults={"is_disabled": True})

        self._run()

        # nothing to resume from, and no window claimed
        job = self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={})
        self.assertEqual(job.progress[ABORTED], 1)
        self.mock_pull_contacts_chunk.assert_not_called()

        state = self._task_state()
        self.assertIsNone(state.last_successfully_started_on)
        self.assertIsNone(cache.get(self.last_fetched_key))
        self.mock_update_counts.assert_not_called()


class DispatchTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.nigeria.backends.exclude(slug="rapidpro").delete()
        self.uganda.is_active = False
        self.uganda.save(update_fields=("is_active",))

    def test_dispatch_creates_and_enqueues_a_job_per_backend(self):
        self.uganda.is_active = True
        self.uganda.save(update_fields=("is_active",))
        self.nigeria.backends.create(
            slug="floip",
            backend_type=RAPIDPRO_BACKEND,
            api_token="token",
            host="http://localhost:8001",
            created_by=self.admin,
            modified_by=self.admin,
        )

        with patch.object(sync_contacts, "apply_async") as mock_enqueue:
            sync_contacts_dispatch()

        jobs = SyncJob.objects.filter(job_type=JOB_TYPE)
        self.assertEqual(
            {(job.org.subdomain, job.scope) for job in jobs},
            {("nigeria", "rapidpro"), ("nigeria", "floip"), ("uganda", "rapidpro")},
        )
        self.assertEqual(mock_enqueue.call_count, 3)
        self.assertEqual({call[0][0][0] for call in mock_enqueue.call_args_list}, {job.id for job in jobs})

        # dispatching again reuses the same jobs
        with patch.object(sync_contacts, "apply_async"):
            sync_contacts_dispatch()

        self.assertEqual(SyncJob.objects.filter(job_type=JOB_TYPE).count(), 3)

    def test_dispatch_leaves_a_run_in_flight_alone(self):
        job = SyncJob.get_or_create_job(self.nigeria, JOB_TYPE, scope="rapidpro")
        job.claim("worker-1", lease_seconds=600)

        # under a live lease - a chunk is being worked on
        with patch.object(sync_contacts, "apply_async") as mock_enqueue:
            sync_contacts_dispatch()

        mock_enqueue.assert_not_called()

        # and between chunks, where the lease is released but a continuation is on its way
        job.checkpoint(cursor={"stage": "contacts"})
        job.release_lease()

        with patch.object(sync_contacts, "apply_async") as mock_enqueue:
            sync_contacts_dispatch()

        mock_enqueue.assert_not_called()

        # a run that stopped checkpointing entirely lost its continuation, so nudge it
        make_stale(job, seconds_ago=2 * LEASE_SECONDS + 60)

        with patch.object(sync_contacts, "apply_async") as mock_enqueue:
            sync_contacts_dispatch()

        mock_enqueue.assert_called_once_with((job.id,), queue="celery")

    def test_dispatch_retries_a_failed_run(self):
        job = SyncJob.get_or_create_job(self.nigeria, JOB_TYPE, scope="rapidpro")
        job.claim("worker-1")
        job.checkpoint(cursor={"stage": "contacts", "since": None, "until": "2026-08-11T10:00:00.000Z"})
        job.record_failure("boom")

        with patch.object(sync_contacts, "apply_async") as mock_enqueue:
            sync_contacts_dispatch()

        mock_enqueue.assert_called_once_with((job.id,), queue="celery")

    def test_dispatch_skips_paused_jobs(self):
        job = SyncJob.get_or_create_job(self.nigeria, JOB_TYPE, scope="rapidpro")
        SyncJob.objects.filter(id=job.id).update(status=SyncJob.STATUS_PAUSED)

        with patch.object(sync_contacts, "apply_async") as mock_enqueue:
            sync_contacts_dispatch()

        mock_enqueue.assert_not_called()

    def test_dispatch_skips_orgs_with_the_pull_disabled(self):
        TaskState.objects.create(org=self.nigeria, task_key=JOB_TYPE, is_disabled=True)

        with patch.object(sync_contacts, "apply_async") as mock_enqueue:
            sync_contacts_dispatch()

        self.assertFalse(SyncJob.objects.filter(org=self.nigeria, job_type=JOB_TYPE).exists())
        mock_enqueue.assert_not_called()

    def test_enqueue_org_syncs_reports_what_it_did(self):
        with patch.object(sync_contacts, "apply_async") as mock_enqueue:
            result = enqueue_org_syncs(self.nigeria)

        job = SyncJob.objects.get(org=self.nigeria, job_type=JOB_TYPE, scope="rapidpro")
        self.assertEqual(result, {"enqueued": {"rapidpro": job.id}, "skipped": {}})
        mock_enqueue.assert_called_once_with((job.id,), queue="celery")

        job.claim("worker-1", lease_seconds=600)

        with patch.object(sync_contacts, "apply_async") as mock_enqueue:
            result = enqueue_org_syncs(self.nigeria)

        self.assertEqual(result, {"enqueued": {}, "skipped": {"rapidpro": job.id}})
        mock_enqueue.assert_not_called()
