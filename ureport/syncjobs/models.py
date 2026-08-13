import logging
from datetime import timedelta

from django.db import models
from django.db.models import Case, F, Q, Value, When
from django.utils import timezone

from dash.orgs.models import Org

logger = logging.getLogger(__name__)

DEFAULT_LEASE_SECONDS = 60 * 10

MAX_ERROR_LENGTH = 10_000


class LeaseLost(Exception):
    """
    Raised when a checkpoint is attempted after this worker's lease on the job has been
    taken over or released - the chunk must abort without writing further progress.
    """


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
