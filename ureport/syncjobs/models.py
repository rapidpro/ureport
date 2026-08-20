import logging
from collections import defaultdict
from datetime import timedelta

from django.core.cache import cache
from django.db import models
from django.db.models import Case, Count, F, Q, Value, When
from django.utils import timezone

from dash.orgs.models import Org

logger = logging.getLogger(__name__)

DEFAULT_LEASE_SECONDS = 60 * 10

MAX_ERROR_LENGTH = 10_000

MAX_ERROR_SUMMARY_LENGTH = 200

# how long after a lease expires a still running job is considered abandoned rather than
# in the middle of a takeover by the redelivery of its own chunk
DEFAULT_STALE_GRACE_SECONDS = 60 * 10

DEFAULT_FAILING_THRESHOLD = 3

# where the monitor task leaves its findings for the status page
STATUS_CACHE_KEY = "syncjobs_status"


class LeaseLost(Exception):
    """
    Raised when a checkpoint is attempted after this worker's lease on the job has been
    taken over or released - the chunk must abort without writing further progress.
    """


class SyncJobQuerySet(models.QuerySet):
    def stale(self, grace_seconds=DEFAULT_STALE_GRACE_SECONDS):
        """
        Runs that nothing is moving forward anymore: a worker died holding the lease and
        no redelivery took it over, or the continuation of a released chunk was never
        delivered. Either way the job sits mid run until an operator or a trigger revives
        it, so it only counts as stale once past the grace an ordinary handover needs.
        """
        cutoff = timezone.now() - timedelta(seconds=grace_seconds)

        return self.filter(status=SyncJob.STATUS_RUNNING).filter(
            Q(lease_expires_on__lt=cutoff) | Q(lease_expires_on__isnull=True, modified_on__lt=cutoff)
        )

    def failing(self, threshold=DEFAULT_FAILING_THRESHOLD):
        """
        Jobs whose retries keep failing, i.e. the failure isn't the transient kind that
        resuming from the last checkpoint fixes. Paused jobs are deliberately stopped, so
        they don't keep reporting the failure that led to the pause.
        """
        return self.filter(consecutive_failures__gte=threshold).exclude(status=SyncJob.STATUS_PAUSED)


class SyncJob(models.Model):
    """
    A resumable unit of background work, e.g. pulling results for one flow or contacts for
    one backend. Progress is checkpointed in the cursor field so that a killed worker only
    loses the chunk it was working on, and a short self-expiring lease replaces long fixed
    timeout locks. Rows are long lived and reused: for incremental syncs COMPLETE means
    caught up, and the cursor carries forward into the next run.
    """

    STATUS_PENDING = "P"
    STATUS_RUNNING = "R"
    STATUS_COMPLETE = "C"
    STATUS_FAILED = "F"
    STATUS_PAUSED = "X"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETE, "Complete"),
        (STATUS_FAILED, "Failed"),
        (STATUS_PAUSED, "Paused"),
    )

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="sync_jobs", null=True)

    job_type = models.CharField(max_length=64)

    # identifies the entity within the org, e.g. a flow UUID or a backend slug
    scope = models.CharField(max_length=64, default="", blank=True)

    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # opaque task defined resume position, e.g. {"after": "2026-08-11T09:14:03Z"}
    cursor = models.JSONField(default=dict, blank=True)

    lease_owner = models.CharField(max_length=255, null=True)
    lease_expires_on = models.DateTimeField(null=True)

    started_on = models.DateTimeField(null=True)
    ended_on = models.DateTimeField(null=True)

    # running counters for the current run, e.g. {"chunks": 3, "created": 2500}
    progress = models.JSONField(default=dict, blank=True)

    # set when work completed but completion hooks haven't run yet, so that finalization
    # is retried if the worker dies between completing and finalizing
    needs_finalize = models.BooleanField(default=False)

    consecutive_failures = models.IntegerField(default=0)
    last_error = models.TextField(default="", blank=True)

    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    objects = SyncJobQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "job_type", "scope"], name="syncjobs_unique_job", nulls_distinct=False
            )
        ]
        indexes = [models.Index(fields=["job_type", "status"], name="syncjobs_by_type_status")]

    @classmethod
    def get_or_create_job(cls, org, job_type, scope=""):
        job, _ = cls.objects.get_or_create(org=org, job_type=job_type, scope=scope)
        return job

    def claim(self, owner, lease_seconds=DEFAULT_LEASE_SECONDS):
        """
        Attempts to take this job's lease with a single atomic conditional update. The gate
        is purely the lease: a null lease (never started, released between chunks, or
        released by completion/failure) or an expired lease (worker died) is claimable, a
        live lease is not - including the lease deliberately held through finalization.
        Claiming a job whose previous run finished (or never started) begins a new run;
        claiming a running or failed job resumes the interrupted run. Returns the refreshed
        job if the claim succeeded, None otherwise.
        """
        now = timezone.now()
        resuming = Q(status__in=(self.STATUS_RUNNING, self.STATUS_FAILED))

        updated = (
            SyncJob.objects.filter(id=self.id)
            .exclude(status=self.STATUS_PAUSED)
            .filter(Q(lease_expires_on__lt=now) | Q(lease_expires_on__isnull=True))
            .update(
                status=self.STATUS_RUNNING,
                lease_owner=owner,
                lease_expires_on=now + timedelta(seconds=lease_seconds),
                started_on=Case(When(resuming, then=F("started_on")), default=Value(now)),
                progress=Case(
                    When(resuming, then=F("progress")),
                    default=Value({}, output_field=models.JSONField()),
                ),
                ended_on=None,
                modified_on=now,
            )
        )
        if not updated:
            return None

        self.refresh_from_db()
        return self

    def checkpoint(self, cursor=None, progress=None, lease_seconds=DEFAULT_LEASE_SECONDS):
        """
        Persists the job's resume position and renews its lease. When the chunk's data
        writes are transactional, call this inside the same transaction so the cursor can
        never run ahead of or behind the data; chunks whose writes autocommit must instead
        make them idempotent under replay from the previous cursor. Raises LeaseLost if
        this worker no longer owns the job.
        """
        if not self.lease_owner:
            raise LeaseLost(f"no lease held on job #{self.id} ({self.job_type}:{self.scope})")

        now = timezone.now()
        updates = dict(lease_expires_on=now + timedelta(seconds=lease_seconds), modified_on=now)
        if cursor is not None:
            updates["cursor"] = cursor
        if progress is not None:
            updates["progress"] = progress

        updated = SyncJob.objects.filter(id=self.id, status=self.STATUS_RUNNING, lease_owner=self.lease_owner).update(
            **updates
        )
        if not updated:
            raise LeaseLost(f"lost lease on job #{self.id} ({self.job_type}:{self.scope})")

        for field, value in updates.items():
            setattr(self, field, value)

    def add_progress(self, **counts):
        """
        Returns this job's progress with the given counters added in, for passing to
        checkpoint(). Does not write anything itself.
        """
        progress = dict(self.progress)
        for key, value in counts.items():
            progress[key] = progress.get(key, 0) + value
        return progress

    def mark_complete(self, needs_finalize=False):
        """
        Marks the current run finished. The lease is intentionally kept so that finalization
        runs without another claimant starting a new run - release_lease() when done.
        Returns False if this worker no longer owns the job, in which case the caller must
        not finalize - the new holder owns that.
        """
        now = timezone.now()
        return self._update_owned(
            status=self.STATUS_COMPLETE,
            ended_on=now,
            needs_finalize=needs_finalize,
            consecutive_failures=0,
            last_error="",
            modified_on=now,
        )

    def clear_finalize(self):
        return self._update_owned(needs_finalize=False, modified_on=timezone.now())

    def release_lease(self):
        return self._update_owned(lease_owner=None, lease_expires_on=None, modified_on=timezone.now())

    def record_failure(self, error):
        """
        Marks the current run failed and releases the lease so the next trigger can retry.
        The cursor is left as its last checkpoint so the retry resumes rather than restarts.
        """
        now = timezone.now()
        return self._update_owned(
            status=self.STATUS_FAILED,
            ended_on=now,
            consecutive_failures=F("consecutive_failures") + 1,
            last_error=str(error)[:MAX_ERROR_LENGTH],
            lease_owner=None,
            lease_expires_on=None,
            modified_on=now,
        )

    @property
    def error_summary(self):
        # a traceback's last line is the exception itself, which is the part worth showing
        lines = [line for line in self.last_error.splitlines() if line.strip()]
        return lines[-1].strip()[:MAX_ERROR_SUMMARY_LENGTH] if lines else ""

    @property
    def progress_summary(self):
        return ", ".join(f"{key}={value}" for key, value in sorted(self.progress.items()))

    def as_status(self, now=None):
        """
        The compact form of this job used by the monitor task. Only ever rendered to
        authenticated staff - it carries error text and scopes.
        """
        now = now or timezone.now()
        expired_for = (now - self.lease_expires_on).total_seconds() if self.lease_expires_on else None

        return dict(
            id=self.id,
            org=self.org_id,
            job_type=self.job_type,
            scope=self.scope,
            status=self.get_status_display(),
            consecutive_failures=self.consecutive_failures,
            last_error=self.error_summary,
            lease_expires_on=self.lease_expires_on.isoformat() if self.lease_expires_on else None,
            stale_for=int(expired_for) if expired_for and expired_for > 0 else None,
            progress=self.progress,
        )

    @classmethod
    def count_by_type(cls):
        status_names = dict(cls.STATUS_CHOICES)
        by_type = defaultdict(dict)

        for row in cls.objects.values("job_type", "status").annotate(count=Count("id")):
            by_type[row["job_type"]][status_names[row["status"]]] = row["count"]

        return dict(by_type)

    @classmethod
    def get_status_report(cls):
        """
        Everything the monitor task last recorded, with the detail entries in it. Read only
        from the cache - the status endpoints are polled and mustn't scan the jobs table.
        """
        cached = cache.get(STATUS_CACHE_KEY) or dict()

        return dict(
            by_type=cached.get("by_type", dict()),
            stale_jobs=cached.get("stale_jobs", dict()),
            failing_jobs=cached.get("failing_jobs", dict()),
            totals=cached.get("totals", dict(running=0, stale=0, failing=0)),
            checked_on=cached.get("checked_on"),
        )

    @classmethod
    def get_status_counts(cls):
        """
        The public form of the report - counts only, no scopes, org ids or error text.
        """
        report = cls.get_status_report()

        return dict(**report["totals"], checked_on=report["checked_on"])

    def pause(self):
        """
        Stops the job being claimed again, from the next chunk onwards. Refused while a
        lease is live: the holder is mid chunk and its own completion writes would race
        this one. The lease is cleared as part of pausing, because a worker whose lease
        merely lapsed is still alive and its ownership guarded writes would otherwise land
        on the paused row and take it out of the paused state. Returns whether it paused.
        """
        return self._update_unleased(status=self.STATUS_PAUSED, lease_owner=None, lease_expires_on=None)

    def resume(self):
        """
        Returns a paused job to the pool. A job paused mid run goes back to the between
        chunks state - running with no lease - so that the next claim resumes it instead of
        starting a run that would discard its progress. The job is only picked up when its
        type is next triggered, this doesn't enqueue anything itself. Returns whether it
        was resumed.
        """
        self.refresh_from_db()

        # a run that never ended is still in flight, whatever the pause made the status
        in_flight = self.started_on is not None and self.ended_on is None
        now = timezone.now()

        updated = SyncJob.objects.filter(id=self.id, status=self.STATUS_PAUSED).update(
            status=self.STATUS_RUNNING if in_flight else self.STATUS_PENDING,
            lease_owner=None,
            lease_expires_on=None,
            modified_on=now,
        )
        if not updated:
            logger.warning("Job #%d (%s:%s) not paused, resume skipped", self.id, self.job_type, self.scope)
            return False

        self.refresh_from_db()
        return True

    def force_resync(self):
        """
        Discards the job's resume position so the next run starts from scratch, e.g. after
        a backend correction that the incremental cursor would skip over. The failure
        counters are left alone so a job that keeps failing stays visible until a run
        actually completes. Refused while a lease is live. Returns whether it was reset.
        """
        return self._update_unleased(
            status=self.STATUS_PENDING,
            cursor={},
            progress={},
            needs_finalize=False,
            started_on=None,
            ended_on=None,
            lease_owner=None,
            lease_expires_on=None,
        )

    def _update_unleased(self, **updates):
        """
        Applies an operator update only while no worker holds a live lease, so manual
        intervention can never clobber a chunk that is still running.
        """
        now = timezone.now()

        updated = (
            SyncJob.objects.filter(id=self.id)
            .filter(Q(lease_expires_on__lt=now) | Q(lease_expires_on__isnull=True))
            .update(modified_on=now, **updates)
        )
        if not updated:
            logger.warning("Job #%d (%s:%s) is leased, update skipped", self.id, self.job_type, self.scope)
            return False

        self.refresh_from_db()
        return True

    def _update_owned(self, **updates):
        """
        Applies updates only while this worker still owns the lease, so a worker that lost
        its lease can't clobber the job. Returns whether the update was applied.
        """
        # a None owner would match any unowned row, which is not ownership
        if not self.lease_owner:
            logger.warning("Job #%d (%s:%s) not owned, update skipped", self.id, self.job_type, self.scope)
            return False

        updated = SyncJob.objects.filter(id=self.id, lease_owner=self.lease_owner).update(**updates)
        if updated:
            self.refresh_from_db()
            return True

        logger.warning("Job #%d (%s:%s) no longer owned, update skipped", self.id, self.job_type, self.scope)
        return False

    def __str__(self):
        return f"{self.job_type}:{self.scope or '*'} org={self.org_id or '*'} [{self.get_status_display()}]"
