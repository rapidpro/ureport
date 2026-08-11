# -*- coding: utf-8 -*-

from django_valkey import get_valkey_connection
from mock import patch

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from dash.orgs.models import TaskState
from ureport.contacts.maintenance import (
    ACTIVITIES_BACKFILL,
    ACTIVITIES_JOB_TYPE,
    LEASE_SECONDS,
    PENDING_KEY,
    POPULATED_KEY,
    REBUILD_JOB_TYPE,
    REBUILD_LOCK_TIMEOUT,
    RESULTS_BACKFILL,
    RESULTS_JOB_TYPE,
    TRIGGER_RETRY,
    backfill_activities_schemes,
    backfill_results_schemes,
    rebuild_reporters_counts,
    resume_schemes_backfill,
)
from ureport.contacts.models import Contact
from ureport.contacts.sync import (
    JOB_TYPE as PULL_JOB_TYPE,
    LEASE_SECONDS as PULL_LEASE_SECONDS,
    LOCK_BACKOFF,
    finalize_contacts_sync,
    sync_contacts,
)
from ureport.contacts.tasks import (
    populate_contact_activities_schemes,
    populate_contact_schemes,
    populate_poll_results_schemes,
    rebuild_contacts_counts,
)
from ureport.polls.models import PollResult
from ureport.stats.models import ContactActivity
from ureport.syncjobs.models import SyncJob
from ureport.syncjobs.testing import (
    SyncJobTestMixin,
    drop_lease,
    expire_lease,
    held_lock,
    hold_lease,
    make_stale,
    reload,
    run_task,
    run_to_completion,
)
from ureport.tests import UreportTest

QUEUE = "slow"


class MaintenanceTest(SyncJobTestMixin, UreportTest):
    """
    Shared plumbing: these jobs and the cache keys they carry over from the pre-chunking tasks
    outlive a test, so each test starts from a clean slate.
    """

    def setUp(self):
        super().setUp()

        self.nigeria.backends.exclude(slug="rapidpro").delete()

        for key in (
            ACTIVITIES_BACKFILL.done_key,
            ACTIVITIES_BACKFILL.cursor_key,
            RESULTS_BACKFILL.done_key,
            RESULTS_BACKFILL.cursor_key,
            POPULATED_KEY,
            PENDING_KEY,
        ):
            cache.delete(key % self.nigeria.id)
            cache.delete(key % self.uganda.id)

    def _task_states(self):
        return TaskState.objects.filter(org__in=(self.nigeria, self.uganda))


class RebuildReportersCountsTest(MaintenanceTest):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(self.nigeria, REBUILD_JOB_TYPE)

    def _run(self, times=1):
        return run_task(rebuild_reporters_counts, self.job.id, times=times)

    @patch("ureport.contacts.models.Contact.recalculate_reporters_stats")
    def test_rebuild_is_a_single_chunk(self, mock_recalculate):
        self.assertEqual(run_to_completion(rebuild_reporters_counts, self.job.id), 1)

        mock_recalculate.assert_called_once_with(self.nigeria)
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, progress={"chunks": 1}, lease_owner=None)

        # the lock the contact tasks coordinate through is left released
        self.assertIsNone(get_valkey_connection().get(TaskState.get_lock_key(self.nigeria, PULL_JOB_TYPE)))

        # rebuilding counters isn't pulling, so it reports no pull in the org's task state
        self.assertFalse(self._task_states().exists())

    @patch("ureport.contacts.models.Contact.recalculate_reporters_stats")
    def test_backs_off_while_a_contact_task_holds_the_lock(self, mock_recalculate):
        with held_lock(TaskState.get_lock_key(self.nigeria, PULL_JOB_TYPE)):
            mock_continue = self._run()

        mock_continue.assert_called_once_with((self.job.id,), queue=QUEUE, countdown=LOCK_BACKOFF)
        mock_recalculate.assert_not_called()

        # a rebuild spinning on a busy org is visible in its progress
        self.assertJobState(self.job, status=SyncJob.STATUS_RUNNING, progress={"lock_backoffs": 1})

        # and the retry that follows the backoff does the rebuild
        self._run()

        mock_recalculate.assert_called_once_with(self.nigeria)
        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, progress={"lock_backoffs": 1, "chunks": 1})

    @patch("ureport.contacts.models.Contact.recalculate_reporters_stats")
    def test_chunk_holds_the_lock_beyond_its_lease(self, mock_recalculate):
        ttls = []
        mock_recalculate.side_effect = lambda org: ttls.append(
            get_valkey_connection().ttl(TaskState.get_lock_key(org, PULL_JOB_TYPE))
        )

        self._run()

        # the lock has to outlast the lease, or it stops keeping a second worker out at the
        # very moment the expiring lease lets one claim the job
        self.assertGreater(ttls[0], LEASE_SECONDS)

    @patch("ureport.contacts.models.Contact.recalculate_reporters_stats")
    def test_reclaim_of_an_overrunning_rebuild_backs_off(self, mock_recalculate):
        self.assertGreater(REBUILD_LOCK_TIMEOUT, LEASE_SECONDS)

        # a rebuild that outran its lease: still holding the lock, no longer holding the job
        self.job.claim("worker-1", lease_seconds=LEASE_SECONDS)
        expire_lease(self.job)

        with held_lock(TaskState.get_lock_key(self.nigeria, PULL_JOB_TYPE), timeout=REBUILD_LOCK_TIMEOUT):
            mock_continue = self._run()

        # the worker that reclaimed the job backs off instead of rebuilding the same counters
        mock_recalculate.assert_not_called()
        mock_continue.assert_called_once_with((self.job.id,), queue=QUEUE, countdown=LOCK_BACKOFF)

    def test_shim_enqueues_a_job_per_active_org(self):
        with patch.object(rebuild_reporters_counts, "apply_async") as mock_enqueue:
            result = rebuild_contacts_counts()

        jobs = {job.org_id: job.id for job in SyncJob.objects.filter(job_type=REBUILD_JOB_TYPE)}
        self.assertEqual(set(jobs), {self.nigeria.id, self.uganda.id})
        self.assertEqual(result, {"enqueued": jobs, "skipped": {}})
        self.assertEqual({call[0][0][0] for call in mock_enqueue.call_args_list}, set(jobs.values()))
        self.assertEqual(mock_enqueue.call_args_list[0][1], {"queue": QUEUE})

        # enqueuing isn't rebuilding, so it must not report anything in the orgs' task states
        self.assertFalse(self._task_states().exists())

        # triggering again reuses the same jobs
        with patch.object(rebuild_reporters_counts, "apply_async"):
            rebuild_contacts_counts()

        self.assertEqual(SyncJob.objects.filter(job_type=REBUILD_JOB_TYPE).count(), 2)

    def test_shim_can_be_limited_to_one_org(self):
        with patch.object(rebuild_reporters_counts, "apply_async") as mock_enqueue:
            result = rebuild_contacts_counts(org_id=self.nigeria.id)

        mock_enqueue.assert_called_once_with((self.job.id,), queue=QUEUE)
        self.assertEqual(result, {"enqueued": {self.nigeria.id: self.job.id}, "skipped": {}})
        self.assertFalse(SyncJob.objects.filter(job_type=REBUILD_JOB_TYPE, org=self.uganda).exists())

    def test_shim_leaves_a_run_in_flight_alone(self):
        hold_lease(self.job)

        with patch.object(rebuild_reporters_counts, "apply_async") as mock_enqueue:
            result = rebuild_contacts_counts(org_id=self.nigeria.id)

        mock_enqueue.assert_not_called()
        self.assertEqual(result, {"enqueued": {}, "skipped": {self.nigeria.id: self.job.id}})

    def test_shim_skips_inactive_orgs(self):
        self.uganda.is_active = False
        self.uganda.save(update_fields=("is_active",))

        with patch.object(rebuild_reporters_counts, "apply_async"):
            result = rebuild_contacts_counts()

        self.assertEqual(list(result["enqueued"]), [self.nigeria.id])


class SchemesBackfillTest(MaintenanceTest):
    """
    Both backfills walk the org's contacts the same way, so the progression, resume and skip
    cases are covered against the contact activities one and the poll results one is checked
    for the rows it updates and the chain it ends.
    """

    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(self.nigeria, ACTIVITIES_JOB_TYPE)
        self.contacts = [self._create_contact(f"C-00{i}", "tel") for i in range(5)]

        # a contact whose scheme the pull hasn't filled in - not this backfill's to copy
        self.schemeless = self._create_contact("C-009", None)

    def _create_contact(self, uuid, scheme, org=None):
        org = org or self.nigeria
        contact = Contact.objects.create(org=org, uuid=uuid, gender="M", born=1990, scheme=scheme)
        ContactActivity.objects.create(org=org, contact=uuid, date=timezone.now().date())
        PollResult.objects.create(org=org, flow="flow-1", ruleset="ruleset-1", contact=uuid, completed=False)
        return contact

    def _run(self, task=None, times=1):
        """
        Runs the backfill task, holding back both what it might ask a continuation of and the
        backfill its finalization chains.
        """
        task = task or backfill_activities_schemes
        with patch.object(backfill_results_schemes, "apply_async") as mock_chain:
            mock_continue = run_task(task, self.job.id, times=times)
        return mock_continue, mock_chain

    def _activity_schemes(self):
        return {a.contact: a.scheme for a in ContactActivity.objects.filter(org=self.nigeria)}

    def _result_schemes(self):
        return {r.contact: r.scheme for r in PollResult.objects.filter(org=self.nigeria)}

    @patch("ureport.contacts.maintenance.BATCHES_PER_CHUNK", 2)
    @patch("ureport.contacts.maintenance.BATCH_SIZE", 2)
    def test_batches_progress_across_chunks(self):
        # first chunk fills its two batches, so there may be more behind it
        mock_continue, _ = self._run()

        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_RUNNING,
            cursor={"max_id": self.contacts[3].id},
            progress={"chunks": 2, "contacts": 4},
        )
        mock_continue.assert_called_once_with((self.job.id,), queue=QUEUE, countdown=None)

        self.assertEqual(
            self._activity_schemes(),
            {"C-000": "tel", "C-001": "tel", "C-002": "tel", "C-003": "tel", "C-004": None, "C-009": None},
        )

        # the pre-chunking task's cursor is dual written so a rollback to it resumes here
        self.assertEqual(cache.get(ACTIVITIES_BACKFILL.cursor_key % self.nigeria.id), self.contacts[3].id)

        # the second chunk finishes the contacts and, being short, ends the run
        mock_continue, mock_chain = self._run()

        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_COMPLETE,
            cursor={"max_id": self.contacts[4].id},
            progress={"chunks": 3, "contacts": 5},
        )
        mock_continue.assert_not_called()

        # the schemeless contact is left for a run that comes after the pull that fills it in
        self.assertEqual(self._activity_schemes()["C-004"], "tel")
        self.assertIsNone(self._activity_schemes()["C-009"])

        # completion dual writes the pre-chunking task's done flag and chains the next backfill
        self.assertIsNotNone(cache.get(ACTIVITIES_BACKFILL.done_key % self.nigeria.id))

        results_job = SyncJob.objects.get(org=self.nigeria, job_type=RESULTS_JOB_TYPE)
        mock_chain.assert_called_once_with((results_job.id,), queue=QUEUE)

    @patch("ureport.contacts.maintenance.BATCHES_PER_CHUNK", 1)
    @patch("ureport.contacts.maintenance.BATCH_SIZE", 2)
    def test_run_resumes_from_its_cursor(self):
        self._run()
        self.assertJobState(self.job, cursor={"max_id": self.contacts[1].id})

        # as a worker that died mid run would, drop the lease and let another one take over
        drop_lease(self.job)
        self._run()

        self.assertJobState(self.job, cursor={"max_id": self.contacts[3].id})
        self.assertEqual(self._activity_schemes()["C-003"], "tel")
        self.assertIsNone(self._activity_schemes()["C-004"])

    @patch("ureport.contacts.maintenance.BATCHES_PER_CHUNK", 1)
    @patch("ureport.contacts.maintenance.BATCH_SIZE", 2)
    def test_first_chunk_seeds_from_legacy_max_id(self):
        cache.set(ACTIVITIES_BACKFILL.cursor_key % self.nigeria.id, self.contacts[3].id, None)

        self._run()

        # the contacts the pre-chunking task already did aren't done again, bar the batch it
        # may have died part way through - it wrote that position per contact, not per batch
        self.assertJobState(self.job, cursor={"max_id": self.contacts[3].id})
        self.assertEqual(
            self._activity_schemes(),
            {"C-000": None, "C-001": None, "C-002": "tel", "C-003": "tel", "C-004": None, "C-009": None},
        )

    def test_legacy_done_flag_skips_everything(self):
        cache.set(ACTIVITIES_BACKFILL.done_key % self.nigeria.id, "2026-01-01T00:00:00.000Z", None)

        _, mock_chain = self._run()

        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, progress={"skipped": 1}, cursor={})
        self.assertEqual(set(self._activity_schemes().values()), {None})

        # the flag it skipped on is left set, refreshed with this run's own completion
        done = cache.get(ACTIVITIES_BACKFILL.done_key % self.nigeria.id)
        self.assertIsNotNone(done)
        self.assertNotEqual(done, "2026-01-01T00:00:00.000Z")

        # and the chain to the next backfill is what the pre-chunking task did here too
        results_job = SyncJob.objects.get(org=self.nigeria, job_type=RESULTS_JOB_TYPE)
        mock_chain.assert_called_once_with((results_job.id,), queue=QUEUE)

    @patch("ureport.contacts.maintenance.BATCHES_PER_CHUNK", 1)
    @patch("ureport.contacts.maintenance.BATCH_SIZE", 4)
    def test_batch_updates_once_per_scheme(self):
        self.contacts[1].scheme = "facebook"
        self.contacts[1].save(update_fields=("scheme",))

        with CaptureQueriesContext(connection) as queries:
            self._run()

        # a batch is a thousand contacts over a handful of schemes, so it's one update per
        # distinct scheme rather than one per contact
        updates = [q["sql"] for q in queries.captured_queries if 'UPDATE "stats_contactactivity"' in q["sql"]]
        self.assertEqual(len(updates), 2)

        self.assertEqual(self._activity_schemes()["C-001"], "facebook")
        self.assertEqual(self._activity_schemes()["C-002"], "tel")

    def test_backfill_is_scoped_to_its_org(self):
        other = self._create_contact("C-100", "tel", org=self.uganda)

        self._run()

        self.assertIsNone(ContactActivity.objects.get(org=self.uganda, contact=other.uuid).scheme)
        self.assertEqual(set(self._activity_schemes().values()), {"tel", None})

    @patch("ureport.contacts.maintenance.BATCHES_PER_CHUNK", 1)
    @patch("ureport.contacts.maintenance.BATCH_SIZE", 2)
    def test_results_backfill_updates_poll_results(self):
        self.job = SyncJob.get_or_create_job(self.nigeria, RESULTS_JOB_TYPE)

        self._run(task=backfill_results_schemes)

        self.assertJobState(self.job, status=SyncJob.STATUS_RUNNING)
        self.assertEqual(self._result_schemes()["C-001"], "tel")
        self.assertIsNone(self._result_schemes()["C-002"])
        self.assertEqual(set(self._activity_schemes().values()), {None})

        self.assertEqual(run_to_completion(backfill_results_schemes, self.job.id), 2)

        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)
        self.assertEqual(self._result_schemes()["C-004"], "tel")
        self.assertIsNotNone(cache.get(RESULTS_BACKFILL.done_key % self.nigeria.id))

        # nothing is chained after the last backfill
        self.assertEqual(
            SyncJob.objects.get(org=self.nigeria, job_type=ACTIVITIES_JOB_TYPE).status, SyncJob.STATUS_PENDING
        )

    def test_shims_only_enqueue(self):
        with patch.object(backfill_activities_schemes, "apply_async") as mock_enqueue:
            job_id = populate_contact_activities_schemes(self.nigeria.id)

        job = SyncJob.objects.get(org=self.nigeria, job_type=ACTIVITIES_JOB_TYPE)
        self.assertEqual(job_id, job.id)
        mock_enqueue.assert_called_once_with((job.id,), queue=QUEUE)

        with patch.object(backfill_results_schemes, "apply_async") as mock_enqueue:
            job_id = populate_poll_results_schemes(self.nigeria.id)

        job = SyncJob.objects.get(org=self.nigeria, job_type=RESULTS_JOB_TYPE)
        self.assertEqual(job_id, job.id)
        mock_enqueue.assert_called_once_with((job.id,), queue=QUEUE)

        # neither backfilled anything itself, nor reported one in the org's task state
        self.assertEqual(set(self._activity_schemes().values()), {None})
        self.assertEqual(set(self._result_schemes().values()), {None})
        self.assertFalse(self._task_states().exists())


class SchemesBackfillTriggerTest(MaintenanceTest):
    """
    The pre-chunking trigger re-pulled every contact and only then backfilled their schemes.
    The re-pull is now the chunked sync's, so the trigger asks it for one and the backfill
    waits on it - it only copies schemes that are already there, and never revisits a contact
    it has passed.
    """

    def setUp(self):
        super().setUp()

        self.pull_job = SyncJob.get_or_create_job(self.nigeria, PULL_JOB_TYPE, scope="rapidpro")
        self.last_fetched_key = Contact.CONTACT_LAST_FETCHED_CACHE_KEY % (self.nigeria.pk, "rapidpro")
        cache.delete(self.last_fetched_key)

    def _trigger(self):
        """
        Runs the trigger, holding back everything it might enqueue: the contact pulls, the
        backfill, and the retry of itself.
        """
        with patch.object(sync_contacts, "apply_async") as mock_pull:
            with patch.object(backfill_activities_schemes, "apply_async") as mock_backfill:
                with patch.object(populate_contact_schemes, "apply_async") as mock_retry:
                    result = populate_contact_schemes(self.nigeria.id)
        return result, mock_pull, mock_backfill, mock_retry

    def _complete_pull(self, scope="rapidpro"):
        """
        Runs a contact sync run for the given backend through to its finalization, as a
        completing chunk would.
        """
        job = SyncJob.get_or_create_job(self.nigeria, PULL_JOB_TYPE, scope=scope)
        job.claim("worker-1")
        job.checkpoint(cursor={"last_until": "2026-08-11T10:00:00.000Z"})
        job.mark_complete()

        with patch("ureport.contacts.sync.update_cache_org_contact_counts"):
            with patch.object(backfill_activities_schemes, "apply_async") as mock_backfill:
                finalize_contacts_sync(reload(job))

        job.release_lease()
        return mock_backfill

    def test_trigger_forces_a_repull_the_backfill_then_waits_on(self):
        SyncJob.objects.filter(id=self.pull_job.id).update(cursor={"last_until": "2026-08-10T10:00:00.000Z"})
        cache.set(self.last_fetched_key, "2026-08-10T10:00:00.000Z", None)

        result, mock_pull, mock_backfill, mock_retry = self._trigger()

        self.assertEqual(result, {"repulled": ["rapidpro"], "skipped": [], "backfill": None})
        mock_pull.assert_called_once_with((self.pull_job.id,), queue="celery")
        mock_retry.assert_not_called()

        # both resume positions are dropped so the run pulls everything again
        self.assertJobState(self.pull_job, cursor={})
        self.assertIsNone(cache.get(self.last_fetched_key))

        # the backfill isn't started yet - it would skip past contacts the re-pull hasn't
        # given a scheme to and never come back to them
        mock_backfill.assert_not_called()
        self.assertIsNotNone(cache.get(PENDING_KEY % self.nigeria.id))

        # completing the re-pull is what starts it
        mock_backfill = self._complete_pull()

        backfill_job = SyncJob.objects.get(org=self.nigeria, job_type=ACTIVITIES_JOB_TYPE)
        mock_backfill.assert_called_once_with((backfill_job.id,), queue=QUEUE)
        self.assertIsNone(cache.get(PENDING_KEY % self.nigeria.id))

        # and the re-pull it waited for is recorded, so triggering again doesn't redo it
        self.assertIsNotNone(cache.get(POPULATED_KEY % self.nigeria.id))

        result, mock_pull, _, _ = self._trigger()

        self.assertEqual(result["repulled"], [])
        mock_pull.assert_not_called()

        # triggering it is not pulling, so it reports no pull in the org's task state
        self.assertFalse(TaskState.objects.filter(org=self.nigeria, task_key=PULL_JOB_TYPE, is_failing=True).exists())

    def test_trigger_skips_the_repull_once_schemes_are_populated(self):
        cache.set(POPULATED_KEY % self.nigeria.id, "2026-01-01T00:00:00.000Z", None)
        SyncJob.objects.filter(id=self.pull_job.id).update(cursor={"last_until": "2026-08-10T10:00:00.000Z"})

        result, mock_pull, mock_backfill, _ = self._trigger()

        backfill_job = SyncJob.objects.get(org=self.nigeria, job_type=ACTIVITIES_JOB_TYPE)
        self.assertEqual(result, {"repulled": [], "skipped": [], "backfill": backfill_job.id})
        mock_backfill.assert_called_once_with((backfill_job.id,), queue=QUEUE)

        # the org's contacts already have their schemes, so nothing is re-pulled
        mock_pull.assert_not_called()
        self.assertJobState(self.pull_job, cursor={"last_until": "2026-08-10T10:00:00.000Z"})
        self.assertIsNone(cache.get(PENDING_KEY % self.nigeria.id))

    def test_trigger_refuses_while_the_pull_is_disabled(self):
        TaskState.objects.create(org=self.nigeria, task_key=PULL_JOB_TYPE, is_disabled=True)
        SyncJob.objects.filter(id=self.pull_job.id).update(cursor={"last_until": "2026-08-10T10:00:00.000Z"})

        result, mock_pull, mock_backfill, mock_retry = self._trigger()

        self.assertEqual(result, {"repulled": [], "skipped": [], "backfill": None, "disabled": True})
        mock_pull.assert_not_called()
        mock_backfill.assert_not_called()
        mock_retry.assert_not_called()

        # nothing is touched, and above all no wait is left that no pull can ever satisfy
        self.assertJobState(self.pull_job, cursor={"last_until": "2026-08-10T10:00:00.000Z"})
        self.assertIsNone(cache.get(PENDING_KEY % self.nigeria.id))

    def test_trigger_retries_until_every_backend_is_reset(self):
        self.pull_job.claim("worker-1")
        self.pull_job.checkpoint(cursor={"stage": "contacts", "since": None, "until": "2026-08-11T10:00:00.000Z"})
        cache.set(self.last_fetched_key, "2026-08-10T10:00:00.000Z", None)

        result, mock_pull, _, mock_retry = self._trigger()

        self.assertEqual(result, {"repulled": [], "skipped": ["rapidpro"], "backfill": None, "retry_in": TRIGGER_RETRY})
        mock_retry.assert_called_once_with((self.nigeria.id,), queue=QUEUE, countdown=TRIGGER_RETRY)
        mock_pull.assert_not_called()

        # the window the run is part way through isn't pulled out from under it, nor is the
        # seed it would resume from dropped
        self.assertEqual(reload(self.pull_job).cursor["until"], "2026-08-11T10:00:00.000Z")
        self.assertEqual(cache.get(self.last_fetched_key), "2026-08-10T10:00:00.000Z")

        # and above all no wait is armed: this backend's ordinary incremental run would
        # otherwise finish and pass the backfill data that was never re-pulled
        self.assertIsNone(cache.get(PENDING_KEY % self.nigeria.id))

        self._complete_pull().assert_not_called()
        self.assertFalse(SyncJob.objects.filter(job_type=ACTIVITIES_JOB_TYPE).exists())

        # the retry finds the backend free and resets it, and now the wait is armed
        result, mock_pull, _, mock_retry = self._trigger()

        self.assertEqual(result, {"repulled": ["rapidpro"], "skipped": [], "backfill": None})
        mock_retry.assert_not_called()
        mock_pull.assert_called_once_with((self.pull_job.id,), queue="celery")
        self.assertIsNotNone(cache.get(PENDING_KEY % self.nigeria.id))

        mock_backfill = self._complete_pull()

        backfill_job = SyncJob.objects.get(org=self.nigeria, job_type=ACTIVITIES_JOB_TYPE)
        mock_backfill.assert_called_once_with((backfill_job.id,), queue=QUEUE)

    def test_reset_never_clobbers_a_claimed_job(self):
        # a claimed job whose lease has expired but whose run nobody has taken over yet - not
        # in flight, so only the lease guard stands between the reset and a live run's cursor
        self.pull_job.claim("worker-1")
        self.pull_job.checkpoint(cursor={"stage": "contacts", "since": None, "until": "2026-08-11T10:00:00.000Z"})
        expire_lease(self.pull_job)
        make_stale(self.pull_job, seconds_ago=2 * PULL_LEASE_SECONDS + 60)
        cache.set(self.last_fetched_key, "2026-08-10T10:00:00.000Z", None)

        result, _, _, mock_retry = self._trigger()

        self.assertEqual(result["skipped"], ["rapidpro"])
        mock_retry.assert_called_once()

        # neither resume position is dropped, and no wait is armed on the strength of it
        self.assertEqual(reload(self.pull_job).cursor["until"], "2026-08-11T10:00:00.000Z")
        self.assertEqual(cache.get(self.last_fetched_key), "2026-08-10T10:00:00.000Z")
        self.assertIsNone(cache.get(PENDING_KEY % self.nigeria.id))

    def test_concurrent_finalizations_start_one_backfill(self):
        self._trigger()
        self._complete_pull()

        # as a second backend's finalization racing the first would, with both reading the
        # marker before either cleared it
        cache.set(PENDING_KEY % self.nigeria.id, "2026-08-11T09:00:00.000Z", None)

        with patch.object(backfill_activities_schemes, "apply_async") as mock_backfill:
            resume_schemes_backfill(self.nigeria)

        # they nudge the one job, and the framework's claim lets only one run of it proceed
        backfill_job = SyncJob.objects.get(org=self.nigeria, job_type=ACTIVITIES_JOB_TYPE)
        mock_backfill.assert_called_once_with((backfill_job.id,), queue=QUEUE)
        self.assertEqual(SyncJob.objects.filter(job_type=ACTIVITIES_JOB_TYPE).count(), 1)

    def test_backfill_waits_for_every_backend(self):
        self.nigeria.backends.create(
            slug="floip",
            backend_type="ureport.backend.rapidpro.RapidProBackend",
            api_token="token",
            host="http://localhost:8001",
            created_by=self.admin,
            modified_by=self.admin,
        )

        result, _, _, _ = self._trigger()
        self.assertEqual(sorted(result["repulled"]), ["floip", "rapidpro"])

        # one backend done isn't every backend done
        self._complete_pull("rapidpro").assert_not_called()
        self.assertIsNotNone(cache.get(PENDING_KEY % self.nigeria.id))

        mock_backfill = self._complete_pull("floip")

        backfill_job = SyncJob.objects.get(org=self.nigeria, job_type=ACTIVITIES_JOB_TYPE)
        mock_backfill.assert_called_once_with((backfill_job.id,), queue=QUEUE)

    def test_run_that_predates_the_trigger_does_not_satisfy_the_wait(self):
        self._trigger()

        # a run started before the trigger widened the window pulled less than it asks for
        cache.set(PENDING_KEY % self.nigeria.id, "2030-01-01T00:00:00.000Z", None)

        self._complete_pull().assert_not_called()
        self.assertIsNotNone(cache.get(PENDING_KEY % self.nigeria.id))

    def test_completing_a_pull_without_a_pending_backfill_does_nothing(self):
        mock_backfill = self._complete_pull()

        mock_backfill.assert_not_called()
        self.assertFalse(SyncJob.objects.filter(job_type=ACTIVITIES_JOB_TYPE).exists())

    def test_trigger_without_an_active_backend_backfills_directly(self):
        self.nigeria.backends.update(is_active=False)

        result, mock_pull, mock_backfill, _ = self._trigger()

        # there is no pull left to wait on, so waiting would strand the backfill
        backfill_job = SyncJob.objects.get(org=self.nigeria, job_type=ACTIVITIES_JOB_TYPE)
        self.assertEqual(result, {"repulled": [], "skipped": [], "backfill": backfill_job.id})
        mock_backfill.assert_called_once_with((backfill_job.id,), queue=QUEUE)
        mock_pull.assert_not_called()
        self.assertIsNone(cache.get(PENDING_KEY % self.nigeria.id))


class TaskNamesTest(UreportTest):
    def test_registered_names_are_preserved(self):
        self.assertEqual(rebuild_contacts_counts.name, "contacts.rebuild_contacts_counts")
        self.assertEqual(populate_contact_schemes.name, "ureport.contacts.tasks.populate_contact_schemes")
        self.assertEqual(populate_contact_activities_schemes.name, "contacts.populate_contact_activities_schemes")
        self.assertEqual(populate_poll_results_schemes.name, "contacts.populate_poll_results_schemes")

        self.assertEqual(rebuild_reporters_counts.name, "contacts.rebuild_reporters_counts")
        self.assertEqual(backfill_activities_schemes.name, "contacts.backfill_activities_schemes")
        self.assertEqual(backfill_results_schemes.name, "contacts.backfill_results_schemes")

    def test_maintenance_jobs_run_on_the_slow_queue(self):
        self.assertEqual(rebuild_reporters_counts.queue, QUEUE)
        self.assertEqual(backfill_activities_schemes.queue, QUEUE)
        self.assertEqual(backfill_results_schemes.queue, QUEUE)


class StaleRunTest(MaintenanceTest):
    def test_stale_run_is_nudged_again(self):
        job = SyncJob.get_or_create_job(self.nigeria, REBUILD_JOB_TYPE)
        job.claim("worker-1")
        job.release_lease()

        # between chunks with a continuation on its way - leave it be
        with patch.object(rebuild_reporters_counts, "apply_async") as mock_enqueue:
            rebuild_contacts_counts(org_id=self.nigeria.id)

        mock_enqueue.assert_not_called()

        # a run that stopped checkpointing entirely lost its continuation, so nudge it
        make_stale(job, seconds_ago=2 * LEASE_SECONDS + 60)

        with patch.object(rebuild_reporters_counts, "apply_async") as mock_enqueue:
            rebuild_contacts_counts(org_id=self.nigeria.id)

        mock_enqueue.assert_called_once_with((job.id,), queue=QUEUE)
