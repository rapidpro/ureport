# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import calendar
import json

import six
from dash.categories.models import Category
from dash.stories.models import Story
from smartmin.views import SmartReadView, SmartTemplateView

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse
from django.utils.translation import ugettext_lazy as _

from ureport.jobs.models import JobSource
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll
from ureport.utils import get_global_count


class IndexView(SmartTemplateView):
    template_name = "public_v2/index.html"

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org

        latest_poll = Poll.get_main_poll(org)
        context["latest_poll"] = latest_poll
        if context["latest_poll"]:
            context["trending_words"] = latest_poll.get_trending_words()

        brick_poll_ids = Poll.get_brick_polls_ids(org)
        context["recent_polls"] = Poll.objects.filter(id__in=brick_poll_ids).order_by("-created_on")

        context["stories"] = Story.objects.filter(org=org, is_active=True, featured=True).order_by("-created_on")

        videos = Video.objects.filter(is_active=True, org=org).order_by("-created_on")
        context["videos"] = videos

        news = NewsItem.objects.filter(is_active=True, org=org).order_by("-created_on")
        context["news"] = news.count() > 0

        context["most_active_regions"] = org.get_regions_stats()

        # global counter
        if org.get_config("common.is_global"):
            context["global_counter"] = get_global_count()

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = org.get_age_stats()
        context["reporters"] = org.get_reporters_count()

        return context


class Count(SmartTemplateView):
    template_name = "public_v2/count"

    def get_context_data(self, **kwargs):
        context = super(Count, self).get_context_data()

        org = self.request.org
        context["org"] = org
        context["count"] = org.get_reporters_count()
        return context


class NewsView(SmartTemplateView):
    def render_to_response(self, context, **kwargs):

        org = self.request.org

        news_items = NewsItem.objects.filter(is_active=True, org=org).order_by("-created_on")
        paginator = Paginator(news_items, 3)

        page = self.request.GET.get("page")
        try:
            news_page = paginator.page(page)
        except PageNotAnInteger:
            news_page = paginator.page(1)
        except EmptyPage:
            news_page = None

        news = []
        next_page = False
        if news_page:
            next_page = news_page.has_next()
            for elt in news_page.object_list:
                news.append(elt.as_brick_json())

        output_json = dict(news=news, next=next_page)
        return HttpResponse(json.dumps(output_json))


class AdditionalMenu(SmartTemplateView):
    template_name = "public_v2/additional_menu.haml"

    def get_context_data(self, **kwargs):
        context = super(AdditionalMenu, self).get_context_data(**kwargs)
        org = self.request.org

        context["org"] = org
        return context


class AboutView(SmartTemplateView):
    template_name = "public_v2/about.html"

    def get_context_data(self, **kwargs):
        context = super(AboutView, self).get_context_data(**kwargs)
        org = self.request.org

        context["org"] = org

        videos = Video.objects.filter(is_active=True, org=org).order_by("-created_on")
        context["videos"] = videos

        return context


class PollContextMixin(object):
    def derive_main_poll(self):
        org = self.request.org
        return Poll.get_main_poll(org)

    def get_context_data(self, **kwargs):
        context = super(PollContextMixin, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org

        main_poll = self.derive_main_poll()
        context["latest_poll"] = main_poll

        context["categories"] = Category.objects.filter(org=org, is_active=True).order_by("name")
        context["polls"] = Poll.get_public_polls(org=org).order_by("-poll_date")

        context["related_stories"] = []
        if main_poll:
            related_stories = Story.objects.filter(org=org, is_active=True, category=main_poll.category)
            related_stories = related_stories.order_by("-featured", "-created_on")
            context["related_stories"] = related_stories

        return context


class PollsView(PollContextMixin, SmartTemplateView):
    template_name = "public_v2/polls.html"

    def get_context_data(self, **kwargs):
        context = super(PollsView, self).get_context_data(**kwargs)

        context["tab"] = "list"

        return context


class PollReadView(PollContextMixin, SmartReadView):
    template_name = "public_v2/polls.html"
    model = Poll

    def derive_queryset(self):
        queryset = super(PollReadView, self).derive_queryset()
        queryset = queryset.filter(org=self.request.org, is_active=True, has_synced=True)
        return queryset

    def derive_main_poll(self):
        return self.get_object()


class StoriesView(SmartTemplateView):
    template_name = "public_v2/stories.html"

    def get_context_data(self, **kwargs):
        context = super(StoriesView, self).get_context_data(**kwargs)

        org = self.request.org

        context["org"] = org
        context["categories"] = Category.objects.filter(org=org, is_active=True).order_by("name")
        context["featured"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        context["other_stories"] = Story.objects.filter(org=org, featured=False, is_active=True).order_by(
            "-created_on"
        )

        return context


class StoryReadView(SmartReadView):
    template_name = "public_v2/story_read.html"
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

        context["org"] = org
        context["categories"] = Category.objects.filter(org=org, is_active=True).order_by("name")
        context["other_stories"] = Story.objects.filter(org=org, featured=False, is_active=True).order_by(
            "-created_on"
        )

        related_polls = Poll.objects.filter(
            org=org, is_active=True, has_synced=True, category=story_category
        ).order_by("-created_on")
        context["related_polls"] = related_polls

        related_stories = Story.objects.filter(
            org=org, is_active=True, category=story_category, featured=True
        ).exclude(pk=story.pk)
        related_stories = related_stories.order_by("-created_on")
        context["related_stories"] = related_stories

        context["story_featured_images"] = story.get_featured_images()

        return context


class UreportersView(SmartTemplateView):
    template_name = "public_v2/ureporters.html"

    def get_context_data(self, **kwargs):
        context = super(UreportersView, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org

        # remove the first option '' from calender.month_abbr
        context["months"] = [six.text_type(_("%s")) % m for m in calendar.month_abbr][1:]

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = org.get_age_stats()
        context["registration_stats"] = org.get_registration_stats()
        context["occupation_stats"] = org.get_occupation_stats()
        context["reporters"] = org.get_reporters_count()

        return context


class JoinEngageView(SmartTemplateView):
    template_name = "public_v2/join_engage.html"

    def get_context_data(self, **kwargs):
        context = super(JoinEngageView, self).get_context_data(**kwargs)

        context["org"] = self.request.org
        return context


class JobsView(SmartTemplateView):
    template_name = "public_v2/jobs.html"

    def get_context_data(self, **kwargs):
        context = super(JobsView, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = self.request.org
        context["job_sources"] = JobSource.objects.filter(org=org, is_active=True).order_by(
            "-is_featured", "-created_on"
        )
        return context
