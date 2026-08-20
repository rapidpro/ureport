# -*- coding: utf-8 -*-

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

from smartmin.views import SmartCRUDL, SmartListView, SmartUpdateView
from ureport.syncjobs.models import SyncJob


class SyncJobCRUDL(SmartCRUDL):
    model = SyncJob
    actions = ("list", "pause", "resume", "force_resync")

    class List(SmartListView):
        """
        Every org's jobs, not just the current one - these are operational controls, and
        the permission is granted to no group, so only superusers reach them.
        """

        fields = ("org", "job_type", "scope", "status", "progress", "lease_expires_on", "failures", "modified_on")
        default_order = ("-modified_on",)
        search_fields = ("scope__icontains", "org__name__icontains", "org__subdomain__icontains")
        select_related = ("org",)
        paginate_by = 50

        def derive_queryset(self, **kwargs):
            queryset = super().derive_queryset(**kwargs)

            job_type = self.request.GET.get("job_type")
            if job_type:
                queryset = queryset.filter(job_type=job_type)

            status = self.request.GET.get("status")
            if status:
                queryset = queryset.filter(status=status)

            return queryset

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            context["report"] = SyncJob.get_status_report()
            context["job_types"] = SyncJob.objects.order_by("job_type").values_list("job_type", flat=True).distinct()
            context["statuses"] = SyncJob.STATUS_CHOICES
            context["filter_job_type"] = self.request.GET.get("job_type", "")
            context["filter_status"] = self.request.GET.get("status", "")
            return context

        def get_org(self, obj):
            return obj.org.name if obj.org else "-"

        def get_scope(self, obj):
            return obj.scope or "-"

        def get_status(self, obj):
            return obj.get_status_display()

        def get_progress(self, obj):
            return obj.progress_summary or "-"

        def get_failures(self, obj):
            return obj.consecutive_failures

    class Action(SmartUpdateView):
        """
        A single job control. Applied one row at a time and only ever through the model's
        guarded updates, so an operator can't overwrite a job a worker is still running.
        """

        fields = ()
        http_method_names = ["post"]
        success_url = "@syncjobs.syncjob_list"
        refused_message = _("Job #%(job_id)d is being worked on, try again in a moment")

        def apply(self, job):  # pragma: no cover
            raise NotImplementedError

        def form_valid(self, form):
            job = self.get_object()

            if self.apply(job):
                messages.success(self.request, self.applied_message % dict(job_id=job.id))
            else:
                messages.warning(self.request, self.refused_message % dict(job_id=job.id))

            return HttpResponseRedirect(self.get_success_url())

    class Pause(Action):
        applied_message = _("Paused job #%(job_id)d")

        def apply(self, job):
            return job.pause()

    class Resume(Action):
        applied_message = _("Resumed job #%(job_id)d")
        refused_message = _("Job #%(job_id)d isn't paused")

        def apply(self, job):
            return job.resume()

    class ForceResync(Action):
        applied_message = _("Job #%(job_id)d will resync from scratch on its next run")

        def apply(self, job):
            return job.force_resync()
