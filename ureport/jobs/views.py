from smartmin.views import SmartTemplateView
from ureport.jobs.models import Source

__author__ = 'awesome'


class JobsView(SmartTemplateView):
    template_name = 'public/jobs.html'

    def get_context_data(self, **kwargs):
        context = super(JobsView, self).get_context_data(**kwargs)

        org = self.request.org

        context['org'] = org
        context['rss_sources'] = Source.objects.filter(source_type=Source.RSS).order_by('-pk')
        context['twitter_sources'] = Source.objects.filter(source_type=Source.TWITTER).order_by('-pk')
        context['facebook_sources'] = Source.objects.filter(source_type=Source.FACEBOOK).order_by('-pk')

        return context