from django.views.decorators.cache import cache_page
from .views import *

urlpatterns = patterns('',
    (r'^$', IndexView.as_view(), {}, 'public.index'),
    (r'^news/$', NewsView.as_view(), {}, 'public.news'),
    (r'^about/$', AboutView.as_view(), {}, 'public.about'),
    (r'^polls/$', PollsView.as_view(), {}, 'public.polls'),
    (r'^poll/(?P<pk>\d+)/$', PollReadView.as_view(), {}, 'public.poll_read'),
    (r'^pollquestion/(?P<pk>\d+)/results/$', cache_page(60 * 5)(PollQuestionResultsView.as_view()), {}, 'public.pollquestion_results'),
    (r'^contact_field_results/$', ReportersResultsView.as_view(), {}, 'public.contact_field_results'),
    (r'^boundaries/$', BoundaryView.as_view(), {}, 'public.boundaries'),
    (r'^boundaries/(?P<osm_id>[a-zA-Z0-9]+)/$', BoundaryView.as_view(), {}, 'public.boundaries'),
    (r'^ureporters/$', UreportersView.as_view(), {}, 'public.ureporters'),
    (r'^stories/$', StoriesView.as_view(), {}, 'public.stories'),
    (r'^story/(?P<pk>\d+)/$', StoryReadView.as_view(), {}, 'public.story_read'),
    (r'^join/$', JoinEngageView.as_view(), {}, 'public.join'),
)

