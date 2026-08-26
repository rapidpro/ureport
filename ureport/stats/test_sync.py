# -*- coding: utf-8 -*-

from datetime import timedelta
from unittest.mock import call, patch

from django.conf import settings
from django.utils import timezone

from dash.orgs.models import TaskState
from ureport.stats.models import ContactActivity
from ureport.stats.sync import (
    DAILY_INTERVAL,
    ENGAGEMENT_BATCH_SIZE,
    ENGAGEMENT_JOB_TYPE,
    LOCK_BACKOFF,
    PRUNE_JOB_TYPE,
    REBUILD_BATCH_SIZE,
    REBUILD_JOB_TYPE,
    REBUILD_LOCK_KEY,
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
from ureport.syncjobs.models import ABORTED, SyncJob
from ureport.syncjobs.testing import SyncJobTestMixin, end_run, held_lock, make_stale, reload, run_task
from ureport.tests import UreportTest

REFRESH_ENGAGEMENT_DATA = "ureport.stats.models.PollEngagementDailyCount.refresh_engagement_data"
CALCULATE_RESPONSE_RATE = "ureport.stats.models.PollStatsCounter.calculate_average_response_rate"
RECALCULATE_COUNTS = "ureport.stats.models.ContactActivity.recalculate_contact_activity_counts"


class RefreshEngagementTest(SyncJobTestMixin, UreportTest):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(self.nigeria, ENGAGEMENT_JOB_TYPE)

        self.mock_refresh = self.start_patch(patch(REFRESH_ENGAGEMENT_DATA))
        self.mock_response_rate = self.start_patch(patch(CALCULATE_RESPONSE_RATE))

    def test_combos_refreshed_a_batch_at_a_time(self):
        combos = engagement_combos()
        self.assertEqual(len(combos), 60)

        mock_continue = run_task(refresh_engagement, self.job.id)

        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_RUNNING,
            cursor={"combo_index": ENGAGEMENT_BATCH_SIZE, "combo_count": len(combos)},
            progress={"chunks": 1, "combos": ENGAGEMENT_BATCH_SIZE},
        )
        mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=None)

        # the metric leads the call, the cursor position doesn't
        self.assertEqual(
            self.mock_refresh.call_args_list,
            [call(self.nigeria, metric, segment, time_filter) for time_filter, segment, metric in combos[:3]],
        )

        # the response rate is only derived once the whole product has been refreshed
        self.mock_response_rate.assert_not_called()

        chunks_left = len(combos) // ENGAGEMENT_BATCH_SIZE - 1
        run_task(refresh_engagement, self.job.id, times=chunks_left)

        # the finished run leaves nothing to resume from, so the next run refreshes it all again
        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_COMPLETE,
            progress={"chunks": chunks_left + 1, "combos": len(combos)},
            cursor={},
            needs_finalize=False,
        )
        self.assertEqual(self.mock_refresh.call_count, len(combos))
        self.mock_response_rate.assert_called_once_with(self.nigeria)

        run_task(refresh_engagement, self.job.id)

        self.assertJobState(self.job, cursor={"combo_index": ENGAGEMENT_BATCH_SIZE, "combo_count": len(combos)})
        self.assertEqual(self.mock_refresh.call_args_list[-3:], self.mock_refresh.call_args_list[:3])

    def test_resumes_mid_list(self):
        combos = engagement_combos()
        SyncJob.objects.filter(id=self.job.id).update(
            cursor={"combo_index": len(combos) - 2, "combo_count": len(combos)}
        )

        run_task(refresh_engagement, self.job.id)

        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={}, progress={"chunks": 1, "combos": 2})
        self.assertEqual(
            self.mock_refresh.call_args_list,
            [call(self.nigeria, metric, segment, time_filter) for time_filter, segment, metric in combos[-2:]],
        )

    def test_cursor_past_the_end_completes(self):
        combos = engagement_combos()
        SyncJob.objects.filter(id=self.job.id).update(cursor={"combo_index": 500, "combo_count": len(combos)})

        run_task(refresh_engagement, self.job.id)

        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={})
        self.mock_refresh.assert_not_called()

    def test_changed_combo_list_restarts_the_pass(self):
        # a release that adds or drops a metric or segment leaves the position pointing at
        # different combinations than it was taken against
        run_task(refresh_engagement, self.job.id, times=2)
        shorter = engagement_combos()[:30]

        with patch("ureport.stats.sync.engagement_combos", return_value=shorter):
            run_task(refresh_engagement, self.job.id)

        self.assertJobState(self.job, cursor={"combo_index": ENGAGEMENT_BATCH_SIZE, "combo_count": len(shorter)})

        # the pass starts over rather than skipping the tail the stale position would miss
        self.assertEqual(self.mock_refresh.call_args_list[6:], self.mock_refresh.call_args_list[:3])

    def test_failed_chunk_resumes_from_its_last_position(self):
        combos = engagement_combos()
        run_task(refresh_engagement, self.job.id, times=2)
        self.mock_refresh.side_effect = ValueError("boom")

        with self.assertRaises(ValueError):
            run_task(refresh_engagement, self.job.id)

        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_FAILED,
            consecutive_failures=1,
            cursor={"combo_index": 2 * ENGAGEMENT_BATCH_SIZE, "combo_count": len(combos)},
        )

        self.mock_refresh.side_effect = None
        run_task(refresh_engagement, self.job.id)

        self.assertJobState(self.job, cursor={"combo_index": 3 * ENGAGEMENT_BATCH_SIZE, "combo_count": len(combos)})

    def test_deactivated_org_aborts_the_run(self):
        run_task(refresh_engagement, self.job.id)

        self.nigeria.is_active = False
        self.nigeria.save(update_fields=("is_active",))

        run_task(refresh_engagement, self.job.id)

        job = self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={})
        self.assertEqual(job.progress[ABORTED], 1)
        self.assertEqual(self.mock_refresh.call_count, ENGAGEMENT_BATCH_SIZE)

        # a run that refreshed only part of the data doesn't get to publish a response rate
        self.mock_response_rate.assert_not_called()

    def test_disabling_the_refresh_mid_run_aborts_it(self):
        run_task(refresh_engagement, self.job.id)

        TaskState.objects.create(org=self.nigeria, task_key="refresh-engagement-data", is_disabled=True)

        # the kill switch lands on the run in flight, not just on the next enqueue
        run_task(refresh_engagement, self.job.id)

        job = self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, cursor={})
        self.assertEqual(job.progress[ABORTED], 1)
        self.assertEqual(self.mock_refresh.call_count, ENGAGEMENT_BATCH_SIZE)
        self.mock_response_rate.assert_not_called()

    def test_finalize_is_idempotent(self):
        job = reload(self.job)

        finalize_engagement_refresh(job)
        finalize_engagement_refresh(job)

        self.assertEqual(self.mock_response_rate.call_args_list, [call(self.nigeria), call(self.nigeria)])


class PruneContactActivitiesTest(SyncJobTestMixin, UreportTest):
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
            mock_continue = run_task(prune_contact_activities, self.job.id)

            self.assertJobState(self.job, status=SyncJob.STATUS_RUNNING, progress={"chunks": 1, "deleted": 4})
            mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=None)

            # the chunk that runs out of expired activities is the one that finishes the run
            run_task(prune_contact_activities, self.job.id)

        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, progress={"chunks": 2, "deleted": 5})

        # only the expired activities of this org went
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria).count(), 2)
        self.assertEqual(ContactActivity.objects.filter(org=self.uganda).count(), 3)

    def test_run_with_nothing_to_prune_completes(self):
        self._create_activities(self.nigeria, 2, days_old=10)

        mock_continue = run_task(prune_contact_activities, self.job.id)

        self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE, progress={"chunks": 1, "deleted": 0}, cursor={})
        mock_continue.assert_not_called()

        # and re-running is harmless - the deletion is its own resume position
        run_task(prune_contact_activities, self.job.id)

        self.assertJobState(self.job, progress={"chunks": 1, "deleted": 0})
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria).count(), 2)

    def test_deactivated_org_aborts_the_run(self):
        self._create_activities(self.nigeria, 2, days_old=401)
        self.nigeria.is_active = False
        self.nigeria.save(update_fields=("is_active",))

        run_task(prune_contact_activities, self.job.id)

        job = self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress[ABORTED], 1)
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria).count(), 2)

    def test_disabling_the_prune_mid_run_aborts_it(self):
        self._create_activities(self.nigeria, 4, days_old=401)

        with patch("ureport.stats.sync.PRUNE_BATCH_SIZE", 1), patch("ureport.stats.sync.PRUNE_BATCHES_PER_CHUNK", 1):
            run_task(prune_contact_activities, self.job.id)

            TaskState.objects.create(org=self.nigeria, task_key="delete-old-contact-activities", is_disabled=True)

            run_task(prune_contact_activities, self.job.id)

        job = self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress[ABORTED], 1)
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria).count(), 3)


class RebuildContactActivityCountsTest(SyncJobTestMixin, UreportTest):
    def setUp(self):
        super().setUp()

        self.job = SyncJob.get_or_create_job(self.nigeria, REBUILD_JOB_TYPE)

        self.mock_refresh = self.start_patch(patch(REFRESH_ENGAGEMENT_DATA))

    @patch(RECALCULATE_COUNTS)
    def test_counters_are_rebuilt_before_what_they_feed(self, mock_recalculate):
        mock_recalculate.return_value = {("a",): 1, ("b",): 2}
        combos = rebuild_combos()
        self.assertEqual(len(combos), 15)

        # the counter rebuild is a chunk of its own
        mock_continue = run_task(rebuild_contact_activity_counts, self.job.id)

        self.assertJobState(
            self.job,
            cursor={"stage": "engagement", "combo_index": 0, "combo_count": len(combos)},
            progress={"chunks": 1, "counters": 2},
        )
        mock_recalculate.assert_called_once_with(self.nigeria)
        self.mock_refresh.assert_not_called()
        mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=None)

        # then the engagement data it feeds, a batch at a time
        run_task(rebuild_contact_activity_counts, self.job.id)

        self.assertJobState(
            self.job,
            cursor={"stage": "engagement", "combo_index": REBUILD_BATCH_SIZE, "combo_count": len(combos)},
            progress={"chunks": 2, "counters": 2, "combos": REBUILD_BATCH_SIZE},
        )
        self.assertEqual(
            self.mock_refresh.call_args_list,
            [call(self.nigeria, REBUILD_METRIC, segment, time_filter) for time_filter, segment in combos[:5]],
        )

        run_task(rebuild_contact_activity_counts, self.job.id, times=len(combos) // REBUILD_BATCH_SIZE - 1)

        self.assertJobState(
            self.job,
            status=SyncJob.STATUS_COMPLETE,
            cursor={},
            progress={"chunks": 4, "counters": 2, "combos": len(combos)},
        )
        self.assertEqual(self.mock_refresh.call_count, len(combos))

        # the counters are only recalculated once per run, and a new run starts over
        self.assertEqual(mock_recalculate.call_count, 1)

        run_task(rebuild_contact_activity_counts, self.job.id)

        self.assertEqual(mock_recalculate.call_count, 2)
        self.assertJobState(self.job, cursor={"stage": "engagement", "combo_index": 0, "combo_count": len(combos)})

    @patch(RECALCULATE_COUNTS)
    def test_backs_off_while_another_worker_rebuilds(self, mock_recalculate):
        # two recalculations at once would double the org's counters rather than replace
        # them, so a chunk that can't have the lock waits instead of running anyway
        with held_lock(TaskState.get_lock_key(self.nigeria, REBUILD_LOCK_KEY)):
            mock_continue = run_task(rebuild_contact_activity_counts, self.job.id)

        mock_recalculate.assert_not_called()
        mock_continue.assert_called_once_with((self.job.id,), queue="slow", countdown=LOCK_BACKOFF)

        self.assertJobState(self.job, status=SyncJob.STATUS_RUNNING, cursor={}, progress={"lock_backoffs": 1})

        # and picks the rebuild up once the lock is free again
        run_task(rebuild_contact_activity_counts, self.job.id)

        mock_recalculate.assert_called_once_with(self.nigeria)
        self.assertEqual(reload(self.job).cursor["stage"], "engagement")

    def test_rebuild_recalculates_the_orgs_counters(self):
        ContactActivity.objects.create(
            org=self.nigeria, contact="contact-1", date=timezone.now().date(), gender="M", born=1990
        )

        run_task(rebuild_contact_activity_counts, self.job.id)

        self.assertJobState(self.job, progress={"chunks": 1, "counters": 3})

    @patch(RECALCULATE_COUNTS)
    def test_deactivated_org_aborts_the_run(self, mock_recalculate):
        self.nigeria.is_active = False
        self.nigeria.save(update_fields=("is_active",))

        run_task(rebuild_contact_activity_counts, self.job.id)

        job = self.assertJobState(self.job, status=SyncJob.STATUS_COMPLETE)
        self.assertEqual(job.progress[ABORTED], 1)
        mock_recalculate.assert_not_called()


class DispatchTest(SyncJobTestMixin, UreportTest):
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

    def _end_run(self, job, ago, ran_for=timedelta(0), failures=0):
        """
        Leaves the job as a whole run - started and ended - that finished that long ago,
        which is the state the cadence and the failure backoff are read from. modified_on
        is moved back with it so the run doesn't also look freshly nudged.
        """
        ended_on = timezone.now() - ago

        return end_run(
            job,
            status=SyncJob.STATUS_FAILED if failures else SyncJob.STATUS_COMPLETE,
            started_on=ended_on - ran_for,
            ended_on=ended_on,
            failures=failures,
            lease_owner=None,
            lease_expires_on=None,
            modified_on=ended_on,
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

    def test_pending_jobs_are_only_enqueued_once(self):
        mock_engagement, mock_prune = self._dispatch()

        self.assertEqual(mock_engagement.call_count, 1)
        self.assertEqual(mock_prune.call_count, 1)

        # the messages are queued but nothing has claimed them yet, so the jobs are still
        # pending - nudging them again would only duplicate the messages, and a surplus one
        # landing after the run completes starts a whole fresh pass
        engagement = self._job(ENGAGEMENT_JOB_TYPE)
        self.assertEqual(engagement.status, SyncJob.STATUS_PENDING)

        mock_engagement, mock_prune = self._dispatch()

        mock_engagement.assert_not_called()
        mock_prune.assert_not_called()

        # a message the broker genuinely lost is picked back up once nothing has moved for
        # long enough
        make_stale(engagement, seconds_ago=2 * 60 * 60)

        mock_engagement, _ = self._dispatch()

        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

    def test_a_due_job_is_only_enqueued_once(self):
        self._dispatch()
        engagement = self._job(ENGAGEMENT_JOB_TYPE)

        self._end_run(engagement, ago=DAILY_INTERVAL + timedelta(hours=1))

        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

        # the run it queued hasn't been picked up yet, so the job still looks finished and
        # stale - the nudge is what stops the next pass queueing a second one
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_not_called()

        # unless nothing came of it, in which case it is queued afresh
        make_stale(engagement, seconds_ago=2 * 60 * 60)

        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

    def test_an_explicit_trigger_defers_only_to_a_run_in_flight(self):
        self._dispatch()
        engagement = self._job(ENGAGEMENT_JOB_TYPE)
        self._end_run(engagement, ago=timedelta(minutes=5))

        # the cadence and the nudge are the dispatcher's business - asking for a refresh
        # directly gets one, as long as no run is actually being worked on
        with patch.object(refresh_engagement, "apply_async") as mock_enqueue:
            refresh_engagement_data(self.nigeria.id)
            refresh_engagement_data(self.nigeria.id)

        self.assertEqual(mock_enqueue.call_count, 2)

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

    def test_cadence_is_measured_from_when_the_run_started(self):
        self._dispatch()
        engagement = self._job(ENGAGEMENT_JOB_TYPE)

        # the cadence is how often a run should start, so a long run doesn't push the next
        # one out by its own duration - this one ended an hour ago but started a day before
        self._end_run(engagement, ago=timedelta(hours=1), ran_for=DAILY_INTERVAL)

        mock_engagement, _ = self._dispatch()

        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

    def test_failures_back_off_beyond_the_daily_cadence(self):
        self._dispatch()
        engagement = self._job(ENGAGEMENT_JOB_TYPE)

        # a single failure is retried at the normal cadence
        self._end_run(engagement, ago=DAILY_INTERVAL + timedelta(hours=1), failures=1)
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

        # a streak of them earns a wait longer than a night: 20h, 40h, 80h, 160h
        self._end_run(engagement, ago=timedelta(hours=25), failures=3)
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_not_called()

        self._end_run(engagement, ago=timedelta(hours=81), failures=3)
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

        # but never longer than the cap
        self._end_run(engagement, ago=timedelta(days=6), failures=50)
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_not_called()

        self._end_run(engagement, ago=timedelta(days=8), failures=50)
        mock_engagement, _ = self._dispatch()
        mock_engagement.assert_called_once_with((engagement.id,), queue="slow")

    def test_a_failure_backoff_is_measured_from_when_the_run_failed(self):
        self._dispatch()
        engagement = self._job(ENGAGEMENT_JOB_TYPE)

        # unlike the cadence, the backoff is a wait after the failure - a run that took a
        # day to fail doesn't get retried the moment it does
        self._end_run(engagement, ago=timedelta(hours=1), ran_for=DAILY_INTERVAL, failures=1)

        mock_engagement, _ = self._dispatch()

        mock_engagement.assert_not_called()

    def test_skips_paused_jobs(self):
        self._dispatch()
        engagement = self._job(ENGAGEMENT_JOB_TYPE)
        self.assertTrue(engagement.pause())

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
        make_stale(engagement, seconds_ago=2 * 60 * 60)

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

    def test_beat_runs_the_dispatcher(self):
        # nothing else nudges these jobs, so a beat entry pointing at a name that no longer
        # exists would simply stop the stats refreshing
        entry = settings.CELERY_BEAT_SCHEDULE["stats-dispatch"]
        self.assertEqual(entry["task"], stats_dispatch.name)
        self.assertEqual(entry["options"], {"queue": "slow"})


class ShimsTest(SyncJobTestMixin, UreportTest):
    def test_registered_task_names(self):
        # the names messages already on the queue and existing triggers resolve by - renaming
        # any of these silently drops that work on the floor
        self.assertEqual(refresh_engagement_data.name, "ureport.stats.tasks.refresh_engagement_data")
        self.assertEqual(delete_old_contact_activities.name, "ureport.stats.tasks.delete_old_contact_activities")
        self.assertEqual(rebuild_contacts_activities_counts.name, "stats.rebuild_contacts_activities_counts")

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
