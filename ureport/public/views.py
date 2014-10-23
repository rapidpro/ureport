from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from smartmin.views import *
from django.utils import timezone

from dash.stories.models import Story
from ureport.polls.models import Poll, PollQuestion
from dash.categories.models import Category
from dash.orgs.models import Org
from ureport.news.models import Video, NewsItem
import math
from datetime import timedelta, datetime

class IndexView(SmartTemplateView):
    template_name = 'public/index.html'

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)

        org = self.request.org
        context['org'] = org

        latest_poll = Poll.get_main_poll(org)
        context['latest_poll'] = latest_poll
        if context['latest_poll']:
            context['trending_words'] = latest_poll.get_trending_words()

        context['recent_polls'] = Poll.get_brick_polls(org)

        context['stories'] = Story.objects.filter(org=org, is_active=True, featured=True).order_by('created_on')

        other_stories = Story.objects.filter(org=org, is_active=True).exclude(pk__in=context['stories'])
        other_stories = other_stories.order_by('created_on')
        context['other_stories'] = other_stories

        videos = Video.objects.filter(is_active=True, org=org).order_by('-created_on')
        context['videos'] = videos

        news = NewsItem.objects.filter(is_active=True, org=org).order_by('-created_on')
        context['news'] = news.count() > 0

        context['most_active_regions'] = org.get_most_active_regions()

        return context

class NewsView(SmartTemplateView):

    def render_to_response(self, context):

        org = self.request.org

        news_items = NewsItem.objects.filter(is_active=True, org=org).order_by('-created_on')
        paginator = Paginator(news_items, 3)

        page = self.request.GET.get('page')
        try:
            news_page = paginator.page(page)
        except PageNotAnInteger:
            news_page = paginator.page(1)
        except EmptyPage:
            news_page = None

        news = []
        next = False
        if news_page:
            next = news_page.has_next()
            for elt in news_page.object_list:
                news.append(elt.as_brick_json())

        output_json = dict(news=news, next=next)
        return HttpResponse(json.dumps(output_json))


class AboutView(SmartTemplateView):
    template_name = 'public/about.html'

    def get_context_data(self, **kwargs):
        context = super(AboutView, self).get_context_data(**kwargs)
        org = self.request.org

        context['org'] = org

        videos = Video.objects.filter(is_active=True, org=org).order_by('-created_on')
        context['videos'] = videos

        return context

class PollContextMixin(object):

    def derive_main_poll(self):
        org = self.request.org
        return Poll.get_main_poll(org)

    def get_context_data(self, **kwargs):
        context = super(PollContextMixin, self).get_context_data(**kwargs)

        org = self.request.org
        context['org'] = org

        main_poll = self.derive_main_poll()
        context['latest_poll'] = main_poll

        context['categories'] = Category.objects.filter(org=org, is_active=True).order_by('name')
        context['polls'] = Poll.objects.filter(org=org, is_active=True, category__is_active=True).order_by('-created_on')

        context['related_stories'] = []
        if main_poll:
            related_stories = Story.objects.filter(org=org, is_active=True, category=main_poll.category)
            related_stories = related_stories.order_by('-featured', '-created_on')
            context['related_stories'] = related_stories

        return context


class PollsView(PollContextMixin, SmartTemplateView):
    template_name = 'public/polls.html'

    def get_context_data(self, **kwargs):
        context = super(PollsView, self).get_context_data(**kwargs)

        context['tab'] = 'list'

        return context

class PollReadView(PollContextMixin, SmartReadView):
    template_name = 'public/polls.html'
    model = Poll

    def derive_queryset(self):
        queryset = super(PollReadView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True)
        return queryset

    def derive_main_poll(self):
        return self.get_object()

class PollQuestionResultsView(SmartReadView):
    model = PollQuestion

    def derive_queryset(self):
        queryset = super(PollQuestionResultsView, self).derive_queryset()
        queryset = queryset.filter(poll__org=self.request.org, is_active=True)
        return queryset

    def render_to_response(self, context):
        segment = self.request.GET.get('segment', None)
        if segment:
            segment = json.loads(segment)

        return HttpResponse(json.dumps(self.object.get_results(segment=segment)))

class BoundaryView(SmartTemplateView):

    def render_to_response(self, context):
        state_id = self.kwargs.get('osm_id', None)

        if state_id:
            boundaries = self.request.org.get_api().get_state_geojson(state_id)
        else:
            boundaries = self.request.org.get_api().get_country_geojson()
        return HttpResponse(json.dumps(boundaries))


class ReportersResultsView(SmartReadView):
    model = Org

    def get_object(self):
        return self.request.org

    def render_to_response(self, context):
        output_data = []

        segment = self.request.GET.get('segment', None)
        if segment:
            segment = json.loads(segment)

        contact_field = self.request.GET.get('contact_field', None)
        if self.get_object() and contact_field:
            api_data = self.get_object().get_contact_field_results(contact_field, segment)
            output_data = self.get_object().organize_categories_data(contact_field, api_data)

        return HttpResponse(json.dumps(output_data))

class StoriesView(SmartTemplateView):
    template_name = 'public/stories.html'

    def get_context_data(self, **kwargs):
        context = super(StoriesView, self).get_context_data(**kwargs)

        org = self.request.org

        context['org'] = org
        context['categories'] = Category.objects.filter(org=org, is_active=True).order_by('name')
        context['featured'] = Story.objects.filter(org=org, featured=True, is_active=True).order_by('-created_on')
        context['other_stories'] = Story.objects.filter(org=org, featured=False, is_active=True).order_by('-created_on')

        return context


class StoryReadView(SmartReadView):
    template_name = 'public/story_read.html'
    model = Story

    def derive_queryset(self):
        queryset = super(StoryReadView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super(StoryReadView, self).get_context_data(**kwargs)

        org = self.request.org

        story = self.get_object()
        story_category = story.category

        context['org'] = org
        context['categories'] = Category.objects.filter(org=org, is_active=True).order_by('name')
        context['other_stories'] = Story.objects.filter(org=org, featured=False, is_active=True).order_by('-created_on')

        related_polls = Poll.objects.filter(org=org, is_active=True, category=story_category).order_by('-created_on')
        context['related_polls'] = related_polls

        related_stories = Story.objects.filter(org=org, is_active=True, category=story_category, featured=True).exclude(pk=story.pk)
        related_stories = related_stories.order_by('-created_on')
        context['related_stories'] = related_stories

        context['story_featured_images'] = story.get_featured_images()

        return context

class UreportersView(SmartTemplateView):
    template_name = 'public/ureporters.html'

    def get_context_data(self, **kwargs):
        context = super(UreportersView, self).get_context_data(**kwargs)

        context['org'] = self.request.org
        return context

class JoinEngageView(SmartTemplateView):
    template_name = 'public/join_engage.html'

    def get_context_data(self, **kwargs):
        context = super(JoinEngageView, self).get_context_data(**kwargs)

        context['org'] = self.request.org
        return context


