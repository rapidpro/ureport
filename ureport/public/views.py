from smartmin.views import *
from django.shortcuts import render_to_response, get_object_or_404, render
from django.utils import timezone

from dash.stories.models import Story
from ureport.polls.models import Poll, PollQuestion
from ureport.categories.models import Category
from dash.orgs.models import Org
from ureport.news.models import Video, NewsItem
import math
import time
from datetime import timedelta, datetime

class PublicSiteMixin(object):

    def get_context_data(self, **kwargs):
        context = super(PublicSiteMixin, self).get_context_data(**kwargs)
        context['is_public'] = True

        return context


class IndexView(PublicSiteMixin, SmartTemplateView):
    template_name = 'public/index.html'

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        org = self.request.org


        context['org'] = org
        latest_poll = Poll.objects.filter(org=org, is_active=True, is_featured=True).order_by('-created_on').first()
        context['latest_poll'] = latest_poll
        if context['latest_poll']:
            context['latest_poll_responses'] = latest_poll.featured_responses.all().order_by('-pk')
            context['question'] = latest_poll.questions.order_by('ruleset_id').first()
            context['trending_words'] = latest_poll.get_trending_words()

        context['recent_polls'] = Poll.get_featured_polls_for_homepage(org, latest_poll)

        context['all_polls'] = Poll.objects.filter(org=org, is_active=True).order_by('-created_on')
        context['stories'] = Story.objects.filter(org=org, is_active=True, featured=True).order_by('created_on')

        other_stories = Story.objects.filter(org=org, is_active=True).exclude(pk__in=context['stories'])
        other_stories = other_stories.order_by('created_on')
        context['other_stories'] = other_stories

        videos = Video.objects.filter(is_active=True, org=org).order_by('-created_on')
        context['videos'] = videos

        news = NewsItem.objects.filter(is_active=True, org=org).order_by('-created_on')
        context['news'] = news


        context['most_active_regions'] = org.get_most_active_regions()

        return context

class AboutView(PublicSiteMixin, SmartTemplateView):
    template_name = 'public/about.html'

    def get_context_data(self, **kwargs):
        context = super(AboutView, self).get_context_data(**kwargs)
        org = self.request.org

        context['org'] = org

        videos = Video.objects.filter(is_active=True, org=org).order_by('-created_on')
        context['videos'] = videos

        return context


class PollsView(PublicSiteMixin, SmartTemplateView):
    template_name = 'public/polls.html'

    def get_context_data(self, **kwargs):
        context = super(PollsView, self).get_context_data(**kwargs)
        org = self.request.org

        context['org'] = org
        latest_poll = Poll.objects.filter(org=org, is_active=True, is_featured=True).order_by('created_on').first()

        context['tab'] = 'list'


        context['latest_poll'] = latest_poll
        if context['latest_poll']:
            context['latest_poll_responses'] = latest_poll.featured_responses.all().order_by('-pk')

        context['featured'] = Poll.objects.filter(org=org, is_active=True).order_by('-created_on').first()
        context['categories'] = Category.objects.filter(org=org, is_active=True).order_by('name')
        context['recent_polls'] = Poll.objects.filter(org=org, is_active=True).order_by('-created_on')
        context['polls'] = Poll.objects.filter(org=org, is_active=True).order_by('-created_on')

        related_stories = Story.objects.filter(org=org, is_active=True, category=latest_poll.category)
        related_stories = related_stories.order_by('-featured', '-created_on')
        context['related_stories'] = related_stories

        return context

class PollReadView(PublicSiteMixin, SmartReadView):
    template_name = 'public/polls.html'
    model = Poll

    def derive_queryset(self):
        queryset = super(PollReadView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super(PollReadView, self).get_context_data(**kwargs)
        org = self.request.org

        latest_poll = self.get_object()

        context['latest_poll'] = latest_poll
        if context['latest_poll']:
            context['latest_poll_responses'] = latest_poll.featured_responses.all().order_by('-pk')


        context['categories'] = Category.objects.filter(org=org, is_active=True).order_by('name')
        context['polls'] = Poll.objects.filter(org=org, is_active=True).order_by('-created_on')

        related_stories = Story.objects.filter(org=org, is_active=True, category=self.get_object().category)
        related_stories = related_stories.order_by('-featured', '-created_on')
        context['related_stories'] = related_stories

        return context

class PollStatisticsView(PublicSiteMixin, SmartReadView):
    template_name = 'public/poll_statistics.html'
    model = Poll

    def derive_queryset(self):
        queryset = super(PollStatisticsView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super(PollStatisticsView, self).get_context_data(**kwargs)
        org = self.request.org
        context['tab'] = 'statistics'

        context['categories'] = Category.objects.filter(org=org, is_active=True).order_by('name')
        context['polls'] = Poll.objects.filter(org=org, is_active=True).order_by('-created_on')

        return context

class PollLocationView(PublicSiteMixin, SmartReadView):
    template_name = 'public/poll_location.html'
    model = Poll

    def derive_queryset(self):
        queryset = super(PollLocationView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super(PollLocationView, self).get_context_data(**kwargs)
        org = self.request.org
        context['tab'] = 'location'

        context['categories'] = Category.objects.filter(org=org, is_active=True).order_by('name')
        context['polls'] = Poll.objects.filter(org=org, is_active=True).order_by('-created_on')

        return context

class PollKeywordView(PublicSiteMixin, SmartReadView):
    template_name = 'public/poll_keyword.html'
    model = Poll

    def derive_queryset(self):
        queryset = super(PollKeywordView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True)
        return queryset

    def get_context_data(self, **kwargs):
        context = super(PollKeywordView, self).get_context_data(**kwargs)
        org = self.request.org
        context['tab'] = 'keyword'

        context['categories'] = Category.objects.filter(org=org, is_active=True).order_by('name')
        context['polls'] = Poll.objects.filter(org=org, is_active=True).order_by('-created_on')

        return context

class PollQuestionResultsView(PublicSiteMixin, SmartReadView):
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
            output_data = self.get_object().get_contact_field_results(contact_field, segment)

        cleaned_categories = []
        interval_dict = dict()
        now = timezone.now()
        # if we have the age_label; Ignore invalid years and make intervals
        if output_data and contact_field.lower() == self.get_object().get_config('born_label').lower():
            current_year = now.year

            for elt in output_data[0]['categories']:
                year_label = elt['label']
                try:
                    if len(year_label) == 4 and int(float(year_label)) > 1900:
                        decade = int(math.floor((current_year - int(elt['label'])) / 10)) * 10
                        key = "%s-%s" % (decade, decade+10)
                        if interval_dict.get(key, None):
                            interval_dict[key] += elt['count']
                        else:
                            interval_dict[key] = elt['count']
                except ValueError:
                    pass

            for obj_key in interval_dict.keys():
                cleaned_categories.append(dict(label=obj_key, count=interval_dict[obj_key] ))

            output_data[0]['categories'] = sorted(cleaned_categories, key=lambda k: int(k['label'].split('-')[0]))

        elif output_data and contact_field.lower() == self.get_object().get_config('registration_label').lower():
            six_months_ago = now - timedelta(days=180)
            six_months_ago = six_months_ago - timedelta(six_months_ago.weekday())

            for elt in output_data[0]['categories']:
                time_str =  elt['label']
                parsed_time = datetime.strptime(time_str, '%d-%m-%Y %H:%M')

                # this is in the range we care about
                if parsed_time > six_months_ago:
                    # get the week of the year
                    dict_key = parsed_time.strftime("%W")

                    if interval_dict.get(dict_key, None):
                        interval_dict[dict_key] += elt['count']
                    else:
                        interval_dict[dict_key] = elt['count']

            # build our final dict using week numbers
            categories = []
            start = six_months_ago
            while start < timezone.now():
                week_dict = start.strftime("%W")
                count = interval_dict.get(week_dict, 0)
                categories.append(dict(label=start.strftime("%m/%d/%y"), count=count))

                start = start + timedelta(days=7)

            output_data[0]['categories'] = categories


        elif output_data and contact_field.lower() == self.get_object().get_config('occupation_label').lower():
            other_count = 0
            for elt in output_data[0]['categories']:
                if len(cleaned_categories) < 9 and elt['label'] != "All Responses":
                    cleaned_categories.append(elt)
                else:
                    other_count += elt['count']
            # cleaned_categories.append(dict(label="Others", count=other_count))
            output_data[0]['categories'] = cleaned_categories

        return HttpResponse(json.dumps(output_data))

class StoriesView(PublicSiteMixin, SmartTemplateView):
    template_name = 'public/stories.html'

    def get_context_data(self, **kwargs):
        context = super(StoriesView, self).get_context_data(**kwargs)

        org = self.request.org

        context['org'] = org
        context['categories'] = Category.objects.filter(org=org, is_active=True).order_by('name')
        context['featured'] = Story.objects.filter(org=org, featured=True, is_active=True).order_by('-created_on')
        context['other_stories'] = Story.objects.filter(org=org, featured=False, is_active=True).order_by('-created_on')

        return context


class StoryReadView(PublicSiteMixin, SmartReadView):
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

        return context

class UreportersView(PublicSiteMixin, SmartTemplateView):
    template_name = 'public/ureporters.html'

    def get_context_data(self, **kwargs):
        context = super(UreportersView, self).get_context_data(**kwargs)

        context['org'] = self.request.org
        return context

class JoinEngageView(PublicSiteMixin, SmartTemplateView):
    template_name = 'public/join_engage.html'

    def get_context_data(self, **kwargs):
        context = super(JoinEngageView, self).get_context_data(**kwargs)

        context['org'] = self.request.org
        return context


