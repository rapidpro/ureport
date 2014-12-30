from smartmin.views import SmartTemplateView
from ureport.jobs.models import Source

__author__ = 'awesome'


class JobsView(SmartTemplateView):
    template_name = 'public/jobs.html'

    def get_context_data(self, **kwargs):
        context = super(JobsView, self).get_context_data(**kwargs)

        org = self.request.org

        context['org'] = org
        # context['first_source'] = Source.objects.all()[0]
        context['sources'] = Source.objects.order_by('title')

        return context