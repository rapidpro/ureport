from dash.orgs.views import OrgPermsMixin, OrgObjPermsMixin
from django.forms import forms
from django.utils.translation import ugettext_lazy as _
from smartmin.views import SmartTemplateView, SmartCRUDL, SmartCreateView, SmartUpdateView, SmartListView
from ureport.jobs.models import JobSource

class JobSourceCRUDL(SmartCRUDL):
    model = JobSource
    actions = ('create', 'list', 'update')

    class Create(OrgPermsMixin, SmartCreateView):
        success_url = '@jobs.jobsource_list'
        success_message = _("Your job source has been added successfully")
        fields = ('is_featured', 'title', 'source_type', 'source_url', 'widget_id')

        def pre_save(self, obj):
            obj = super(JobSourceCRUDL.Create, self).pre_save(obj)
            obj.org = self.request.org
            return obj

    class Update(OrgObjPermsMixin, SmartUpdateView):
        success_url = '@jobs.jobsource_list'
        success_message = _("Your job source has been added successfully")
        fields = ('is_active', 'is_featured', 'title', 'source_type', 'source_url', 'widget_id')

        def pre_save(self, obj):
            obj = super(JobSourceCRUDL.Update, self).pre_save(obj)
            obj.org = self.request.org
            return obj

    class List(OrgPermsMixin, SmartListView):
        fields = ('title', 'source_type', 'source_url', 'modified_on')
        default_order = ('-created_on', 'id')

        def get_queryset(self):
            queryset = super(JobSourceCRUDL.List, self).get_queryset().filter(org=self.request.org)
            return queryset
