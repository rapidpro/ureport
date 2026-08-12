# -*- coding: utf-8 -*-

from datetime import timedelta
from unittest.mock import call, patch

from django.utils import timezone

from dash.orgs.models import TaskState
from ureport.stats.models import ContactActivity
from ureport.stats.sync import (
    DAILY_INTERVAL,
    ENGAGEMENT_BATCH_SIZE,
    ENGAGEMENT_JOB_TYPE,
    PRUNE_JOB_TYPE,
    REBUILD_BATCH_SIZE,
    REBUILD_JOB_TYPE,
    REBUILD_METRIC,
    engagement_combos,
    finalize_engagement_refresh,
    prune_contact_activities,
    rebuild_combos,
    rebuild_contact_activity_counts,
    refresh_engagement,
    stats_dispatch,
)
from ureport.stats.tasks import (
    delete_old_contact_activities,
    rebuild_contacts_activities_counts,
    refresh_engagement_data,
)
from ureport.syncjobs.models import SyncJob
from ureport.tests import UreportTest

REFRESH_ENGAGEMENT_DATA = "ureport.stats.models.PollEngagementDailyCount.refresh_engagement_data"
CALCULATE_RESPONSE_RATE = "ureport.stats.models.PollStatsCounter.calculate_average_response_rate"
RECALCULATE_COUNTS = "ureport.stats.models.ContactActivity.recalculate_contact_activity_counts"


class ChunkTestMixin:
    def _run(self, task, job, times=1):
        """
        Runs a chunk task the given number of times, as a worker would with each
        continuation, without actually queueing anything.
        """
        with patch.object(task, "apply_async") as mock_continue:
            for _ in range(times):
                task(job.id)
        return mock_continue

    def _job(self, job):
        return SyncJob.objects.get(id=job.id)


class RefreshEngagementTest(ChunkTestMixin, UreportTest):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(self.nigeria, ENGAGEMENT_JOB_TYPE)

    @patch(CALCULATE_RESPONSE_RATE)
    @patch(REFRESH_ENGAGEMENT_DATA)
    def test_combos_refreshed_a_batch_at_a_time(self, mock_refresh, mock_response_rate):
        combos = engagement_combos()
        self.assertEqual(len(combos), 60)

        mock_continue = self._run(refresh_engagement, self.job)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_RUNNING)
        self.assertEqual(job.cursor, {"combo_index": ENGAGEMENT_BATCH_SIZE})
        self.assertEqual(job.progress, {"chunks": 1, "combos": ENGAGEMENT_BATCH_SIZE})
        mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=None)

        # the metric leads the call, the cursor position doesn't
        self.assertEqual(
            mock_refresh.call_args_list,
            [call(self.nigeria, metric, segment, time_filter) for time_filter, segment, metric in combos[:3]],
        )

        # the response rate is only derived once the whole product has been refreshed
        mock_response_rate.assert_not_called()

        chunks_left = len(combos) // ENGAGEMENT_BATCH_SIZE - 1
        self._run(refresh_engagement, self.job, times=chunks_left)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress, {"chunks": chunks_left + 1, "combos": len(combos)})
        self.assertEqual(mock_refresh.call_count, len(combos))
        mock_response_rate.assert_called_once_with(self.nigeria)

        # the finished run leaves nothing to resume from, so the next run refreshes it all again
        self.assertEqual(job.cursor, {})
        self.assertFalse(job.needs_finalize)

        self._run(refresh_engagement, self.job)

        self.assertEqual(self._job(self.job).cursor, {"combo_index": ENGAGEMENT_BATCH_SIZE})
        self.assertEqual(mock_refresh.call_args_list[-3:], mock_refresh.call_args_list[:3])

    @patch(CALCULATE_RESPONSE_RATE)
    @patch(REFRESH_ENGAGEMENT_DATA)
    def test_resumes_mid_list(self, mock_refresh, mock_response_rate):
        combos = engagement_combos()
        SyncJob.objects.filter(id=self.job.id).update(cursor={"combo_index": len(combos) - 2})

        self._run(refresh_engagement, self.job)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.cursor, {})
        self.assertEqual(job.progress, {"chunks": 1, "combos": 2})
        self.assertEqual(
            mock_refresh.call_args_list,
            [call(self.nigeria, metric, segment, time_filter) for time_filter, segment, metric in combos[-2:]],
        )

    @patch(CALCULATE_RESPONSE_RATE)
    @patch(REFRESH_ENGAGEMENT_DATA)
    def test_cursor_past_the_end_completes(self, mock_refresh, mock_response_rate):
        # e.g. a release that dropped a metric, leaving the previous run's position stranded
        SyncJob.objects.filter(id=self.job.id).update(cursor={"combo_index": 500})

        self._run(refresh_engagement, self.job)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.cursor, {})
        mock_refresh.assert_not_called()

    @patch(CALCULATE_RESPONSE_RATE)
    @patch(REFRESH_ENGAGEMENT_DATA)
    def test_failed_chunk_resumes_from_its_last_position(self, mock_refresh, mock_response_rate):
        self._run(refresh_engagement, self.job, times=2)
        mock_refresh.side_effect = ValueError("boom")

        with self.assertRaises(ValueError):
            self._run(refresh_engagement, self.job)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_FAILED)
        self.assertEqual(job.consecutive_failures, 1)
        self.assertEqual(job.cursor, {"combo_index": 2 * ENGAGEMENT_BATCH_SIZE})

        mock_refresh.side_effect = None
        self._run(refresh_engagement, self.job)

        self.assertEqual(self._job(self.job).cursor, {"combo_index": 3 * ENGAGEMENT_BATCH_SIZE})

    @patch(CALCULATE_RESPONSE_RATE)
    @patch(REFRESH_ENGAGEMENT_DATA)
    def test_deactivated_org_aborts_the_run(self, mock_refresh, mock_response_rate):
        self._run(refresh_engagement, self.job)

        self.nigeria.is_active = False
        self.nigeria.save(update_fields=("is_active",))

        self._run(refresh_engagement, self.job)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.cursor, {})
        self.assertEqual(job.progress["aborted"], 1)
        self.assertEqual(mock_refresh.call_count, ENGAGEMENT_BATCH_SIZE)

        # a run that refreshed only part of the data doesn't get to publish a response rate
        mock_response_rate.assert_not_called()

    @patch(CALCULATE_RESPONSE_RATE)
    def test_finalize_is_idempotent(self, mock_response_rate):
        job = SyncJob.objects.get(id=self.job.id)

        finalize_engagement_refresh(job)
        finalize_engagement_refresh(job)

        self.assertEqual(mock_response_rate.call_args_list, [call(self.nigeria), call(self.nigeria)])

    @patch(CALCULATE_RESPONSE_RATE)
    def test_finalize_skips_an_aborted_run(self, mock_response_rate):
        SyncJob.objects.filter(id=self.job.id).update(progress={"aborted": 1})

        finalize_engagement_refresh(SyncJob.objects.get(id=self.job.id))

        mock_response_rate.assert_not_called()


class PruneContactActivitiesTest(ChunkTestMixin, UreportTest):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(self.nigeria, PRUNE_JOB_TYPE)

    def _create_activities(self, org, count, days_old):
        date = (timezone.now() - timedelta(days=days_old)).date()
        return ContactActivity.objects.bulk_create(
            [ContactActivity(org=org, contact=f"contact-{days_old}-{i}", date=date) for i in range(count)]
        )

    def test_prunes_until_nothing_is_left(self):
        self._create_activities(self.nigeria, 5, days_old=401)
        self._create_activities(self.nigeria, 2, days_old=10)
        self._create_activities(self.uganda, 3, days_old=401)

        with patch("ureport.stats.sync.PRUNE_BATCH_SIZE", 2), patch("ureport.stats.sync.PRUNE_BATCHES_PER_CHUNK", 2):
            mock_continue = self._run(prune_contact_activities, self.job)

            job = self._job(self.job)
            self.assertEqual(job.status, SyncJob.STATUS_RUNNING)
            self.assertEqual(job.progress, {"chunks": 1, "deleted": 4})
            mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=None)

            # the chunk that runs out of expired activities is the one that finishes the run
            self._run(prune_contact_activities, self.job)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress, {"chunks": 2, "deleted": 5})

        # only the expired activities of this org went
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria).count(), 2)
        self.assertEqual(ContactActivity.objects.filter(org=self.uganda).count(), 3)

    def test_run_with_nothing_to_prune_completes(self):
        self._create_activities(self.nigeria, 2, days_old=10)

        mock_continue = self._run(prune_contact_activities, self.job)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress, {"chunks": 1, "deleted": 0})
        self.assertEqual(job.cursor, {})
        mock_continue.assert_not_called()

        # and re-running is harmless - the deletion is its own resume position
        self._run(prune_contact_activities, self.job)

        self.assertEqual(self._job(self.job).progress, {"chunks": 1, "deleted": 0})
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria).count(), 2)

    def test_deactivated_org_aborts_the_run(self):
        self._create_activities(self.nigeria, 2, days_old=401)
        self.nigeria.is_active = False
        self.nigeria.save(update_fields=("is_active",))

        self._run(prune_contact_activities, self.job)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress["aborted"], 1)
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria).count(), 2)


class RebuildContactActivityCountsTest(ChunkTestMixin, UreportTest):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(self.nigeria, REBUILD_JOB_TYPE)

    @patch(REFRESH_ENGAGEMENT_DATA)
    @patch(RECALCULATE_COUNTS)
    def test_counters_are_rebuilt_before_what_they_feed(self, mock_recalculate, mock_refresh):
        mock_recalculate.return_value = {("a",): 1, ("b",): 2}
        combos = rebuild_combos()
        self.assertEqual(len(combos), 15)

        # the counter rebuild is a chunk of its own
        mock_continue = self._run(rebuild_contact_activity_counts, self.job)

        job = self._job(self.job)
        self.assertEqual(job.cursor, {"stage": "engagement", "combo_index": 0})
        self.assertEqual(job.progress, {"chunks": 1, "counters": 2})
        mock_recalculate.assert_called_once_with(self.nigeria)
        mock_refresh.assert_not_called()
        mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=None)

        # then the engagement data it feeds, a batch at a time
        self._run(rebuild_contact_activity_counts, self.job)

        job = self._job(self.job)
        self.assertEqual(job.cursor, {"stage": "engagement", "combo_index": REBUILD_BATCH_SIZE})
        self.assertEqual(job.progress, {"chunks": 2, "counters": 2, "combos": REBUILD_BATCH_SIZE})
        self.assertEqual(
            mock_refresh.call_args_list,
            [call(self.nigeria, REBUILD_METRIC, segment, time_filter) for time_filter, segment in combos[:5]],
        )

        self._run(rebuild_contact_activity_counts, self.job, times=len(combos) // REBUILD_BATCH_SIZE - 1)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.cursor, {})
        self.assertEqual(job.progress, {"chunks": 4, "counters": 2, "combos": len(combos)})
        self.assertEqual(mock_refresh.call_count, len(combos))

        # the counters are only recalculated once per run, and a new run starts over
        self.assertEqual(mock_recalculate.call_count, 1)

        self._run(rebuild_contact_activity_counts, self.job)

        self.assertEqual(mock_recalculate.call_count, 2)
        self.assertEqual(self._job(self.job).cursor, {"stage": "engagement", "combo_index": 0})

    @patch(REFRESH_ENGAGEMENT_DATA)
    def test_rebuild_recalculates_the_orgs_counters(self, mock_refresh):
        ContactActivity.objects.create(
            org=self.nigeria, contact="contact-1", date=timezone.now().date(), gender="M", born=1990
        )

        self._run(rebuild_contact_activity_counts, self.job)

        self.assertEqual(self._job(self.job).progress, {"chunks": 1, "counters": 3})

    @patch(REFRESH_ENGAGEMENT_DATA)
    @patch(RECALCULATE_COUNTS)
    def test_deactivated_org_aborts_the_run(self, mock_recalculate, mock_refresh):
        self.nigeria.is_active = False
        self.nigeria.save(update_fields=("is_active",))

        self._run(rebuild_contact_activity_counts, self.job)

        job = self._job(self.job)
        self.assertEqual(job.status, SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress["aborted"], 1)
        mock_recalculate.assert_not_called()


class DispatchTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.uganda.is_active = False
        self.uganda.save(update_fields=("is_active",))

    def _dispatch(self):
        with (
            patch.object(refresh_engagement, "apply_async") as mock_engagement,
            patch.object(prune_contact_activities, "apply_async") as mock_prune,
        ):
            stats_dispatch()

        return mock_engagement, mock_prune

    def _job(self, job_type):
        return SyncJob.objects.get(org=self.nigeria, job_type=job_type)

    def _end_run(self, job, ago, failures=0):
        ended_on = timezone.now() - ago
        SyncJob.objects.filter(id=job.id).update(
            status=SyncJob.STATUS_FAILED if failures else SyncJob.STATUS_COMPLETE,
            lease_owner=None,
            lease_expires_on=None,
            ended_on=ended_on,
            modified_on=ended_on,
            consecutive_failures=failures,
        )

    def test_creates_and_enqueues_a_job_of_each_type_per_active_org(self):
        self.uganda.is_active = True
        self.uganda.save(update_fields=("is_active",))

        mock_engagement, mock_prune = self._dispatch()

        jobs = SyncJob.objects.filter(job_type__in=(ENGAGEMENT_JOB_TYPE, PRUNE_JOB_TYPE))
        self.assertEqual(
            {(job.org.subdomain, job.job_type) for job in jobs},
            {
                ("nigeria", ENGAGEMENT_JOB_TYPE),
                ("nigeria", PRUNE_JOB_TYPE),
                ("uganda", ENGAGEMENT_JOB_TYPE),
                ("uganda", PRUNE_JOB_TYPE),
            },
        )
        self.assertEqual(mock_engagement.call_count, 2)
        self.assertEqual(mock_prune.call_count, 2)

        # dispatching again reuses the same jobs
        self._dispatch()

        self.assertEqual(SyncJob.objects.filter(job_type__in=(ENGAGEMENT_JOB_TYPE, PRUNE_JOB_TYPE)).count(), 4)

    def test_only_due_once_a_day(self):
        self._dispatch()

        engagement = self._job(ENGAGEMENT_JOB_TYPE)
        prune = self._job(PRUNE_JOB_TYPE)

        self._end_run(engagement, ago=DAILY_INTERVAL - timedelta(hours=1))
        self._end_run(prune, ago=DAILY_INTERVAL + timedelta(hours=1))

        mock_engagement, mock_prune = self._dispatch()

        mock_engagement.assert_not_called()
        mock_prune.assert_called_once_with((prune.id,), queue="slow")

        # once the engagement run is stale enough too it goes again
        self._end_run(engagement, ago=DAILY_INTERVAL + timedelta(minutes=1))

        mock_engagement, _ = self._dispatch()

        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

    def test_failures_back_off_beyond_the_daily_cadence(self):
        self._dispatch()
        engagement = self._job(ENGAGEMENT_JOB_TYPE)

        # a single failure is retried at the normal cadence
        self._end_run(engagement, ago=DAILY_INTERVAL + timedelta(hours=1), failures=1)
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

        # a streak of them earns a wait longer than a day
        self._end_run(engagement, ago=timedelta(hours=25), failures=6)
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_not_called()

        self._end_run(engagement, ago=timedelta(hours=33), failures=6)
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

        # but never longer than the cap
        self._end_run(engagement, ago=timedelta(days=8), failures=50)
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

    def test_skips_paused_jobs(self):
        self._dispatch()
        engagement = self._job(ENGAGEMENT_JOB_TYPE)
        SyncJob.objects.filter(id=engagement.id).update(status=SyncJob.STATUS_PAUSED, ended_on=None)

        mock_engagement, _ = self._dispatch()

        mock_engagement.assert_not_called()

    def test_skips_job_types_disabled_for_the_org(self):
        TaskState.objects.create(org=self.nigeria, task_key="refresh-engagement-data", is_disabled=True)

        mock_engagement, mock_prune = self._dispatch()

        # the kill switch the pre-chunking task honored keeps the job from even existing
        self.assertFalse(SyncJob.objects.filter(org=self.nigeria, job_type=ENGAGEMENT_JOB_TYPE).exists())
        mock_engagement.assert_not_called()
        mock_prune.assert_called_once()

    def test_leaves_a_run_in_flight_alone(self):
        self._dispatch()
        engagement = self._job(ENGAGEMENT_JOB_TYPE)
        engagement.claim("worker-1", lease_seconds=600)

        # under a live lease - a chunk is being worked on
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_not_called()

        # and between chunks, where the lease is released but a continuation is on its way
        engagement.checkpoint(cursor={"combo_index": 3})
        engagement.release_lease()

        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_not_called()

        # a run that stopped checkpointing entirely lost its continuation, so nudge it
        SyncJob.objects.filter(id=engagement.id).update(modified_on=timezone.now() - timedelta(hours=2))

        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

    def test_errors_are_isolated_per_org(self):
        self.uganda.is_active = True
        self.uganda.save(update_fields=("is_active",))

        with (
            patch("ureport.stats.sync.dispatch_org_stats", side_effect=[ValueError("boom"), None]) as mock_dispatch,
            patch("ureport.stats.sync.logger") as mock_logger,
        ):
            stats_dispatch()

        self.assertEqual(mock_dispatch.call_count, 2)
        self.assertEqual(mock_logger.error.call_count, 1)

    def test_can_be_limited_to_one_org(self):
        self.uganda.is_active = True
        self.uganda.save(update_fields=("is_active",))

        with patch.object(refresh_engagement, "apply_async"), patch.object(prune_contact_activities, "apply_async"):
            stats_dispatch(org_id=self.nigeria.id)

        self.assertEqual(
            set(SyncJob.objects.values_list("org__subdomain", flat=True).distinct()),
            {"nigeria"},
        )


class ShimsTest(UreportTest):
    def test_refresh_engagement_data_enqueues_a_job(self):
        with patch.object(refresh_engagement, "apply_async") as mock_enqueue:
            result = refresh_engagement_data(self.nigeria.id)

        job = SyncJob.objects.get(org=self.nigeria, job_type=ENGAGEMENT_JOB_TYPE)
        self.assertEqual(result, job.id)
        mock_enqueue.assert_called_once_with((job.id,), queue="slow")

        # it neither runs nor claims the work, so it must not report on it either
        self.assertFalse(TaskState.objects.filter(org=self.nigeria).exists())

        # and it leaves a run that is already being worked on alone
        job.claim("worker-1", lease_seconds=600)

        with patch.object(refresh_engagement, "apply_async") as mock_enqueue:
            self.assertIsNone(refresh_engagement_data(self.nigeria.id))

        mock_enqueue.assert_not_called()

    def test_delete_old_contact_activities_enqueues_a_job(self):
        with patch.object(prune_contact_activities, "apply_async") as mock_enqueue:
            result = delete_old_contact_activities(self.nigeria.id)

        job = SyncJob.objects.get(org=self.nigeria, job_type=PRUNE_JOB_TYPE)
        self.assertEqual(result, job.id)
        mock_enqueue.assert_called_once_with((job.id,), queue="slow")
        self.assertFalse(TaskState.objects.filter(org=self.nigeria).exists())

    def test_shims_honor_the_orgs_kill_switch(self):
        TaskState.objects.create(org=self.nigeria, task_key="delete-old-contact-activities", is_disabled=True)

        with patch.object(prune_contact_activities, "apply_async") as mock_enqueue:
            self.assertIsNone(delete_old_contact_activities(self.nigeria.id))

        mock_enqueue.assert_not_called()
        self.assertFalse(SyncJob.objects.filter(org=self.nigeria, job_type=PRUNE_JOB_TYPE).exists())

    def test_rebuild_contacts_activities_counts_enqueues_every_active_org(self):
        with patch.object(rebuild_contact_activity_counts, "apply_async") as mock_enqueue:
            rebuild_contacts_activities_counts()

        jobs = SyncJob.objects.filter(job_type=REBUILD_JOB_TYPE)
        self.assertEqual({job.org.subdomain for job in jobs}, {"nigeria", "uganda"})
        self.assertEqual({call_args[0][0][0] for call_args in mock_enqueue.call_args_list}, {job.id for job in jobs})
        self.assertFalse(TaskState.objects.exists())

    def test_rebuild_contacts_activities_counts_can_be_limited_to_one_org(self):
        with patch.object(rebuild_contact_activity_counts, "apply_async") as mock_enqueue:
            rebuild_contacts_activities_counts(org_id=self.nigeria.id)

        job = SyncJob.objects.get(job_type=REBUILD_JOB_TYPE)
        self.assertEqual(job.org, self.nigeria)
        mock_enqueue.assert_called_once_with((job.id,), queue="slow")
