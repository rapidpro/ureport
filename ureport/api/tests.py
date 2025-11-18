# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import zoneinfo
from collections import OrderedDict
from datetime import datetime
from random import randint

import six
from mock import patch
from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth import get_user_model
from django.utils import timezone

from dash.categories.models import Category
from dash.dashblocks.models import DashBlock, DashBlockType
from dash.orgs.models import Org
from dash.stories.models import Story
from ureport.api.serializers import CategoryReadSerializer, StoryReadSerializer, generate_absolute_url_from_file
from ureport.contacts.models import ReportersCounter
from ureport.flows.models import FlowResult
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll, PollQuestion


class UreportAPITests(APITestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="super", email="super@user.com", password="super"
        )
        self.uganda = self.create_org("uganda", self.superuser)
        self.nigeria = self.create_org("testserver", self.superuser)

        self.health_uganda = Category.objects.create(
            org=self.uganda, name="Health", created_by=self.superuser, modified_by=self.superuser
        )

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.superuser, modified_by=self.superuser
        )

        self.reg_poll = self.create_poll("registration")
        self.another_poll = self.create_poll("another")
        self.first_featured_poll = self.create_poll("first featured", is_featured=True)
        self.first_poll_question = self.create_poll_question(
            self.superuser, self.first_featured_poll, "test question", "uuid1"
        )
        self.second_featured_poll = self.create_poll("second featured", is_featured=True)

        self.second_poll_question = self.create_poll_question(
            self.superuser, self.second_featured_poll, "another test question", "uuid2"
        )
        self.non_synced_poll = self.create_poll("unsynced", has_synced=False)

        self.type_foo = DashBlockType.objects.create(
            name="Foo",
            slug="foo",
            description="foo description",
            has_title=True,
            has_image=True,
            has_rich_text=True,
            has_summary=True,
            has_link=True,
            has_color=False,
            has_video=False,
            has_tags=True,
            has_gallery=False,
            created_by=self.superuser,
            modified_by=self.superuser,
        )

        self.type_bar = DashBlockType.objects.create(
            name="Bar",
            slug="bar",
            description="bar description",
            has_title=False,
            has_image=False,
            has_rich_text=False,
            has_summary=False,
            has_link=False,
            has_color=False,
            has_video=False,
            has_tags=True,
            has_gallery=False,
            created_by=self.superuser,
            modified_by=self.superuser,
        )

        self.dashblock1 = DashBlock.objects.create(
            dashblock_type=self.type_foo,
            org=self.uganda,
            title="First",
            content="First content",
            summary="first summary",
            created_by=self.superuser,
            modified_by=self.superuser,
        )

        self.dashblock2 = DashBlock.objects.create(
            dashblock_type=self.type_bar,
            org=self.uganda,
            content="Bar content",
            summary="bar summary here",
            created_by=self.superuser,
            modified_by=self.superuser,
        )

        self.news_item = self.create_news_item("Some item")
        self.create_video("Test Video")
        self.create_story("Test Story")

    def create_org(self, subdomain, user):
        name = subdomain

        org = Org.objects.filter(subdomain=subdomain).first()
        if org:
            org.name = name
            org.save()
        else:
            org = Org.objects.create(domain=subdomain, name=name, created_by=user, modified_by=user)

        org.administrators.add(user)

        self.assertEqual(Org.objects.filter(domain=subdomain).count(), 1)
        return Org.objects.get(domain=subdomain)

    def create_poll(self, title, is_featured=False, has_synced=True, published=True):
        now = timezone.now()
        return Poll.objects.create(
            flow_uuid=six.text_type(randint(1000, 9999)),
            title=title,
            category=self.health_uganda,
            poll_date=now,
            org=self.uganda,
            is_featured=is_featured,
            published=published,
            has_synced=has_synced,
            created_by=self.superuser,
            modified_by=self.superuser,
        )

    def create_poll_question(self, user, poll, result_name, result_uuid):
        flow_result = FlowResult.objects.filter(
            org=poll.org, flow_uuid=poll.flow_uuid, result_uuid=result_uuid
        ).first()
        if flow_result:
            flow_result.result_name = result_name
            flow_result.save(update_fields=("result_name",))
        else:
            flow_result = FlowResult.objects.create(
                org=poll.org, flow_uuid=poll.flow_uuid, result_uuid=result_uuid, result_name=result_name
            )

        question = PollQuestion.objects.filter(flow_result=flow_result, poll=poll).first()
        if question:
            question.ruleset_label = result_name
            question.save(update_fields=("ruleset_label",))
        else:
            question = PollQuestion.objects.create(
                poll=poll,
                title=result_name,
                ruleset_label=result_name,
                ruleset_uuid=result_uuid,
                flow_result=flow_result,
                created_by=user,
                modified_by=user,
            )
        return question

    def create_news_item(self, title):
        return NewsItem.objects.create(
            title=title,
            description="uganda description 1",
            link="http://uganda.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.superuser,
            modified_by=self.superuser,
        )

    def create_video(self, title):
        self.uganda_video = Video.objects.create(
            title=title,
            description="You are welcome to Kampala",
            video_id="Kplatown",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.superuser,
            modified_by=self.superuser,
        )

    def create_story(self, title):
        self.uganda_story = Story.objects.create(
            title=title,
            featured=True,
            summary="This is a test summary",
            content="This is test content",
            video_id="iouiou",
            tags="tag1, tag2, tag3",
            category=self.health_uganda,
            created_by=self.superuser,
            modified_by=self.superuser,
            org=self.uganda,
        )

    def test_api_docs_page(self):
        response = self.client.get("/api/v1/docs/")
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api")
        self.assertEqual(response.status_code, 301)

        response = self.client.get("/api", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/api/v1/docs/")

        response = self.client.get("/api/")
        self.assertEqual(response.status_code, 302)

        response = self.client.get("/api/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/api/v1/docs/")

        response = self.client.get("/api/v1")
        self.assertEqual(response.status_code, 301)

        response = self.client.get("/api/v1", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/api/v1/docs/")

        response = self.client.get("/api/v1/")
        self.assertEqual(response.status_code, 302)

        response = self.client.get("/api/v1/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/api/v1/docs/")

    def test_orgs_list(self):
        url = "/api/v1/orgs/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], Org.objects.count())

    @patch("django.core.cache.cache.get")
    def test_single_org(self, mock_cache_get):
        mock_cache_get.return_value = None

        url = "/api/v1/orgs/%d/" % self.uganda.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        org = self.uganda
        logo_url = generate_absolute_url_from_file(response, org.logo) if org.logo else None
        gender_stats = response.data.pop("gender_stats")
        age_stats = response.data.pop("age_stats")
        registration_stats = response.data.pop("registration_stats")
        occupation_stats = response.data.pop("occupation_stats")
        schemes_stats = response.data.pop("schemes_stats")
        reporters_count = response.data.pop("reporters_count")
        self.assertDictEqual(
            response.data,
            dict(
                id=org.pk,
                logo_url=logo_url,
                name=org.name,
                language=org.language,
                subdomain=org.subdomain,
                domain=org.domain,
                timezone=six.text_type(org.timezone),
            ),
        )

        self.assertEqual(
            gender_stats, dict(female_count=0, female_percentage="---", male_count=0, male_percentage="---")
        )

        self.assertEqual(
            age_stats,
            [
                dict(name="0-14", y=0, absolute_count=0),
                dict(name="15-19", y=0, absolute_count=0),
                dict(name="20-24", y=0, absolute_count=0),
                dict(name="25-30", y=0, absolute_count=0),
                dict(name="31-34", y=0, absolute_count=0),
                dict(name="35+", y=0, absolute_count=0),
            ],
        )
        self.assertEqual(reporters_count, 0)
        self.assertEqual(occupation_stats, [])
        self.assertEqual(schemes_stats, [])

        ReportersCounter.objects.create(org=org, type="gender:f", count=2)
        ReportersCounter.objects.create(org=org, type="gender:m", count=2)
        ReportersCounter.objects.create(org=org, type="gender:m", count=1)

        now = timezone.now()
        now_year = now.year

        two_years_ago = now_year - 2
        five_years_ago = now_year - 5
        twelve_years_ago = now_year - 12
        forthy_five_years_ago = now_year - 45

        ReportersCounter.objects.create(org=org, type="born:%s" % two_years_ago, count=2)
        ReportersCounter.objects.create(org=org, type="born:%s" % five_years_ago, count=1)
        ReportersCounter.objects.create(org=org, type="born:%s" % twelve_years_ago, count=3)
        ReportersCounter.objects.create(org=org, type="born:%s" % twelve_years_ago, count=2)
        ReportersCounter.objects.create(org=org, type="born:%s" % forthy_five_years_ago, count=2)

        ReportersCounter.objects.create(org=org, type="born:10", count=10)
        ReportersCounter.objects.create(org=org, type="born:732837", count=20)

        ReportersCounter.objects.create(org=org, type="total-reporters", count=5)

        ReportersCounter.objects.create(org=org, type="occupation:student", count=5)
        ReportersCounter.objects.create(org=org, type="occupation:writer", count=2)
        ReportersCounter.objects.create(org=org, type="occupation:all responses", count=13)

        response = self.client.get(url)

        gender_stats = response.data.pop("gender_stats")
        self.assertEqual(
            gender_stats, dict(female_count=2, female_percentage="40%", male_count=3, male_percentage="60%")
        )

        age_stats = response.data.pop("age_stats")
        self.assertEqual(
            age_stats,
            [
                dict(name="0-14", y=80, absolute_count=8),
                dict(name="15-19", y=0, absolute_count=0),
                dict(name="20-24", y=0, absolute_count=0),
                dict(name="25-30", y=0, absolute_count=0),
                dict(name="31-34", y=0, absolute_count=0),
                dict(name="35+", y=20, absolute_count=2),
            ],
        )

        reporters_count = response.data.pop("reporters_count")
        self.assertEqual(reporters_count, 5)

        occupation_stats = response.data.pop("occupation_stats")
        self.assertEqual(occupation_stats, [])

        tz = zoneinfo.ZoneInfo("UTC")

        with patch.object(timezone, "now", return_value=datetime(2015, 9, 4, 3, 4, 5, 6, tzinfo=tz)):
            for entry in registration_stats:
                self.assertEqual(entry["count"], 0)

            ReportersCounter.objects.create(org=org, type="registered_on:2015-08-27", count=3)
            ReportersCounter.objects.create(org=org, type="registered_on:2015-08-25", count=2)
            ReportersCounter.objects.create(org=org, type="registered_on:2015-08-25", count=3)
            ReportersCounter.objects.create(org=org, type="registered_on:2015-08-25", count=1)
            ReportersCounter.objects.create(org=org, type="registered_on:2015-06-30", count=2)
            ReportersCounter.objects.create(org=org, type="registered_on:2015-06-30", count=2)
            ReportersCounter.objects.create(org=org, type="registered_on:2014-11-25", count=6)

            response = self.client.get(url)

            stats = response.data.pop("registration_stats")

            non_zero_keys = {"08/24/15": 9, "06/29/15": 4}

            for entry in stats:
                self.assertFalse(entry["label"].endswith("14"))
                if entry["count"] != 0:
                    self.assertTrue(entry["label"] in non_zero_keys.keys())
                    self.assertEqual(entry["count"], non_zero_keys[entry["label"]])

    def test_polls_by_org_list(self):
        url = "/api/v1/polls/org/%d/" % self.uganda.pk
        url2 = "/api/v1/polls/org/%d/" % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["count"],
            Poll.objects.filter(org=self.uganda, is_active=True, published=True, has_synced=True).count(),
        )
        self.assertTrue(response.data["results"][0]["created_on"] > response.data["results"][1]["created_on"])

        response = self.client.get(url2)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["count"],
            Poll.objects.filter(org=self.nigeria, is_active=True, published=True, has_synced=True).count(),
        )

        response = self.client.get(f"{url}?sort=modified_on")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["count"],
            Poll.objects.filter(org=self.uganda, is_active=True, published=True, has_synced=True).count(),
        )
        self.assertTrue(response.data["results"][0]["modified_on"] > response.data["results"][1]["modified_on"])

    def test_polls_by_org_list_with_flow_uuid_parameter(self):
        url = "/api/v1/polls/org/%d/?flow_uuid=%s" % (self.uganda.pk, self.reg_poll.flow_uuid)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["title"], "registration")

    def test_polls_by_org_list_with_fields_parameter(self):
        url = "/api/v1/polls/org/%d/?fields=%s" % (self.uganda.pk, "title")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_polls = Poll.objects.filter(org=self.uganda, is_active=True, published=True, has_synced=True).count()
        self.assertEqual(response.data["count"], count_polls)
        polls = [self.second_featured_poll, self.first_featured_poll, self.another_poll, self.reg_poll]
        for i in range(count_polls):
            self.assertEqual(response.data["results"][i]["title"], polls[i].title)

    def test_polls_by_org_list_with_exclude_parameter(self):
        url = "/api/v1/polls/org/%d/?exclude=%s,%s,%s,%s,%s,%s" % (
            self.uganda.pk,
            "flow_uuid",
            "title",
            "category",
            "poll_date",
            "modified_on",
            "created_on",
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_polls = Poll.objects.filter(org=self.uganda, is_active=True, published=True, has_synced=True).count()
        poll = self.reg_poll
        self.assertEqual(response.data["count"], count_polls)
        self.assertDictEqual(
            response.data["results"][3],
            dict(
                id=poll.pk,
                org=poll.org_id,
                questions=[],
            ),
        )

    def test_featured_poll_by_org_list_when_featured_polls_exists(self):
        url = "/api/v1/polls/org/%d/featured/" % self.uganda.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["title"], "second featured")
        self.assertEqual(response.data["results"][1]["title"], "first featured")
        self.assertTrue(response.data["results"][0]["created_on"] > response.data["results"][1]["created_on"])

        response = self.client.get(f"{url}?sort=modified_on")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertTrue(response.data["results"][0]["modified_on"] > response.data["results"][1]["modified_on"])

    def test_featured_poll_by_org_list_with_fields_parameter_when_featured_polls_exists(self):
        url = "/api/v1/polls/org/%d/featured/?fields=%s" % (self.uganda.pk, "created_on")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertTrue(response.data["results"][0]["created_on"] > response.data["results"][1]["created_on"])

    def test_featured_poll_by_org_list_when_no_featured_polls_exists(self):
        url = "/api/v1/polls/org/%d/featured/" % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

        response = self.client.get("/api/v1/polls/org/foo/featured/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_single_poll(self):
        url = "/api/v1/polls/%d/" % self.reg_poll.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        poll = self.reg_poll
        category = response.data.pop("category")
        self.assertDictEqual(
            response.data,
            dict(
                id=poll.pk,
                flow_uuid=poll.flow_uuid,
                title=poll.title,
                org=poll.org_id,
                questions=[],
                poll_date=poll.poll_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                modified_on=poll.modified_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                created_on=poll.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        )

        self.assertDictEqual(
            dict(category),
            dict(
                OrderedDict(name=poll.category.name, image_url=CategoryReadSerializer().get_image_url(poll.category))
            ),
        )

        with patch("ureport.polls.models.PollQuestion.get_results") as mock_get_results:
            mock_get_results.return_value = [dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT")]

            poll_question = self.create_poll_question(self.superuser, self.reg_poll, "What's on mind? :)", "uuid1")

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            category = response.data.pop("category")
            self.assertDictEqual(
                response.data,
                dict(
                    id=poll.pk,
                    flow_uuid=poll.flow_uuid,
                    title=poll.title,
                    org=poll.org_id,
                    created_on=poll.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    modified_on=poll.modified_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    poll_date=poll.poll_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    questions=[
                        dict(
                            id=poll_question.pk,
                            ruleset_uuid="uuid1",
                            title="What's on mind? :)",
                            results=dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT"),
                            results_by_age=[dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT")],
                            results_by_gender=[dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT")],
                            results_by_location=[
                                dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT")
                            ],
                        )
                    ],
                ),
            )

            poll_question.is_active = False
            poll_question.save()

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            category = response.data.pop("category")
            self.assertDictEqual(
                response.data,
                dict(
                    id=poll.pk,
                    flow_uuid=poll.flow_uuid,
                    title=poll.title,
                    org=poll.org_id,
                    poll_date=poll.poll_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    modified_on=poll.modified_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    created_on=poll.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    questions=[],
                ),
            )

    def test_single_poll_with_fields_parameter(self):
        url = "/api/v1/polls/%d/?fields=%s,%s,%s" % (self.reg_poll.pk, "id", "title", "questions")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        poll = self.reg_poll
        self.assertDictEqual(
            response.data,
            dict(
                id=poll.pk,
                title=poll.title,
                questions=[],
            ),
        )

        with patch("ureport.polls.models.PollQuestion.get_results") as mock_get_results:
            mock_get_results.return_value = [dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT")]

            poll_question = self.create_poll_question(self.superuser, self.reg_poll, "What's on mind? :)", "uuid1")

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertDictEqual(
                response.data,
                dict(
                    id=poll.pk,
                    title=poll.title,
                    questions=[
                        dict(
                            id=poll_question.pk,
                            ruleset_uuid="uuid1",
                            title="What's on mind? :)",
                            results=dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT"),
                            results_by_age=[dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT")],
                            results_by_gender=[dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT")],
                            results_by_location=[
                                dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT")
                            ],
                        )
                    ],
                ),
            )

            poll_question.is_active = False
            poll_question.save()

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertDictEqual(
                response.data,
                dict(
                    id=poll.pk,
                    title=poll.title,
                    questions=[],
                ),
            )

    def test_single_poll_with_exclude_parameter(self):
        url = "/api/v1/polls/%d/?exclude=%s,%s,%s,%s" % (self.reg_poll.pk, "id", "title", "category", "questions")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        poll = self.reg_poll
        self.assertDictEqual(
            response.data,
            dict(
                flow_uuid=poll.flow_uuid,
                org=poll.org_id,
                poll_date=poll.poll_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                modified_on=poll.modified_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                created_on=poll.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        )

        with patch("ureport.polls.models.PollQuestion.get_results") as mock_get_results:
            mock_get_results.return_value = [dict(set=20, unset=10, open_ended=False, categories="CATEGORIES-DICT")]

            poll_question = self.create_poll_question(self.superuser, self.reg_poll, "What's on mind? :)", "uuid1")

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertDictEqual(
                response.data,
                dict(
                    flow_uuid=poll.flow_uuid,
                    org=poll.org_id,
                    created_on=poll.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    modified_on=poll.modified_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    poll_date=poll.poll_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                ),
            )

            poll_question.is_active = False
            poll_question.save()

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertDictEqual(
                response.data,
                dict(
                    flow_uuid=poll.flow_uuid,
                    org=poll.org_id,
                    poll_date=poll.poll_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    modified_on=poll.modified_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    created_on=poll.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                ),
            )

    def test_news_item_by_org_list(self):
        url = "/api/v1/news/org/%d/" % self.uganda.pk
        url1 = "/api/v1/news/org/%d/" % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], NewsItem.objects.filter(org=self.uganda).count())
        response = self.client.get(url1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], NewsItem.objects.filter(org=self.nigeria).count())

    def test_single_news_item(self):
        url = "/api/v1/news/%d/" % self.news_item.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        news = self.news_item
        category = response.data.pop("category")
        self.assertDictEqual(
            response.data,
            dict(
                id=news.pk,
                short_description=news.short_description(),
                title=news.title,
                description=news.description,
                link=news.link,
                org=news.org_id,
                created_on=news.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        )
        self.assertDictEqual(
            dict(category),
            dict(name=news.category.name, image_url=CategoryReadSerializer().get_image_url(news.category)),
        )

    def test_video_by_org_list(self):
        url = "/api/v1/videos/org/%d/" % self.uganda.pk
        url1 = "/api/v1/videos/org/%d/" % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], Video.objects.filter(org=self.uganda).count())
        response = self.client.get(url1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], Video.objects.filter(org=self.nigeria).count())

    def test_single_video(self):
        url = "/api/v1/videos/%d/" % self.uganda_video.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        video = self.uganda_video
        category = response.data.pop("category")
        self.assertDictEqual(
            response.data,
            dict(
                id=video.pk,
                title=video.title,
                video_id=video.video_id,
                description=video.description,
                org=video.org_id,
                created_on=video.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        )
        self.assertDictEqual(
            dict(category),
            dict(name=video.category.name, image_url=CategoryReadSerializer().get_image_url(video.category)),
        )

    def test_story_by_org_list(self):
        url = "/api/v1/stories/org/%d/" % self.uganda.pk
        url1 = "/api/v1/stories/org/%d/" % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], Story.objects.filter(org=self.uganda).count())
        response = self.client.get(url1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], Story.objects.filter(org=self.nigeria).count())

    def test_single_story(self):
        url = "/api/v1/stories/%d/" % self.uganda_story.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        story = self.uganda_story
        category = response.data.pop("category")
        self.assertDictEqual(
            response.data,
            dict(
                id=story.pk,
                title=story.title,
                video_id=story.video_id,
                audio_link=story.audio_link,
                summary=story.summary,
                content=story.content,
                featured=story.featured,
                tags=story.tags,
                images=StoryReadSerializer().get_images(story),
                org=story.org_id,
                created_on=story.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        )
        self.assertDictEqual(
            dict(category),
            dict(name=story.category.name, image_url=CategoryReadSerializer().get_image_url(story.category)),
        )

    def test_single_story_with_fields_parameter(self):
        url = "/api/v1/stories/%d/?fields=%s" % (self.uganda_story.pk, "content")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        story = self.uganda_story
        self.assertDictEqual(
            response.data,
            dict(
                content=story.content,
            ),
        )

    def test_single_story_with_exclude_parameter(self):
        url = "/api/v1/stories/%d/?exclude=%s,%s,%s,%s" % (
            self.uganda_story.pk,
            "content",
            "featured",
            "images",
            "category",
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        story = self.uganda_story
        self.assertDictEqual(
            response.data,
            dict(
                id=story.pk,
                title=story.title,
                video_id=story.video_id,
                audio_link=story.audio_link,
                summary=story.summary,
                tags=story.tags,
                org=story.org_id,
                created_on=story.created_on.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ),
        )

    def test_dashblock_by_org_list(self):
        url_uganda = "/api/v1/dashblocks/org/%d/" % self.uganda.pk
        url_nigeria = "/api/v1/dashblocks/org/%d/" % self.nigeria.pk
        response = self.client.get(url_uganda)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], DashBlock.objects.filter(org=self.uganda).count())
        response = self.client.get(url_nigeria)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], DashBlock.objects.filter(org=self.nigeria).count())

        response = self.client.get(url_uganda + "?dashblock_type=foo")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["count"], DashBlock.objects.filter(org=self.uganda, dashblock_type__slug="foo").count()
        )

    def test_single_dashblock(self):
        url = "/api/v1/dashblocks/%d/" % self.dashblock1.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dashblock = self.dashblock1

        self.assertDictEqual(
            response.data,
            dict(
                id=dashblock.pk,
                org=dashblock.org.pk,
                dashblock_type=dashblock.dashblock_type.slug,
                priority=dashblock.priority,
                title=dashblock.title,
                summary=dashblock.summary,
                content=dashblock.content,
                image_url=None,
                color=dashblock.color,
                path=dashblock.link,
                video_id=dashblock.video_id,
                tags=dashblock.tags,
            ),
        )
