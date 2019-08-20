# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import calendar
import json

import six
from dash.categories.models import Category
from dash.dashblocks.models import DashBlock, DashBlockType
from dash.stories.models import Story
from smartmin.views import SmartReadView, SmartTemplateView

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Prefetch
from django.http import HttpResponse
from django.utils.translation import ugettext_lazy as _

from ureport.jobs.models import JobSource
from ureport.locations.models import Boundary
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll
from ureport.stats.models import ContactActivity
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
        context["global_counter"] = get_global_count()

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = org.get_age_stats()
        context["reporters"] = org.get_reporters_count()
        context["feat_images"] = range(10)

        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")

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


class CustomPage(SmartReadView):
    template_name = "public_v2/custom_page.html"
    model = DashBlock
    slug_url_kwarg = "link"

    def derive_queryset(self):
        org = self.request.org
        try:
            dashblock_type = DashBlockType.objects.get(slug="additional_menu")
        except DashBlockType.DoesNotExist:
            return DashBlock.objects.none()

        queryset = DashBlock.objects.filter(dashblock_type=dashblock_type, org=org, is_active=True)
        queryset = queryset.order_by("-priority")

        return queryset


class AboutView(SmartTemplateView):
    template_name = "public_v2/about.html"

    def get_context_data(self, **kwargs):
        context = super(AboutView, self).get_context_data(**kwargs)
        org = self.request.org

        context["org"] = org

        videos = Video.objects.filter(is_active=True, org=org).order_by("-created_on")
        context["videos"] = videos

        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        return context


class PollContextMixin(object):
    def derive_main_poll(self):
        org = self.request.org
        return Poll.get_main_poll(org)

    def get_context_data(self, **kwargs):
        context = super(PollContextMixin, self).get_context_data(**kwargs)

        org = self.request.org
        context["org"] = org

        context["gender_stats"] = org.get_gender_stats()
        context["age_stats"] = org.get_age_stats()

        context["states"] = [dict(id=k, name=v) for k, v in Boundary.get_org_top_level_boundaries_name(org).items()]

        main_poll = self.derive_main_poll()
        context["latest_poll"] = main_poll

        if main_poll:
            top_question = main_poll.get_questions().first()
            context["top_question"] = top_question

            if top_question:
                gender_stats = top_question.get_gender_stats()
                total_gender = 0
                for elt in gender_stats:
                    total_gender += elt["set"]
                gender_stats_dict = {
                    elt["label"].lower(): dict(
                        count=elt["set"], percentage=int(round(elt["set"] * 100 / float(total_gender)))
                    )
                    for elt in gender_stats
                    if total_gender
                }

                context["gender_stats"] = gender_stats_dict

                age_stats = top_question.get_age_stats()
                total_age = 0
                for elt in age_stats:
                    total_age += elt["set"]

                context["age_stats"] = [
                    dict(name=elt["label"], y=int(round(elt["set"] * 100 / float(total_age))))
                    for elt in age_stats
                    if total_age
                ]
                context["locations_stats"] = top_question.get_location_stats()

        context["categories"] = (
            Category.objects.filter(org=org, is_active=True)
            .prefetch_related(Prefetch("polls", queryset=Poll.objects.filter(is_active=True)))
            .order_by("name")
        )
        context["polls"] = Poll.get_public_polls(org=org).order_by("-poll_date")

        context["related_stories"] = []
        if main_poll:
            related_stories = Story.objects.filter(org=org, is_active=True, category=main_poll.category)
            related_stories = related_stories.order_by("-featured", "-created_on")
            context["related_stories"] = related_stories

        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
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
        context["categories"] = (
            Category.objects.filter(org=org, is_active=True)
            .prefetch_related(Prefetch("story_set", queryset=Story.objects.filter(is_active=True)))
            .order_by("name")
        )
        context["stories"] = Story.objects.filter(org=org, is_active=True).order_by("title")

        context["featured"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
        context["other_stories"] = Story.objects.filter(org=org, featured=False, is_active=True).order_by(
            "-created_on"
        )
        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")

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
        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
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
        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")

        # global counter
        context["global_counter"] = get_global_count()

        polled = org.get_filtered_engagement_counts("total-ruleset-polled:engagement:date")
        responded = org.get_filtered_engagement_counts("total-ruleset-responded:engagement:date")
        response_rate = {}
        for key, val in responded.items():
            polled_count = polled.get(key, 0)
            if polled_count == 0:
                response_rate[key] = 0
            else:
                response_rate[key] = val * 100 / polled_count

        context["response_rate"] = response_rate

        context["responded_male"] = org.get_filtered_engagement_counts(
            "total-ruleset-responded:engagement:gender:m:date"
        )
        context["responded_female"] = org.get_filtered_engagement_counts(
            "total-ruleset-responded:engagement:gender:f:date"
        )

        context["contact_activities"] = ContactActivity.get_activity(org)
        return context


class JoinEngageView(SmartTemplateView):
    template_name = "public_v2/join_engage.html"

    def get_context_data(self, **kwargs):
        context = super(JoinEngageView, self).get_context_data(**kwargs)
        org = self.request.org
        context["org"] = org
        context["main_stories"] = Story.objects.filter(org=org, featured=True, is_active=True).order_by("-created_on")
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
