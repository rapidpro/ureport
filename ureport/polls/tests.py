# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import uuid
import zoneinfo
from datetime import datetime, timedelta, timezone as tzone

import six
from mock import Mock, patch
from temba_client.exceptions import TembaRateExceededError

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Count, ExpressionWrapper, F, IntegerField, Sum, TextField, Value
from django.db.models.functions import Cast, ExtractYear
from django.http import HttpRequest
from django.template import TemplateSyntaxError
from django.urls import reverse
from django.utils import timezone

from dash.categories.fields import CategoryChoiceField
from dash.categories.models import Category, CategoryImage
from dash.orgs.models import TaskState
from dash.tags.models import Tag
from ureport.flows.models import FlowResultCategory
from ureport.locations.models import Boundary
from ureport.polls.models import Poll, PollImage, PollQuestion, PollResponseCategory, PollResult
from ureport.polls.tasks import (
    backfill_poll_results,
    fetch_old_sites_count,
    pull_refresh,
    pull_results_main_poll,
    pull_results_other_polls,
    rebuild_counts,
    recheck_poll_flow_data,
    refresh_org_flows,
    update_or_create_questions,
    update_results_age_gender,
)
from ureport.polls.templatetags.ureport import question_segmented_results
from ureport.stats.models import (
    AgeSegment,
    ContactActivity,
    ContactActivityCounter,
    GenderSegment,
    PollStats,
    PollWordCloud,
)
from ureport.tests import MockTembaClient, TestBackend, UreportTest
from ureport.utils import datetime_to_json_date, json_date_to_datetime


class PollTest(UreportTest):
    def setUp(self):
        super(PollTest, self).setUp()
        self.health_uganda = Category.objects.create(
            org=self.uganda, name="Health", created_by=self.admin, modified_by=self.admin
        )

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

        self.tag_uganda = Tag.objects.create(
            org=self.uganda, name="sports", created_by=self.admin, modified_by=self.admin
        )
        self.tag_nigeria = Tag.objects.create(
            org=self.nigeria, name="news", created_by=self.admin, modified_by=self.admin
        )

    @patch("ureport.polls.tasks.update_or_create_questions.delay")
    def test_poll_update_or_create_questions_task(self, mock_task_delay):
        poll1 = self.create_poll(self.uganda, "Poll 1", "flow-uuid-1", self.health_uganda, self.admin)
        poll2 = self.create_poll(self.uganda, "Poll 2", "flow-uuid-2", self.health_uganda, self.admin)

        Poll.update_or_create_questions_task([poll1, poll2])

        mock_task_delay.assert_called_once_with([poll1.pk, poll2.pk])

    def test_poll_pull_refresh(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

        pull_refresh_url = reverse("polls.poll_pull_refresh", args=[poll1.pk])

        post_data = dict(poll=poll1.pk)

        with patch("ureport.polls.models.Poll.pull_refresh_task") as mock_pull_refresh:
            mock_pull_refresh.return_value = "Done"

            response = self.client.get(pull_refresh_url, SERVER_NAME="uganda.ureport.io")
            self.assertLoginRedirect(response)

            response = self.client.post(pull_refresh_url, post_data, SERVER_NAME="uganda.ureport.io")
            self.assertLoginRedirect(response)

            self.login(self.admin)

            response = self.client.get(pull_refresh_url, SERVER_NAME="uganda.ureport.io")
            self.assertLoginRedirect(response)

            response = self.client.post(pull_refresh_url, post_data, SERVER_NAME="uganda.ureport.io")
            self.assertLoginRedirect(response)

            self.login(self.superuser)

            response = self.client.post(pull_refresh_url, post_data, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 302)
            mock_pull_refresh.assert_called_once_with()
            mock_pull_refresh.reset_mock()

            response = self.client.post(pull_refresh_url, post_data, SERVER_NAME="uganda.ureport.io", follow=True)

            self.assertEqual(response.context["org"], self.uganda)
            self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_list"))
            self.assertContains(
                response, "Scheduled a pull refresh for poll #%d on org #%d" % (poll1.pk, poll1.org_id)
            )

            mock_pull_refresh.assert_called_once_with()

    @patch("ureport.polls.tasks.pull_refresh.apply_async")
    @patch("django.core.cache.cache.set")
    def test_pull_refresh_task(self, mock_cache_set, mock_pull_refresh):
        tz = zoneinfo.ZoneInfo("Africa/Kigali")
        with patch.object(timezone, "now", return_value=datetime(2015, 9, 4, 3, 4, 5, 0, tzinfo=tz)):
            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

            poll1.pull_refresh_task()

            now = timezone.now()
            mock_cache_set.assert_called_once_with(
                Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (poll1.org_id, poll1.pk),
                datetime_to_json_date(now.replace(tzinfo=tzone.utc)),
                None,
            )

            mock_pull_refresh.assert_called_once_with((poll1.pk,), queue="sync")

    def test_get_public_polls(self):
        self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)
        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", self.health_uganda, self.admin, has_synced=True)

        self.create_poll(self.nigeria, "Poll 3", "uuid-3", self.education_nigeria, self.admin, has_synced=True)

        self.create_poll(self.nigeria, "Poll 4", "", self.education_nigeria, self.admin, has_synced=True)

        self.assertTrue(Poll.get_public_polls(self.uganda))
        self.assertEqual(Poll.get_public_polls(self.uganda).count(), 1)
        self.assertTrue(poll2 in Poll.get_public_polls(self.uganda))

        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertFalse(Poll.get_public_polls(self.uganda))

        poll2.published = False
        poll2.save()

        self.assertFalse(Poll.get_public_polls(self.uganda))

        self.health_uganda.is_active = True
        self.health_uganda.save()

        poll2.is_active = False
        poll2.save()

        self.assertFalse(Poll.get_public_polls(self.uganda))

    def test_get_valid_polls(self):
        self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)
        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", self.health_uganda, self.admin, has_synced=True)

        self.create_poll(self.nigeria, "Poll 3", "uuid-3", self.education_nigeria, self.admin, has_synced=True)

        self.create_poll(self.nigeria, "Poll 4", "", self.education_nigeria, self.admin, has_synced=True)

        self.assertTrue(Poll.get_valid_polls(self.uganda))
        self.assertEqual(Poll.get_valid_polls(self.uganda).count(), 1)
        self.assertTrue(poll2 in Poll.get_valid_polls(self.uganda))

        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertTrue(poll2 in Poll.get_valid_polls(self.uganda))

        poll2.published = False
        poll2.save()

        self.assertTrue(poll2 in Poll.get_valid_polls(self.uganda))

        self.health_uganda.is_active = True
        self.health_uganda.save()

        poll2.published = True
        poll2.is_active = False
        poll2.save()

        self.assertFalse(Poll.get_valid_polls(self.uganda))

    def test_poll_find_main_poll(self):
        self.assertIsNone(Poll.find_main_poll(self.uganda))
        self.assertIsNone(Poll.find_main_poll(self.nigeria))

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, has_synced=True)

        self.assertEqual(six.text_type(poll1), "Poll 1")

        self.assertIsNone(Poll.find_main_poll(self.uganda))
        self.assertIsNone(Poll.find_main_poll(self.nigeria))

        self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")

        self.assertEqual(Poll.find_main_poll(self.uganda), poll1)
        self.assertIsNone(Poll.find_main_poll(self.nigeria))

        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", self.health_uganda, self.admin, has_synced=True)

        self.create_poll_question(self.admin, poll2, "question poll 2", "uuid-202")

        self.assertEqual(Poll.find_main_poll(self.uganda), poll2)
        self.assertIsNone(Poll.find_main_poll(self.nigeria))

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin, has_synced=True)

        self.create_poll_question(self.admin, poll3, "question poll 3", "uuid-303")

        self.assertEqual(Poll.find_main_poll(self.uganda), poll3)
        self.assertIsNone(Poll.find_main_poll(self.nigeria))

        poll1.is_featured = True
        poll1.save()

        self.assertEqual(Poll.find_main_poll(self.uganda), poll1)
        self.assertIsNone(Poll.find_main_poll(self.nigeria))

        poll1.is_active = False
        poll1.save()

        self.assertEqual(Poll.find_main_poll(self.uganda), poll3)
        self.assertIsNone(Poll.find_main_poll(self.nigeria))

        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertIsNone(Poll.find_main_poll(self.uganda))
        self.assertIsNone(Poll.find_main_poll(self.nigeria))

    @patch("django.core.cache.cache.get")
    def test_get_other_polls(self, mock_cache_get):
        mock_cache_get.return_value = None

        polls = []
        for i in range(10):
            poll = self.create_poll(
                self.uganda,
                "Poll %s" % i,
                "uuid-%s" % i,
                self.health_uganda,
                self.admin,
                featured=True,
                has_synced=True,
            )
            self.create_poll_question(self.admin, poll, "question poll %s" % i, "uuid-10-%s" % i)

            polls.append(poll)

        self.assertTrue(Poll.get_other_polls(self.uganda))
        self.assertEqual(
            list(Poll.get_other_polls(self.uganda)),
            [polls[8], polls[7], polls[6], polls[5], polls[4], polls[3], polls[2], polls[1], polls[0]],
        )

    @patch("django.core.cache.cache.get")
    def test_get_recent_polls(self, mock_cache_get):
        mock_cache_get.return_value = None

        polls = []
        for i in range(10):
            poll = self.create_poll(
                self.uganda,
                "Poll %s" % i,
                "uuid-%s" % i,
                self.health_uganda,
                self.admin,
                featured=True,
                has_synced=True,
            )
            self.create_poll_question(self.admin, poll, "question poll %s" % i, "uuid-10-%s" % i)

            polls.append(poll)

        self.assertTrue(Poll.get_recent_polls(self.uganda))
        self.assertEqual(list(Poll.get_recent_polls(self.uganda)), list(reversed(polls[:9])))

        now = timezone.now()
        two_month_ago = now - timedelta(days=60)

        Poll.objects.filter(pk__in=[polls[0].pk, polls[1].pk]).update(created_on=two_month_ago)

        self.assertTrue(Poll.get_recent_polls(self.uganda))
        self.assertEqual(list(Poll.get_recent_polls(self.uganda)), list(reversed(polls[2:9])))

    def test_get_flow(self):
        with patch("dash.orgs.models.Org.get_flows") as mock:
            mock.return_value = {"uuid-1": "Flow"}

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

            self.assertEqual(poll1.get_flow(), "Flow")
            mock.assert_called_once_with(backend=poll1.backend)

    def test_runs(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEqual(poll1.runs(), "----")

        self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")

        with patch("ureport.polls.models.PollQuestion.get_polled") as mock:
            mock.return_value = 100

            self.assertEqual(poll1.runs(), 100)
            mock.assert_called_with()

    def test_responded_runs(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEqual(poll1.responded_runs(), "---")

        self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")

        with patch("ureport.polls.models.PollQuestion.get_responded") as mock:
            mock.return_value = 40

            self.assertEqual(poll1.responded_runs(), 40)
            mock.assert_called_once_with()

    def test_response_percentage(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEqual(poll1.response_percentage(), "---")

        self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")
        with patch("ureport.polls.models.PollQuestion.get_response_percentage") as mock_response_percentage:
            mock_response_percentage.return_value = "40%"

            self.assertEqual(poll1.response_percentage(), "40%")
            mock_response_percentage.assert_called_with()

    def test_get_featured_images(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertFalse(poll1.get_featured_images())

        poll_image1 = PollImage.objects.create(
            name="image 1", poll=poll1, created_by=self.admin, modified_by=self.admin
        )

        self.assertEqual(six.text_type(poll_image1), "Poll 1 - image 1")

        self.assertFalse(poll1.get_featured_images())

        poll_image1.image = "polls/image.jpg"
        poll_image1.is_active = False
        poll_image1.save()

        self.assertFalse(poll1.get_featured_images())

        poll_image1.is_active = True
        poll_image1.save()

        self.assertTrue(poll1.get_featured_images())
        self.assertTrue(poll_image1 in poll1.get_featured_images())
        self.assertEqual(len(poll1.get_featured_images()), 1)

    def test_get_categoryimage(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEqual(poll1.get_category_image(), self.health_uganda.get_first_image())

        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertIsNone(poll1.get_category_image())

        self.health_uganda.is_active = True
        self.health_uganda.save()

        self.assertEqual(poll1.get_category_image(), self.health_uganda.get_first_image())

        category_image1 = CategoryImage.objects.create(
            category=self.health_uganda,
            name="image 1",
            image="categories/some_image.jpg",
            created_by=self.admin,
            modified_by=self.admin,
        )

        poll1.category_image = category_image1
        poll1.save()

        self.assertEqual(poll1.get_category_image(), poll1.category_image.image)

    @patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_create_poll(self):
        create_url = reverse("polls.poll_create")

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        with patch("dash.orgs.models.Org.get_flows") as mock_get_flows:
            flows_cached = dict()
            flows_cached["uuid-25"] = dict(
                runs=300,
                completed_runs=120,
                name="Flow 1",
                uuid="uuid-25",
                participants=None,
                labels="",
                archived=False,
                created_on="2015-04-08T08:30:40.000Z",
                date_hint="2015-04-08",
                results=[
                    dict(
                        key="color",
                        name="Color",
                        categories=["Orange", "Blue", "Other", "Nothing"],
                        node_uuids=["42a8e177-9e88-429b-b70a-7d4854423092"],
                    )
                ],
                rulesets=[dict(uuid="uuid-8435", id=8435, response_type="C", label="Does your community have power")],
            )

            self.login(self.admin)
            response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 200)
            self.assertIn("form", response.context)

            self.assertEqual(len(response.context["form"].fields), 6)
            self.assertIn("is_featured", response.context["form"].fields)
            self.assertIn("title", response.context["form"].fields)
            self.assertIn("category", response.context["form"].fields)
            self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
            self.assertEqual(
                list(response.context["form"].fields["category"].choices),
                [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
            )
            self.assertIn("category_image", response.context["form"].fields)
            self.assertIn("poll_tags", response.context["form"].fields)
            self.assertIn("loc", response.context["form"].fields)

            response = self.client.post(create_url, dict(), SERVER_NAME="uganda.ureport.io")
            self.assertTrue(response.context["form"].errors)

            self.assertEqual(len(response.context["form"].errors), 2)
            self.assertIn("title", response.context["form"].errors)
            self.assertIn("category", response.context["form"].errors)
            self.assertFalse(Poll.objects.all())

            post_data = dict(
                title="Poll 1", category=self.health_uganda.pk, poll_tags=[self.tag_uganda.pk, "[NEW_TAG]_Books"]
            )

            response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
            self.assertTrue(Poll.objects.all())

            poll = Poll.objects.get()
            self.assertEqual(poll.title, "Poll 1")
            self.assertEqual(poll.backend.slug, "rapidpro")
            self.assertEqual(poll.org, self.uganda)

            self.assertEqual(poll.tags.all().count(), 2)
            self.assertEqual(set(poll.tags.all().values_list("name", flat=True)), {"Books", "sports"})

            self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_poll_flow", args=[poll.pk]))

            self.assertEqual(Poll.objects.all().count(), 1)

            # new submission should not create a new poll
            post_data = dict(title="Poll 1", category=self.health_uganda.pk)
            response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(Poll.objects.all().count(), 1)

            ten_minutes_ago = timezone.now() - timedelta(minutes=10)

            # a new submission after five minutes will create a new poll
            Poll.objects.filter(org=poll.org, backend__slug="rapidpro").update(
                created_on=ten_minutes_ago, flow_uuid="uuid-25"
            )
            response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(Poll.objects.all().count(), 2)

            Poll.objects.filter(org=poll.org, backend__slug="rapidpro").update(flow_uuid="uuid-25")
            tz = zoneinfo.ZoneInfo("Africa/Kigali")
            with patch.object(timezone, "now", return_value=datetime(2015, 9, 4, 3, 4, 5, 0, tzinfo=tz)):
                flows_cached["uuid-30"] = dict(
                    runs=300,
                    completed_runs=120,
                    name="Flow 2",
                    uuid="uuid-30",
                    labels="",
                    archived=False,
                    date_hint="2015-04-08",
                    participants=None,
                    results=[
                        dict(
                            key="color",
                            name="Color",
                            categories=["Orange", "Blue", "Other", "Nothing"],
                            node_uuids=["42a8e177-9e88-429b-b70a-7d4854423092"],
                        )
                    ],
                    rulesets=[
                        dict(uuid="uuid-8435", id=8436, response_type="C", label="Does your community have power")
                    ],
                )

                mock_get_flows.return_value = flows_cached

                post_data = dict(title="Poll 2", category=self.health_uganda.pk)
                response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
                self.assertEqual(Poll.objects.all().count(), 3)

                poll = Poll.objects.get(title="Poll 2")
                self.assertEqual(poll.org, self.uganda)
                self.assertEqual(poll.poll_date, json_date_to_datetime("2015-09-04T01:04:05.000Z"))

                Poll.objects.filter(org=poll.org, backend__slug="rapidpro").update(flow_uuid="uuid-25")

                response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
                self.assertEqual(response.status_code, 200)
                self.assertIn("form", response.context)

                self.assertEqual(len(response.context["form"].fields), 6)
                self.assertNotIn("backend", response.context["form"].fields)

                # add the config for a second backend
                floip_backend = self.uganda.backends.create(
                    slug="floip",
                    api_token="floip_token",
                    backend_type="ureport.backend.rapidpro.RapidProBackend",
                    host="http://localhost:8001",
                    created_by=self.admin,
                    modified_by=self.admin,
                )

                response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
                self.assertEqual(response.status_code, 200)
                self.assertIn("form", response.context)

                self.assertEqual(len(response.context["form"].fields), 7)
                self.assertIn("is_featured", response.context["form"].fields)
                self.assertIn("title", response.context["form"].fields)
                self.assertIn("category", response.context["form"].fields)
                self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
                self.assertEqual(
                    list(response.context["form"].fields["category"].choices),
                    [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
                )
                self.assertIn("category_image", response.context["form"].fields)
                self.assertIn("poll_tags", response.context["form"].fields)
                self.assertIn("loc", response.context["form"].fields)

                self.assertIn("backend", response.context["form"].fields)
                self.assertEqual(len(response.context["form"].fields["backend"].choices), 3)
                self.assertEqual(
                    set(
                        [
                            (getattr(elt[0], "value", ""), elt[1])
                            for elt in response.context["form"].fields["backend"].choices
                        ]
                    ),
                    set([("", "---------"), (poll.backend.pk, "rapidpro"), (floip_backend.pk, "floip")]),
                )

    @patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_poll_poll_flow_view(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "", self.health_uganda, self.admin, featured=True)

        uganda_poll_flow_url = reverse("polls.poll_poll_flow", args=[poll1.pk])

        response = self.client.get(uganda_poll_flow_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        with patch("dash.orgs.models.Org.get_flows") as mock_get_flows:
            flows_cached = dict()
            flows_cached["uuid-25"] = dict(
                runs=300,
                completed_runs=120,
                name="Flow 1",
                uuid="uuid-25",
                participants=None,
                labels="",
                archived=False,
                created_on="2015-04-08T08:30:40.000Z",
                date_hint="2015-04-08",
                results=[
                    dict(
                        key="color",
                        name="Color",
                        categories=["Orange", "Blue", "Other", "Nothing"],
                        node_uuids=["42a8e177-9e88-429b-b70a-7d4854423092"],
                    )
                ],
                rulesets=[dict(uuid="uuid-8435", id=8435, response_type="C", label="Does your community have power")],
            )

            mock_get_flows.return_value = flows_cached

            self.login(self.admin)
            self.assertFalse(poll1.flow_uuid)
            response = self.client.get(uganda_poll_flow_url, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 200)
            self.assertTrue("form" in response.context)

            self.assertEqual(len(response.context["form"].fields), 2)
            self.assertTrue("loc" in response.context["form"].fields)
            self.assertTrue("flow_uuid" in response.context["form"].fields)
            self.assertEqual(len(response.context["form"].fields["flow_uuid"].choices), 1)
            self.assertEqual(response.context["form"].fields["flow_uuid"].choices[0][0], "uuid-25")
            self.assertEqual(response.context["form"].fields["flow_uuid"].choices[0][1], "Flow 1 (2015-04-08)")

            post_data = dict(flow_uuid="uuid-25")
            response = self.client.post(uganda_poll_flow_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 200)

            poll = Poll.objects.get(pk=poll1.pk)
            self.assertEqual(poll.flow_uuid, "uuid-25")

            self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_poll_date", args=[poll.pk]))

            response = self.client.get(uganda_poll_flow_url, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 302)

            response = self.client.get(uganda_poll_flow_url, follow=True, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_poll_date", args=[poll.pk]))

    def test_poll_poll_date_view(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

        uganda_poll_date_url = reverse("polls.poll_poll_date", args=[poll1.pk])
        nigeria_poll_date_url = reverse("polls.poll_poll_date", args=[poll2.pk])

        response = self.client.get(uganda_poll_date_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_poll_date_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_poll_date_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        with patch("dash.orgs.models.Org.get_flows") as mock_get_flows:
            flows_cached = dict()
            flows_cached["uuid-1"] = dict(
                runs=300,
                completed_runs=120,
                name="Flow 1",
                uuid="uuid-1",
                labels="",
                archived=False,
                created_on="2015-04-08T12:48:44.320Z",
                date_hint="2015-04-08",
                participants=None,
                results=[
                    dict(
                        key="color",
                        name="Color",
                        categories=["Orange", "Blue", "Other", "Nothing"],
                        node_uuids=["42a8e177-9e88-429b-b70a-7d4854423092"],
                    )
                ],
                rulesets=[dict(uuid="uuid-8435", id=8435, response_type="C", label="Does your community have power")],
            )

            mock_get_flows.return_value = flows_cached

            now = timezone.now()
            yesterday = now - timedelta(days=1)

            response = self.client.get(uganda_poll_date_url, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 200)
            self.assertTrue("form" in response.context)

            self.assertEqual(len(response.context["form"].fields), 2)

            self.assertTrue("poll_date" in response.context["form"].fields)
            self.assertTrue("loc" in response.context["form"].fields)

            post_data = dict(poll_date=yesterday.strftime("%Y-%m-%d %H:%M:%S"))
            response = self.client.post(uganda_poll_date_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")

            poll = Poll.objects.get(flow_uuid="uuid-1")
            self.assertEqual(poll.org, self.uganda)
            self.assertEqual(poll.title, "Poll 1")
            self.assertEqual(
                poll.poll_date.astimezone(self.uganda.timezone).replace(tzinfo=tzone.utc),
                yesterday.replace(microsecond=0),
            )

            self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_questions", args=[poll.pk]))

            tz = zoneinfo.ZoneInfo("Africa/Kigali")
            with patch.object(timezone, "now", return_value=datetime(2015, 9, 4, 3, 4, 5, 0, tzinfo=tz)):
                response = self.client.post(uganda_poll_date_url, dict(), follow=True, SERVER_NAME="uganda.ureport.io")

                poll = Poll.objects.get(flow_uuid="uuid-1")
                self.assertEqual(poll.org, self.uganda)
                self.assertEqual(poll.title, "Poll 1")
                self.assertEqual(poll.poll_date, json_date_to_datetime("2015-09-04T01:04:05.000Z"))

                self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_questions", args=[poll.pk]))

    @patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_update_poll(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

        uganda_update_url = reverse("polls.poll_update", args=[poll1.pk])
        nigeria_update_url = reverse("polls.poll_update", args=[poll2.pk])

        response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        with patch("dash.orgs.models.Org.get_flows") as mock_get_flows:
            flows_cached = dict()
            flows_cached["uuid-1"] = dict(
                runs=300,
                completed_runs=120,
                name="Flow 1",
                uuid="uuid-1",
                labels="",
                archived=False,
                created_on="2015-04-08T12:48:44.320Z",
                date_hint="2015-04-08",
                participants=None,
                results=[
                    dict(
                        key="color",
                        name="Color",
                        categories=["Orange", "Blue", "Other", "Nothing"],
                        node_uuids=["42a8e177-9e88-429b-b70a-7d4854423092"],
                    )
                ],
                rulesets=[dict(uuid="uuid-8435", id=8435, response_type="C", label="Does your community have power")],
            )

            mock_get_flows.return_value = flows_cached

            response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 200)
            self.assertIn("form", response.context)

            self.assertEqual(len(response.context["form"].fields), 7)
            self.assertIn("published", response.context["form"].fields)
            self.assertIn("is_featured", response.context["form"].fields)
            self.assertIn("title", response.context["form"].fields)
            self.assertIn("category", response.context["form"].fields)
            self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
            self.assertEqual(
                list(response.context["form"].fields["category"].choices),
                [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
            )
            self.assertIn("category_image", response.context["form"].fields)
            self.assertIn("poll_tags", response.context["form"].fields)
            self.assertIn("loc", response.context["form"].fields)

            self.assertEqual(response.context["tags_data"], [dict(id=self.tag_uganda.pk, text=self.tag_uganda.name)])

            response = self.client.post(uganda_update_url, dict(), SERVER_NAME="uganda.ureport.io")
            self.assertIn("form", response.context)
            self.assertTrue(response.context["form"].errors)
            self.assertEqual(len(response.context["form"].errors), 2)
            self.assertIn("title", response.context["form"].errors)
            self.assertIn("category", response.context["form"].errors)

            post_data = dict(title="title updated", category=self.health_uganda.pk, is_featured=False)
            response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
            updated_poll = Poll.objects.get(pk=poll1.pk)
            self.assertEqual(updated_poll.title, "title updated")
            self.assertFalse(updated_poll.is_featured)

            self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_poll_date", args=[updated_poll.pk]))

            post_data["poll_tags"] = [self.tag_uganda.pk, "[NEW_TAG]_Trending"]
            response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
            updated_poll = Poll.objects.get(pk=poll1.pk)
            self.assertEqual(updated_poll.title, "title updated")
            self.assertEqual(updated_poll.tags.all().count(), 2)
            self.assertEqual(set(updated_poll.tags.all().values_list("name", flat=True)), {"Trending", "sports"})

    def test_list_poll(self):
        list_url = reverse("polls.poll_list")
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["object_list"]), 1)
        self.assertFalse(poll2 in response.context["object_list"])
        self.assertTrue(poll1 in response.context["object_list"])

        self.assertContains(response, reverse("polls.poll_questions", args=[poll1.pk]))

        poll1.has_synced = True
        poll1.save()

        cache.set(
            Poll.POLL_RESULTS_LAST_SYNC_TIME_CACHE_KEY % (self.uganda.pk, poll1.flow_uuid),
            datetime_to_json_date(timezone.now() - timedelta(minutes=5)),
            None,
        )

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["object_list"]), 1)
        self.assertRegex(response.content.decode("utf-8"), "Last results synced 5(.*)minutes ago")

    @patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_questions_poll(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

        uganda_questions_url = reverse("polls.poll_questions", args=[poll1.pk])
        nigeria_questions_url = reverse("polls.poll_questions", args=[poll2.pk])

        response = self.client.get(uganda_questions_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_questions_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_questions_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_questions_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 0)

        self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")

        response = self.client.get(uganda_questions_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 6)
        self.assertTrue("ruleset_uuid-101_include" in response.context["form"].fields)
        self.assertTrue("ruleset_uuid-101_priority" in response.context["form"].fields)
        self.assertTrue("ruleset_uuid-101_label" in response.context["form"].fields)
        self.assertTrue("ruleset_uuid-101_title" in response.context["form"].fields)
        self.assertTrue("ruleset_uuid-101_color" in response.context["form"].fields)
        self.assertTrue("ruleset_uuid-101_hidden_charts" in response.context["form"].fields)
        self.assertEqual(response.context["form"].fields["ruleset_uuid-101_priority"].initial, 0)
        self.assertIsNone(response.context["form"].fields["ruleset_uuid-101_color"].initial)
        self.assertIsNone(response.context["form"].fields["ruleset_uuid-101_hidden_charts"].initial)
        self.assertEqual(response.context["form"].fields["ruleset_uuid-101_label"].initial, "question poll 1")
        self.assertEqual(response.context["form"].fields["ruleset_uuid-101_title"].initial, "question poll 1")
        self.assertContains(response, "The label of the ruleset from RapidPro")

        post_data = dict()
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue(response.context["form"].errors)
        self.assertTrue(response.context["form"].errors["__all__"][0], "You must include at least one poll question.")

        post_data = dict()
        post_data["ruleset_uuid-101_include"] = True
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue(response.context["form"].errors)
        self.assertTrue(
            response.context["form"].errors["__all__"][0], "You must include a title for every included question."
        )

        post_data = dict()
        post_data["ruleset_uuid-101_include"] = True
        post_data["ruleset_uuid-101_title"] = "hello " * 50
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue(response.context["form"].errors)
        self.assertTrue(
            response.context["form"].errors["__all__"][0],
            "Title too long. The max limit is 255 characters for each title",
        )

        post_data = dict()
        post_data["ruleset_uuid-101_include"] = True
        post_data["ruleset_uuid-101_title"] = "have electricity access"
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue(PollQuestion.objects.filter(poll=poll1))

        poll_question = PollQuestion.objects.filter(poll=poll1, ruleset_uuid="uuid-101")[0]
        self.assertEqual(poll_question.title, "have electricity access")
        self.assertEqual(poll_question.ruleset_label, "question poll 1")
        self.assertEqual(poll_question.priority, 0)

        self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_images", args=[poll1.pk]))

        post_data = dict()
        post_data["ruleset_uuid-101_include"] = True
        post_data["ruleset_uuid-101_title"] = "electricity network coverage"
        post_data["ruleset_uuid-101_priority"] = 5
        post_data["ruleset_uuid-101_color"] = "D1"
        post_data["ruleset_uuid-101_hidden_charts"] = "GL"
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")

        self.assertTrue(PollQuestion.objects.filter(poll=poll1))

        poll_question = PollQuestion.objects.filter(poll=poll1)[0]
        self.assertEqual(poll_question.title, "electricity network coverage")
        self.assertEqual(poll_question.ruleset_label, "question poll 1")
        self.assertEqual(poll_question.priority, 5)
        self.assertEqual(poll_question.color_choice, "D1")
        self.assertTrue(poll_question.show_age())
        self.assertFalse(poll_question.show_gender())
        self.assertFalse(poll_question.show_locations())
        self.assertFalse(poll_question.hide_all_chart_pills())
        self.assertEqual(poll_question.get_last_pill(), "age")

    def test_images_poll(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

        uganda_poll_images_url = reverse("polls.poll_images", args=[poll1.pk])
        nigeria_poll_images_url = reverse("polls.poll_images", args=[poll2.pk])

        response = self.client.get(uganda_poll_images_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_poll_images_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_poll_images_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_poll_images_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 3)
        for field in response.context["form"].fields:
            self.assertFalse(response.context["form"].fields[field].initial)

        self.assertFalse(PollImage.objects.filter(poll=poll1))

        upload = open("test-data/image.jpg", "rb")
        post_data = dict(image_1=upload)
        response = self.client.post(uganda_poll_images_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue(PollImage.objects.filter(poll=poll1))
        self.assertEqual(PollImage.objects.filter(poll=poll1).count(), 1)

        response = self.client.get(uganda_poll_images_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["form"].fields), 3)
        self.assertTrue(response.context["form"].fields["image_1"].initial)

        upload = open("test-data/image.jpg", "rb")
        post_data = dict(image_1=upload)
        response = self.client.post(uganda_poll_images_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue(PollImage.objects.filter(poll=poll1))
        self.assertEqual(PollImage.objects.filter(poll=poll1).count(), 1)

        self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_responses", args=[poll1.pk]))

    def test_responses_poll(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, featured=True)

        uganda_poll_responses_url = reverse("polls.poll_responses", args=[poll1.pk])
        nigeria_poll_responses_url = reverse("polls.poll_responses", args=[poll2.pk])

        response = self.client.get(uganda_poll_responses_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_poll_responses_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_poll_responses_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_poll_responses_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 4)
        for field in response.context["form"].fields.values():
            self.assertFalse(field.initial)

        response = self.client.post(uganda_poll_responses_url, dict(), follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertFalse("form" in response.context)
        self.assertFalse(poll1.response_title)
        self.assertFalse(poll1.response_author)
        self.assertFalse(poll1.response_content)

        post_data = dict(
            response_author="Pink Floyd", response_title="Youtube Stream", response_content="Just give me a reason"
        )

        response = self.client.post(uganda_poll_responses_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertFalse("form" in response.context)

        poll1.refresh_from_db()
        self.assertEqual(poll1.response_title, "Youtube Stream")
        self.assertEqual(poll1.response_author, "Pink Floyd")
        self.assertEqual(poll1.response_content, "Just give me a reason")

        response = self.client.get(uganda_poll_responses_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 4)
        self.assertTrue("response_author" in response.context["form"].fields)
        self.assertTrue("response_title" in response.context["form"].fields)
        self.assertTrue("response_content" in response.context["form"].fields)

    @patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_templatetags(self):
        from ureport.polls.templatetags.ureport import (
            config,
            org_arrow_link,
            org_color,
            org_host_link,
            question_results,
            show_org_flags,
            transparency,
        )

        with patch("dash.orgs.models.Org.get_config") as mock:
            mock.return_value = "Done"

            self.assertIsNone(config(None, "field_name"))
            self.assertEqual(config(self.uganda, "field_name"), "Done")
            mock.assert_called_with("field_name")

        self.assertIsNone(org_color(None, 1))
        self.assertEqual(org_color(self.uganda, 0), "#E4002B")
        self.assertEqual(org_color(self.uganda, 1), "#FF8200")
        self.assertEqual(org_color(self.uganda, 2), "#FFD100")
        self.assertEqual(org_color(self.uganda, 3), "#009A17")

        self.uganda.set_config("common.colors", "#cccccc, #dddddd, #eeeeee, #111111, #222222, #333333, #444444")

        self.assertEqual(org_color(self.uganda, 0), "#CCCCCC")
        self.assertEqual(org_color(self.uganda, 1), "#DDDDDD")
        self.assertEqual(org_color(self.uganda, 2), "#EEEEEE")
        self.assertEqual(org_color(self.uganda, 3), "#111111")
        self.assertEqual(org_color(self.uganda, 4), "#222222")
        self.assertEqual(org_color(self.uganda, 5), "#333333")
        self.assertEqual(org_color(self.uganda, 6), "#444444")
        self.assertEqual(org_color(self.uganda, 7), "#CCCCCC")
        self.assertEqual(org_color(self.uganda, 8), "#DDDDDD")
        self.assertEqual(org_color(self.uganda, 9), "#EEEEEE")
        self.assertEqual(org_color(self.uganda, 10), "#111111")
        self.assertEqual(org_color(self.uganda, 11), "#222222")

        self.assertIsNone(transparency(None, 0.8))
        self.assertEqual(transparency("#808080", 0.7), "rgba(128, 128, 128, 0.7)")

        with self.assertRaises(TemplateSyntaxError):
            transparency("#abc", 0.5)

        with patch("ureport.polls.templatetags.ureport.get_linked_orgs") as mock_get_linked_orgs:
            mock_get_linked_orgs.return_value = ["linked_org"]

            request = Mock(spec=HttpRequest)
            request.user = Mock(spec=User, is_authenticated=True)

            show_org_flags(dict(is_iorg=True, request=request, is_new_brand=True))
            mock_get_linked_orgs.assert_called_with(True)

            request.user = Mock(spec=User, is_authenticated=False)
            show_org_flags(dict(is_iorg=True, request=request, is_new_brand=True))
            mock_get_linked_orgs.assert_called_with(False)

        request = Mock(spec=HttpRequest)
        request.user = get_user_model().objects.get(pk=1)

        with patch("django.contrib.auth.models.User.is_authenticated") as mock_authenticated:
            mock_authenticated.return_value = True

            self.assertEqual(org_host_link(dict(request=request)), "https://ureport.io")

            request.org = self.nigeria
            self.assertEqual(org_host_link(dict(request=request)), "http://nigeria.ureport.io")

            with self.settings(SESSION_COOKIE_SECURE=True):
                self.assertEqual(org_host_link(dict(request=request)), "https://nigeria.ureport.io")

            self.nigeria.domain = "ureport.ng"
            self.nigeria.save()

            self.assertEqual(org_host_link(dict(request=request)), "http://nigeria.ureport.io")

            with self.settings(SESSION_COOKIE_SECURE=True):
                self.assertEqual(org_host_link(dict(request=request)), "https://nigeria.ureport.io")

        self.assertIsNone(org_arrow_link(org=None))
        self.assertEqual(org_arrow_link(self.uganda), "&#8594;")

        self.uganda.language = "ar"
        self.uganda.save()

        self.assertEqual(org_arrow_link(self.uganda), "&#8592;")

        self.assertFalse(question_results(None))

        with patch("ureport.polls.models.PollQuestion.get_results") as mock_results:
            mock_results.return_value = ["Results"]

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

            poll1_question = self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")

            self.assertEqual(question_results(poll1_question), "Results")

            mock_results.side_effect = KeyError

            self.assertFalse(question_results(poll1_question))

        with patch("ureport.polls.models.PollQuestion.get_results") as mock_results:
            mock_results.return_value = ["Results"]

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

            poll1_question = self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")
            self.assertEqual(question_segmented_results(poll1_question, "gender"), ["Results"])

            mock_results.side_effect = KeyError

            self.assertFalse(question_segmented_results(poll1_question, "gender"))

    def test_delete_poll_stats(self):
        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        poll_question = self.create_poll_question(self.admin, poll, "question 1", "step-uuid")

        self.assertFalse(PollStats.objects.all())

        PollResult.objects.create(
            org=self.nigeria,
            flow=poll.flow_uuid,
            ruleset=poll_question.flow_result.result_uuid,
            date=timezone.now(),
            contact="contact-uuid",
            completed=False,
        )

        with self.settings(
            CACHES={
                "default": {
                    "BACKEND": "django_valkey.cache.ValkeyCache",
                    "LOCATION": "redis://127.0.0.1:6379/1",
                }
            }
        ):
            poll.rebuild_poll_results_counts()

            self.assertTrue(PollStats.objects.all())

            poll.stopped_syncing = True
            poll.save()

            poll.delete_poll_stats()

            self.assertTrue(PollStats.objects.all())

            poll.stopped_syncing = False
            poll.save()

            poll.delete_poll_stats()
            self.assertFalse(PollStats.objects.all())

            poll2 = self.create_poll(self.nigeria, "Poll 2", "flow-uuid", self.education_nigeria, self.admin)
            poll_question2 = self.create_poll_question(self.admin, poll2, "question 1", "step-uuid")

            self.assertFalse(PollStats.objects.all())
            self.assertFalse(PollStats.objects.filter(flow_result_id=poll_question.flow_result_id))
            self.assertFalse(PollStats.objects.filter(flow_result_id=poll_question2.flow_result_id))

            # rebuild for first poll will rebuild for poll2 as well
            poll.rebuild_poll_results_counts()

            self.assertTrue(PollStats.objects.all())
            self.assertTrue(PollStats.objects.filter(flow_result_id=poll_question.flow_result_id))
            self.assertTrue(PollStats.objects.filter(flow_result_id=poll_question2.flow_result_id))

    def test_delete_poll_results(self):
        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        poll_question = self.create_poll_question(self.admin, poll, "question 1", "step-uuid")

        PollResult.objects.create(
            org=self.nigeria,
            flow=poll.flow_uuid,
            ruleset=poll_question.flow_result.result_uuid,
            date=timezone.now(),
            contact="contact-uuid",
            completed=False,
        )

        poll.delete_poll_results()

        self.assertFalse(PollResult.objects.filter(org=self.nigeria, flow=poll.flow_uuid))

    @patch("ureport.polls.tasks.pull_refresh_from_archives.apply_async")
    @patch("ureport.polls.models.Poll.get_flow_date")
    @patch("dash.orgs.models.Org.get_backend")
    @patch("ureport.tests.TestBackend.pull_results")
    def test_poll_pull_results(
        self, mock_pull_results, mock_get_backend, mock_poll_flow_date, mock_pull_refresh_from_archives_task
    ):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)
        mock_poll_flow_date.return_value = None

        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        self.assertFalse(poll.has_synced)
        Poll.pull_results(poll.pk)

        poll = Poll.objects.get(pk=poll.pk)
        self.assertTrue(poll.has_synced)

        mock_pull_refresh_from_archives_task.assert_called_once_with((poll.pk,), queue="sync")

        self.assertEqual(mock_get_backend.call_args[1], {"backend_slug": "rapidpro"})
        mock_pull_results.assert_called_once()

    @patch("ureport.polls.tasks.pull_refresh_from_archives.apply_async")
    @patch("ureport.polls.models.Poll.get_flow_date")
    @patch("dash.orgs.models.Org.get_backend")
    @patch("ureport.tests.TestBackend.pull_results")
    def test_poll_pull_results_old_flows(
        self, mock_pull_results, mock_get_backend, mock_poll_flow_date, mock_pull_refresh_from_archives_task
    ):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

        mock_poll_flow_date.return_value = datetime_to_json_date(timezone.now() - timedelta(days=88))
        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        self.assertFalse(poll.has_synced)
        Poll.pull_results(poll.pk)

        poll = Poll.objects.get(pk=poll.pk)
        self.assertTrue(poll.has_synced)

        self.assertFalse(mock_pull_refresh_from_archives_task.called)

        poll.has_synced = False
        poll.save()

        mock_pull_results.reset_mock()
        mock_poll_flow_date.return_value = datetime_to_json_date(timezone.now() - timedelta(days=91))

        self.assertFalse(poll.has_synced)
        Poll.pull_results(poll.pk)

        poll = Poll.objects.get(pk=poll.pk)
        self.assertTrue(poll.has_synced)

        mock_pull_refresh_from_archives_task.assert_called_once_with((poll.pk,), queue="sync")

        self.assertEqual(mock_get_backend.call_args[1], {"backend_slug": "rapidpro"})
        mock_pull_results.assert_called_once()


class PollQuestionTest(UreportTest):
    def setUp(self):
        super(PollQuestionTest, self).setUp()
        self.health_uganda = Category.objects.create(
            org=self.uganda, name="Health", created_by=self.admin, modified_by=self.admin
        )

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

    def assertResult(self, result, index, category, count):
        self.assertEqual(count, result["categories"][index]["count"])
        self.assertEqual(category, result["categories"][index]["label"])

    def test_poll_question_category_order(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll_question1 = self.create_poll_question(self.admin, poll1, "question 1", "uuid-101")

        self.create_poll_response_category(poll_question1, "rule-uuid-1", "Yes")
        self.create_poll_response_category(poll_question1, "rule-uuid-2", "No")

        calculated_results = [
            dict(open_ended=False, set=0, unset=0, categories=[dict(count=0, label="Yes"), dict(count=0, label="No")])
        ]

        self.assertEqual(poll_question1.calculate_results(), calculated_results)

        PollResponseCategory.objects.all().delete()
        self.create_poll_response_category(poll_question1, "rule-uuid-2", "No")
        self.create_poll_response_category(poll_question1, "rule-uuid-1", "Yes")

        calculated_results = [
            dict(open_ended=False, set=0, unset=0, categories=[dict(count=0, label="No"), dict(count=0, label="Yes")])
        ]

        self.assertEqual(poll_question1.calculate_results(), calculated_results)

    def test_poll_question_model(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll_question1 = self.create_poll_question(self.admin, poll1, "question 1", "uuid-101")

        self.assertEqual(six.text_type(poll_question1), "question 1")

        # no response category are ignored
        self.create_poll_response_category(poll_question1, "rule-uuid-4", "No Response")

        self.assertFalse(poll_question1.is_open_ended())

        self.create_poll_response_category(poll_question1, "rule-uuid-1", "Yes")

        self.assertTrue(poll_question1.is_open_ended())

        self.create_poll_response_category(poll_question1, "rule-uuid-2", "No")
        PollResponseCategory.objects.filter(category="No").update(is_active=False)
        FlowResultCategory.objects.filter(category="No").update(is_active=False)

        self.assertTrue(poll_question1.is_open_ended())

        PollResponseCategory.objects.filter(category="No").update(is_active=True)
        FlowResultCategory.objects.filter(category="No").update(is_active=True)

        self.assertFalse(poll_question1.is_open_ended())

        # should be ignored in calculated results
        self.create_poll_response_category(poll_question1, "rule-uuid-3", "Other")

        now = timezone.now()

        PollResult.objects.create(
            org=self.uganda,
            flow=poll1.flow_uuid,
            ruleset=poll_question1.flow_result.result_uuid,
            contact="contact-1",
            date=now,
            category="All responses",
            state="",
            district="",
            text="1 better place",
            completed=False,
        )

        PollResult.objects.create(
            org=self.uganda,
            flow=poll1.flow_uuid,
            ruleset=poll_question1.flow_result.result_uuid,
            contact="contact-2",
            date=now,
            category="All responses",
            state="",
            district="",
            text="the great coffee",
            completed=False,
        )

        PollResult.objects.create(
            org=self.uganda,
            flow=poll1.flow_uuid,
            ruleset=poll_question1.flow_result.result_uuid,
            contact="contact-3",
            date=now,
            category="All responses",
            state="",
            district="",
            text="1 cup of black tea",
            completed=False,
        )

        PollResult.objects.create(
            org=self.uganda,
            flow=poll1.flow_uuid,
            ruleset=poll_question1.flow_result.result_uuid,
            contact="contact-3",
            date=now,
            category="All responses",
            state="",
            district="",
            text="1 cup of green tea",
            completed=False,
        )

        PollResult.objects.create(
            org=self.uganda,
            flow=poll1.flow_uuid,
            ruleset=poll_question1.flow_result.result_uuid,
            contact="contact-4",
            date=now,
            category="All responses",
            state="",
            district="",
            text="awesome than this encore",
            completed=False,
        )

        PollResult.objects.create(
            org=self.uganda,
            flow=poll1.flow_uuid,
            ruleset=poll_question1.flow_result.result_uuid,
            contact="contact-5",
            date=now,
            category="All responses",
            state="",
            district="",
            text="from an Awesome place in kigali",
            completed=False,
        )

        PollResult.objects.create(
            org=self.uganda,
            flow=poll1.flow_uuid,
            ruleset=poll_question1.flow_result.result_uuid,
            contact="contact-5",
            date=now,
            category="All responses",
            state="",
            district="",
            text="HtTp://kigali.coffee.fbcdn.com/like_image.png",
            completed=False,
        )

        with patch("ureport.polls.models.PollQuestion.is_open_ended") as mock_open:
            mock_open.return_value = True

            self.assertFalse(PollWordCloud.objects.all())
            poll_question1.generate_word_cloud()
            self.assertTrue(PollWordCloud.objects.all())
            self.assertEqual(PollWordCloud.objects.all().count(), 1)

            # another run will keep the same DB object
            poll_question1.generate_word_cloud()
            self.assertTrue(PollWordCloud.objects.all())
            self.assertEqual(PollWordCloud.objects.all().count(), 1)

            results = poll_question1.calculate_results()
            result = results[0]
            self.assertEqual(11, len(result["categories"]))
            self.assertTrue(result["open_ended"])
            self.assertResult(result, 0, "awesome", 2)
            self.assertResult(result, 1, "cup", 2)
            self.assertResult(result, 2, "place", 2)
            self.assertResult(result, 3, "tea", 2)
            self.assertResult(result, 4, "better", 1)
            self.assertResult(result, 5, "black", 1)
            self.assertResult(result, 6, "coffee", 1)
            self.assertResult(result, 7, "encore", 1)
            self.assertResult(result, 8, "great", 1)
            self.assertResult(result, 9, "green", 1)
            self.assertResult(result, 10, "kigali", 1)

            self.uganda.language = "fr"
            self.uganda.save()

            results = poll_question1.calculate_results()
            result = results[0]
            self.assertEqual(10, len(result["categories"]))
            self.assertTrue(result["open_ended"])
            self.assertResult(result, 0, "awesome", 2)
            self.assertResult(result, 1, "cup", 2)
            self.assertResult(result, 2, "place", 2)
            self.assertResult(result, 3, "tea", 2)
            self.assertResult(result, 4, "better", 1)
            self.assertResult(result, 5, "black", 1)
            self.assertResult(result, 6, "coffee", 1)
            self.assertResult(result, 7, "great", 1)
            self.assertResult(result, 8, "green", 1)
            self.assertResult(result, 9, "kigali", 1)

            self.uganda.set_config("common.ignore_words", " Black, Green ")

            results = poll_question1.calculate_results()
            result = results[0]
            self.assertEqual(8, len(result["categories"]))
            self.assertTrue(result["open_ended"])
            self.assertResult(result, 0, "awesome", 2)
            self.assertResult(result, 1, "cup", 2)
            self.assertResult(result, 2, "place", 2)
            self.assertResult(result, 3, "tea", 2)
            self.assertResult(result, 4, "better", 1)
            self.assertResult(result, 5, "coffee", 1)
            self.assertResult(result, 6, "great", 1)
            self.assertResult(result, 7, "kigali", 1)

            self.uganda.language = "en"
            self.uganda.save()

            with patch("ureport.utils.get_dict_from_cursor") as mock_get_dict_from_cursor:
                # no error for segmenting
                results = poll_question1.calculate_results(dict(location="State"))
                # should not have used the path with custom sql
                self.assertFalse(mock_get_dict_from_cursor.called)

        calculated_results = [
            dict(open_ended=False, set=0, unset=0, categories=[dict(count=0, label="Yes"), dict(count=0, label="No")])
        ]

        self.assertEqual(poll_question1.calculate_results(), calculated_results)
        poll1.rebuild_poll_results_counts()

        calculated_results = [
            dict(open_ended=False, set=0, unset=7, categories=[dict(count=0, label="Yes"), dict(count=0, label="No")])
        ]
        self.assertEqual(poll_question1.calculate_results(), calculated_results)

    def test_poll_question_calculate_results(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll_question1 = self.create_poll_question(self.admin, poll1, "question 1", "uuid-101")

        self.assertEqual(six.text_type(poll_question1), "question 1")

        # no response category are ignored
        self.create_poll_response_category(poll_question1, "rule-uuid-4", "No Response")

        self.assertFalse(poll_question1.is_open_ended())

        yes_category = self.create_poll_response_category(poll_question1, "rule-uuid-1", "Yes")

        self.assertTrue(poll_question1.is_open_ended())

        no_category = self.create_poll_response_category(poll_question1, "rule-uuid-2", "No")
        PollResponseCategory.objects.filter(category="No").update(is_active=False)

        self.assertTrue(poll_question1.is_open_ended())

        PollResponseCategory.objects.filter(category="No").update(is_active=True)

        self.assertFalse(poll_question1.is_open_ended())

        # should be ignored in calculated results
        self.create_poll_response_category(poll_question1, "rule-uuid-3", "Other")

        male_gender = GenderSegment.objects.filter(gender="M").first()
        female_gender = GenderSegment.objects.filter(gender="F").first()

        age_segment_20 = AgeSegment.objects.filter(min_age=20).first()
        age_segment_25 = AgeSegment.objects.filter(min_age=25).first()

        now = timezone.now()

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=yes_category,
            flow_result_category=yes_category.flow_result_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )

        calculated_results = [
            dict(open_ended=False, set=3, unset=1, categories=[dict(count=2, label="Yes"), dict(count=1, label="No")])
        ]
        self.assertEqual(poll_question1.calculate_results(), calculated_results)
        self.assertEqual(poll_question1.get_responded(), 3)
        self.assertEqual(poll_question1.get_polled(), 4)

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=None,
            gender_segment=male_gender,
            location=None,
            date=None,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=None,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=yes_category,
            flow_result_category=yes_category.flow_result_category,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=None,
            count=3,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=None,
            count=5,
        )

        calculated_results = [
            dict(set=2, unset=0, label="Male", categories=[dict(count=0, label="Yes"), dict(count=2, label="No")]),
            dict(set=4, unset=5, label="Female", categories=[dict(count=3, label="Yes"), dict(count=1, label="No")]),
        ]
        self.assertEqual(poll_question1.calculate_results(segment=dict(gender="gender")), calculated_results)

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=age_segment_20,
            gender_segment=None,
            location=None,
            date=None,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=None,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=yes_category,
            flow_result_category=yes_category.flow_result_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=None,
            count=3,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=None,
            count=5,
        )

        calculated_results = [
            dict(set=0, unset=0, label="0-14", categories=[dict(count=0, label="Yes"), dict(count=0, label="No")]),
            dict(set=0, unset=0, label="15-19", categories=[dict(count=0, label="Yes"), dict(count=0, label="No")]),
            dict(set=2, unset=0, label="20-24", categories=[dict(count=0, label="Yes"), dict(count=2, label="No")]),
            dict(set=4, unset=5, label="25-30", categories=[dict(count=3, label="Yes"), dict(count=1, label="No")]),
            dict(set=0, unset=0, label="31-34", categories=[dict(count=0, label="Yes"), dict(count=0, label="No")]),
            dict(set=0, unset=0, label="35+", categories=[dict(count=0, label="Yes"), dict(count=0, label="No")]),
        ]
        self.assertEqual(poll_question1.calculate_results(segment=dict(age="Age")), calculated_results)

    def test_squash_poll_stats(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll_question1 = self.create_poll_question(self.admin, poll1, "question 1", "uuid-101")

        self.assertEqual(six.text_type(poll_question1), "question 1")

        # no response category are ignored
        self.create_poll_response_category(poll_question1, "rule-uuid-4", "No Response")

        self.assertFalse(poll_question1.is_open_ended())

        yes_category = self.create_poll_response_category(poll_question1, "rule-uuid-1", "Yes")

        self.assertTrue(poll_question1.is_open_ended())

        no_category = self.create_poll_response_category(poll_question1, "rule-uuid-2", "No")
        PollResponseCategory.objects.filter(category="No").update(is_active=False)

        self.assertTrue(poll_question1.is_open_ended())

        PollResponseCategory.objects.filter(category="No").update(is_active=True)

        self.assertFalse(poll_question1.is_open_ended())

        # should be ignored in calculated results
        self.create_poll_response_category(poll_question1, "rule-uuid-3", "Other")

        male_gender = GenderSegment.objects.filter(gender="M").first()
        female_gender = GenderSegment.objects.filter(gender="F").first()

        age_segment_20 = AgeSegment.objects.filter(min_age=20).first()
        age_segment_25 = AgeSegment.objects.filter(min_age=25).first()

        now = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        PollStats.objects.all().delete()
        self.assertEqual(0, PollStats.objects.all().count())

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=yes_category,
            flow_result_category=yes_category.flow_result_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=3,
        )

        self.assertEqual(4, PollStats.objects.all().count())
        calculated_results = [
            dict(open_ended=False, set=6, unset=1, categories=[dict(count=2, label="Yes"), dict(count=4, label="No")])
        ]
        self.assertEqual(poll_question1.calculate_results(), calculated_results)

        PollStats.squash()

        self.assertEqual(3, PollStats.objects.all().count())
        calculated_results = [
            dict(open_ended=False, set=6, unset=1, categories=[dict(count=2, label="Yes"), dict(count=4, label="No")])
        ]
        self.assertEqual(poll_question1.calculate_results(), calculated_results)

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=4,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=2,
        )

        self.assertEqual(5, PollStats.objects.all().count())
        calculated_results = [
            dict(
                open_ended=False, set=12, unset=1, categories=[dict(count=2, label="Yes"), dict(count=10, label="No")]
            )
        ]
        self.assertEqual(poll_question1.calculate_results(), calculated_results)

        PollStats.squash()

        self.assertEqual(3, PollStats.objects.all().count())
        calculated_results = [
            dict(
                open_ended=False, set=12, unset=1, categories=[dict(count=2, label="Yes"), dict(count=10, label="No")]
            )
        ]
        self.assertEqual(poll_question1.calculate_results(), calculated_results)

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=None,
            gender_segment=male_gender,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=yes_category,
            flow_result_category=yes_category.flow_result_category,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=None,
            count=3,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=now,
            count=5,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=now,
            count=4,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=now,
            count=3,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=None,
            count=3,
        )
        calculated_results = [
            dict(set=2, unset=0, label="Male", categories=[dict(count=0, label="Yes"), dict(count=2, label="No")]),
            dict(set=4, unset=16, label="Female", categories=[dict(count=3, label="Yes"), dict(count=1, label="No")]),
        ]
        self.assertEqual(poll_question1.calculate_results(segment=dict(gender="gender")), calculated_results)

        self.assertEqual(11, PollStats.objects.all().count())
        PollStats.squash()

        self.assertEqual(8, PollStats.objects.all().count())
        self.assertEqual(poll_question1.calculate_results(segment=dict(gender="gender")), calculated_results)

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=age_segment_20,
            gender_segment=None,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=no_category,
            flow_result_category=no_category.flow_result_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=yes_category,
            flow_result_category=yes_category.flow_result_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=3,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=5,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=yes_category,
            flow_result_category=yes_category.flow_result_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=4,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=yes_category,
            flow_result_category=yes_category.flow_result_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            flow_result=poll_question1.flow_result,
            category=None,
            flow_result_category=None,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=6,
        )

        calculated_results = [
            dict(set=0, unset=0, label="0-14", categories=[dict(count=0, label="Yes"), dict(count=0, label="No")]),
            dict(set=0, unset=0, label="15-19", categories=[dict(count=0, label="Yes"), dict(count=0, label="No")]),
            dict(set=2, unset=0, label="20-24", categories=[dict(count=0, label="Yes"), dict(count=2, label="No")]),
            dict(set=9, unset=13, label="25-30", categories=[dict(count=8, label="Yes"), dict(count=1, label="No")]),
            dict(set=0, unset=0, label="31-34", categories=[dict(count=0, label="Yes"), dict(count=0, label="No")]),
            dict(set=0, unset=0, label="35+", categories=[dict(count=0, label="Yes"), dict(count=0, label="No")]),
        ]
        self.assertEqual(poll_question1.calculate_results(segment=dict(age="Age")), calculated_results)

        self.assertEqual(16, PollStats.objects.all().count())
        PollStats.squash()

        self.assertEqual(12, PollStats.objects.all().count())
        self.assertEqual(poll_question1.calculate_results(segment=dict(age="Age")), calculated_results)

    def test_tasks(self):
        self.org = self.create_org("burundi", zoneinfo.ZoneInfo("Africa/Bujumbura"), self.admin)

        self.education = Category.objects.create(
            org=self.org, name="Education", created_by=self.admin, modified_by=self.admin
        )

        self.poll = self.create_poll(self.org, "Poll 1", "uuid-1", self.education, self.admin)

        with patch("ureport.polls.tasks.fetch_flows") as mock_fetch_flows:
            mock_fetch_flows.return_value = "FETCHED"

            refresh_org_flows(self.org.pk)
            mock_fetch_flows.assert_called_once_with(self.org)

        with patch("ureport.polls.tasks.do_fetch_old_sites_count") as mock_fetch_old_sites_count:
            mock_fetch_old_sites_count.return_value = "FETCHED"

            fetch_old_sites_count()
            mock_fetch_old_sites_count.assert_called_once_with()

        with patch("ureport.polls.tasks.update_poll_flow_data") as mock_update_poll_flow_data:
            mock_update_poll_flow_data.return_value = "RECHECKED"

            recheck_poll_flow_data(self.org.pk)
            mock_update_poll_flow_data.assert_called_once_with(self.org)

        with patch("ureport.polls.models.Poll.pull_results") as mock_pull_results:
            mock_pull_results.return_value = "Pulled"

            pull_refresh(self.poll.pk)
            mock_pull_results.assert_called_once_with(self.poll.pk)

        with patch("ureport.polls.models.Poll.rebuild_poll_results_counts") as mock_rebuild_counts:
            mock_rebuild_counts.return_value = "Rebuilt"

            rebuild_counts()
            self.assertEqual(mock_rebuild_counts.call_count, Poll.objects.all().count())

        with patch("ureport.polls.models.Poll.update_or_create_questions") as mock_update_or_create_questions:
            mock_update_or_create_questions.side_effect = None

            update_or_create_questions([self.poll.pk])
            mock_update_or_create_questions.assert_called_once()
            mock_update_or_create_questions.reset_mock()

            poll2 = self.create_poll(self.uganda, "Poll 2", "flow-uuid-2", self.health_uganda, self.admin)
            update_or_create_questions([self.poll.pk, poll2.pk])
            self.assertEqual(mock_update_or_create_questions.call_count, 2)

        with patch("ureport.polls.models.Poll.rebuild_poll_results_counts") as mock_rebuild_counts:
            mock_rebuild_counts.return_value = "Rebuilt"

            with patch("ureport.polls.tasks.populate_age_and_gender_poll_results") as mock_populate_age_gender_results:
                mock_populate_age_gender_results.return_value = "Populated"

                update_results_age_gender(self.nigeria.pk)

                mock_populate_age_gender_results.assert_called_once_with(self.nigeria)
                self.assertEqual(mock_rebuild_counts.call_count, Poll.objects.filter(org=self.nigeria).count())


class PollResultsTest(UreportTest):
    def setUp(self):
        super(PollResultsTest, self).setUp()

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

        self.poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        self.poll_question = self.create_poll_question(self.admin, self.poll, "question 1", "step-uuid")

        self.now = timezone.now()
        self.last_week = self.now - timedelta(days=7)
        self.last_month = self.now - timedelta(days=30)

    def test_contact_activity_counters(self):
        self.assertFalse(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))
        self.assertFalse(ContactActivityCounter.objects.filter(org=self.nigeria))

        current_year = timezone.now().year
        next_year = current_year + 1
        eight_years_ago = current_year - 8

        result_date = timezone.now().replace(
            year=next_year, month=9, day=15, hour=0, minute=0, second=0, microsecond=0
        )

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.flow_result.result_uuid,
            date=result_date,
            contact="contact-uuid",
            completed=False,
        )

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.flow_result.result_uuid,
            category="No",
            date=result_date,
            contact="contact-uuid",
            completed=False,
        )

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid",
            category="No",
            text="Nah",
            completed=False,
            date=result_date,
            state="R-LAGOS",
            district="R-oyo",
            ward="R-IKEJA",
        )

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid2",
            category="Yes",
            text="Yeah",
            completed=False,
            born=eight_years_ago,
            gender="M",
            date=result_date,
            state="R-LAGOS",
            district="R-OYO",
            ward="R-IKEJA",
            scheme="facebook",
        )

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid3",
            category="Yes",
            text="Yeah",
            completed=False,
            born=eight_years_ago,
            gender="M",
            date=result_date,
            state="R-ABUJA",
            district="R-BU",
            ward="R-BA",
            scheme="facebook",
        )

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid4",
            category="Yes",
            text="Yeah",
            completed=False,
            born=eight_years_ago,
            gender="F",
            date=result_date,
            state="R-LAGOS",
            district="R-OYO",
            ward="R-IKEJA",
            scheme="tel",
        )
        self.assertTrue(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))
        self.assertTrue(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid2"))
        self.assertTrue(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid3"))

        def verify_counts():
            activity_counts = (
                ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_ALL)
                .values("date")
                .annotate(Sum("count"))
            )

            activities = (
                ContactActivity.objects.filter(org=self.nigeria).values("date").annotate(count__sum=Count("id"))
            )
            self.assertEqual(12, activity_counts.count())
            self.assertEqual(12, activities.count())

            # the count should be 1 for each date and match contact activities query couns
            for idx, elt in enumerate(activity_counts):
                self.assertEqual(4, elt["count__sum"])
                self.assertEqual(elt, activities[idx])

            age_activity_counts = (
                ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_AGE)
                .annotate(age=Cast("value", output_field=IntegerField()))
                .values("date", "type", "age")
                .annotate(Sum("count"))
            )
            age_activities = (
                ContactActivity.objects.filter(org=self.nigeria)
                .exclude(born=None)
                .exclude(date=None)
                .annotate(year=ExtractYear("date"))
                .annotate(age=ExpressionWrapper(F("year") - F("born"), output_field=IntegerField()))
                .annotate(type=Value("B"))
                .values("date", "type", "age")
                .annotate(count__sum=Count("id"))
            )

            self.assertEqual(12, age_activity_counts.count())
            self.assertEqual(12, age_activities.count())

            for idx, elt in enumerate(age_activity_counts):
                self.assertEqual(3, elt["count__sum"])
                self.assertEqual(elt, age_activities[idx])

            gender_activity_counts = (
                ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_GENDER)
                .values("date", "type", "value")
                .annotate(Sum("count"))
            )

            gender_activities = (
                ContactActivity.objects.filter(org=self.nigeria)
                .exclude(gender=None)
                .exclude(date=None)
                .annotate(value=Cast("gender", output_field=TextField()))
                .annotate(type=Value("G"))
                .values("date", "type", "value")
                .annotate(count__sum=Count("id"))
            )

            self.assertEqual(24, gender_activity_counts.count())
            self.assertEqual(24, gender_activities.count())

            for idx, elt in enumerate(gender_activity_counts):
                self.assertEqual(elt, gender_activities[idx])
                if elt["value"] == "F":
                    self.assertEqual(1, elt["count__sum"])
                if elt["value"] == "M":
                    self.assertEqual(2, elt["count__sum"])

            location_activity_counts = (
                ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_LOCATION)
                .values("date", "type", "value")
                .annotate(Sum("count"))
            )

            location_activities = (
                ContactActivity.objects.filter(org=self.nigeria)
                .exclude(state=None)
                .exclude(date=None)
                .annotate(value=Cast("state", output_field=TextField()))
                .annotate(type=Value("L"))
                .values("date", "type", "value")
                .annotate(count__sum=Count("id"))
            )

            self.assertEqual(24, location_activity_counts.count())
            self.assertEqual(24, location_activities.count())

            for idx, elt in enumerate(location_activity_counts):
                self.assertEqual(elt, location_activities[idx])
                if elt["value"] == "R-LAGOS":
                    self.assertEqual(2, elt["count__sum"])
                if elt["value"] == "R-ABUJA":
                    self.assertEqual(1, elt["count__sum"])

            scheme_activity_counts = (
                ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_SCHEME)
                .values("date", "type", "value")
                .annotate(Sum("count"))
            )
            scheme_activities = (
                ContactActivity.objects.filter(org=self.nigeria)
                .exclude(scheme=None)
                .exclude(date=None)
                .annotate(value=Cast("scheme", output_field=TextField()))
                .annotate(type=Value("S"))
                .values("date", "type", "value")
                .annotate(count__sum=Count("id"))
            )

            self.assertEqual(24, scheme_activity_counts.count())
            self.assertEqual(24, scheme_activities.count())

            for idx, elt in enumerate(scheme_activity_counts):
                self.assertEqual(elt, scheme_activities[idx])
                if elt["value"] == "tel":
                    self.assertEqual(1, elt["count__sum"])
                if elt["value"] == "facebook":
                    self.assertEqual(2, elt["count__sum"])

        verify_counts()

        self.assertEqual(192, ContactActivityCounter.objects.all().count())
        ContactActivityCounter.squash()
        self.assertEqual(96, ContactActivityCounter.objects.all().count())

        verify_counts()

        ContactActivity.recalculate_contact_activity_counts(self.nigeria)

        self.assertEqual(96, ContactActivityCounter.objects.all().count())
        verify_counts()

        # manually delete, then regenarate
        ContactActivityCounter.objects.filter(org_id=self.nigeria).delete()
        ContactActivity.recalculate_contact_activity_counts(self.nigeria)
        verify_counts()

    def test_contact_activity(self):
        self.assertFalse(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))
        self.assertFalse(ContactActivityCounter.objects.filter(org=self.nigeria))

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.flow_result.result_uuid,
            date=self.now,
            contact="contact-uuid",
            completed=False,
        )

        self.assertFalse(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))
        self.assertFalse(ContactActivityCounter.objects.filter(org=self.nigeria))

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.flow_result.result_uuid,
            category="No",
            date=self.now,
            contact="contact-uuid",
            completed=False,
        )

        self.assertTrue(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid").count(), 12)
        self.assertFalse(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(born=None))
        self.assertFalse(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid")
            .exclude(gender="")
            .exclude(gender=None)
        )
        self.assertFalse(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid")
            .exclude(state="")
            .exclude(state=None)
        )
        self.assertFalse(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid")
            .exclude(district="")
            .exclude(district=None)
        )
        self.assertFalse(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid")
            .exclude(ward="")
            .exclude(ward=None)
        )

        # have all type counts
        activity_counts = (
            ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_ALL)
            .values("date")
            .annotate(Sum("count"))
        )
        self.assertEqual(12, activity_counts.count())
        # the count shoul be 1 for each date
        for elt in activity_counts:
            self.assertEqual(1, elt["count__sum"])

        # no gender/age/location/scheme type counts
        self.assertEqual(
            0,
            ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_AGE)
            .values("date")
            .annotate(Sum("count"))
            .count(),
        )
        self.assertEqual(
            0,
            ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_GENDER)
            .values("date")
            .annotate(Sum("count"))
            .count(),
        )
        self.assertEqual(
            0,
            ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_LOCATION)
            .values("date")
            .annotate(Sum("count"))
            .count(),
        )
        self.assertEqual(
            0,
            ContactActivityCounter.objects.filter(org=self.nigeria, type=ContactActivityCounter.TYPE_SCHEME)
            .values("date")
            .annotate(Sum("count"))
            .count(),
        )

    def test_poll_result_generate_stats(self):
        poll_result1 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.flow_result.result_uuid,
            date=self.now,
            contact="contact-uuid",
            completed=False,
        )

        gen_stats = poll_result1.generate_poll_stats()
        self.assertEqual(len(gen_stats.keys()), 1)
        self.assertEqual(
            list(gen_stats.keys()),
            [
                (
                    self.nigeria.id,
                    self.poll_question.flow_result.result_uuid,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    self.now.replace(hour=0, minute=0, second=0, microsecond=0),
                )
            ],
        )

        poll_result2 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid",
            category="No",
            text="Nah",
            completed=False,
            date=self.now,
            state="R-LAGOS",
            district="R-oyo",
            ward="R-IKEJA",
            scheme="tel",
        )

        gen_stats = poll_result2.generate_poll_stats()

        ruleset = poll_result2.ruleset.lower()
        category = poll_result2.category.lower()
        state = poll_result2.state.upper()
        district = poll_result2.district.upper()
        ward = poll_result2.ward.upper()

        self.assertEqual(len(gen_stats.keys()), 1)
        self.assertEqual(
            list(gen_stats.keys()),
            [
                (
                    self.nigeria.id,
                    ruleset,
                    category,
                    "",
                    "",
                    state,
                    district,
                    ward,
                    "tel",
                    self.now.replace(hour=0, minute=0, second=0, microsecond=0),
                )
            ],
        )

        poll_result3 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid",
            category="No Response",
            text="None",
            completed=False,
            date=self.now,
            state="R-LAGOS",
            district="R-oyo",
            ward="R-IKEJA",
            scheme="facebook",
        )

        gen_stats = poll_result3.generate_poll_stats()

        ruleset = poll_result3.ruleset.lower()
        state = poll_result3.state.upper()
        district = poll_result3.district.upper()
        ward = poll_result3.ward.upper()

        self.assertEqual(len(gen_stats.keys()), 1)
        self.assertEqual(
            list(gen_stats.keys()),
            [
                (
                    self.nigeria.id,
                    ruleset,
                    "",
                    "",
                    "",
                    state,
                    district,
                    ward,
                    "facebook",
                    self.now.replace(hour=0, minute=0, second=0, microsecond=0),
                )
            ],
        )

        poll_result4 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid",
            category="Yes",
            text="Yeah",
            completed=False,
            born=2015,
            gender="M",
            date=self.now,
            state="R-LAGOS",
            district="R-oyo",
            ward="R-IKEJA",
            scheme="tel",
        )

        gen_stats = poll_result4.generate_poll_stats()

        ruleset = poll_result4.ruleset.lower()
        state = poll_result4.state.upper()
        district = poll_result4.district.upper()
        ward = poll_result4.ward.upper()

        self.assertEqual(len(gen_stats.keys()), 1)
        self.assertEqual(
            list(gen_stats.keys()),
            [
                (
                    self.nigeria.id,
                    ruleset,
                    "yes",
                    2015,
                    "m",
                    state,
                    district,
                    ward,
                    "tel",
                    self.now.replace(hour=0, minute=0, second=0, microsecond=0),
                )
            ],
        )

        poll_result5 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.flow_result.result_uuid,
            date=None,
            contact="contact-uuid",
            completed=False,
        )

        gen_stats = poll_result5.generate_poll_stats()
        self.assertEqual(len(gen_stats.keys()), 1)
        self.assertEqual(
            list(gen_stats.keys()),
            [(self.nigeria.id, self.poll_question.flow_result.result_uuid, "", "", "", "", "", "", "", None)],
        )

    def test_poll_results_stats(self):
        nigeria_boundary = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-NIGERIA",
            name="Nigeria",
            parent=None,
            level=0,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        lagos_boundary = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-LAGOS",
            name="Lagos",
            parent=nigeria_boundary,
            level=1,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        oyo_boundary = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-OYO",
            name="Oyo",
            parent=lagos_boundary,
            level=2,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        ikeja_boundary = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-IKEJA",
            name="Ikeja",
            parent=oyo_boundary,
            level=3,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        rule_uuid = uuid.uuid4()
        yes_category = self.create_poll_response_category(self.poll_question, rule_uuid, "Yes")

        rule_uuid = uuid.uuid4()
        self.create_poll_response_category(self.poll_question, rule_uuid, "No")

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.flow_result.result_uuid,
            contact="contact-uuid",
            category="Yes",
            text="Yeah",
            completed=False,
            born=2015,
            gender="M",
            date=self.now,
            state="R-LAGOS",
            district="R-oyo",
            ward="R-IKEJA",
        )
        self.poll.rebuild_poll_results_counts()
        self.assertEqual(PollStats.objects.all().count(), 1)
        poll_stat = PollStats.objects.get()

        self.assertEqual(poll_stat.org, self.nigeria)
        self.assertEqual(poll_stat.flow_result, self.poll_question.flow_result)
        self.assertEqual(poll_stat.flow_result_category, yes_category.flow_result_category)
        self.assertEqual(poll_stat.location, ikeja_boundary)
        self.assertEqual(poll_stat.gender_segment, GenderSegment.objects.get(gender="M"))
        self.assertEqual(poll_stat.age_segment, AgeSegment.objects.get(min_age=0))
        self.assertEqual(poll_stat.date, self.now.replace(hour=0, minute=0, second=0, microsecond=0))

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.flow_result.result_uuid,
            contact="contact-uuid",
            category="Yes",
            text="Yeah",
            completed=False,
            date=self.now,
        )

        self.poll.rebuild_poll_results_counts()
        self.assertEqual(PollStats.objects.all().count(), 2)
        self.assertEqual(
            PollStats.objects.filter(flow_result=self.poll_question.flow_result).aggregate(Sum("count"))["count__sum"],
            2,
        )
        self.assertEqual(
            PollStats.objects.filter(flow_result_category=yes_category.flow_result_category).aggregate(Sum("count"))[
                "count__sum"
            ],
            2,
        )
        self.assertEqual(PollStats.objects.filter(location=ikeja_boundary).aggregate(Sum("count"))["count__sum"], 1)

        self.assertEqual(
            self.poll_question.calculate_results()[0]["categories"],
            [{"count": 2, "label": "Yes"}, {"count": 0, "label": "No"}],
        )
        self.assertEqual(
            self.poll_question.calculate_results(segment=dict(location="State"))[0]["categories"],
            [{"count": 1, "label": "Yes"}, {"count": 0, "label": "No"}],
        )
        self.assertEqual(
            self.poll_question.calculate_results(segment=dict(location="District", parent="R-LAGOS"))[0]["categories"],
            [{"count": 1, "label": "Yes"}, {"count": 0, "label": "No"}],
        )
        self.assertEqual(
            self.poll_question.calculate_results(segment=dict(location="Ward", parent="R-OYO"))[0]["categories"],
            [{"count": 1, "label": "Yes"}, {"count": 0, "label": "No"}],
        )


class PollsTasksTest(UreportTest):
    def setUp(self):
        super(PollsTasksTest, self).setUp()
        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )
        self.poll = self.create_poll(self.nigeria, "Poll 1", "uuid-1", self.education_nigeria, self.admin)

        self.poll_same_flow = self.create_poll(
            self.nigeria, "Poll Same Flow", "uuid-1", self.education_nigeria, self.admin, has_synced=True
        )

        self.polls_query = Poll.objects.filter(pk__in=[self.poll.pk, self.poll_same_flow.pk]).order_by("-created_on")

        # polls without flow_uuid
        self.create_poll(self.nigeria, "Poll 4", "", self.education_nigeria, self.admin, has_synced=False)
        self.create_poll(self.nigeria, "Poll 5", "", self.education_nigeria, self.admin, has_synced=True)

    @patch("ureport.polls.models.Poll.get_flow_date")
    @patch("dash.orgs.models.Org.get_backend")
    @patch("ureport.tests.TestBackend.pull_results")
    @patch("ureport.polls.models.Poll.get_main_poll")
    def test_pull_results_main_poll(self, mock_get_main_poll, mock_pull_results, mock_get_backend, mock_get_flow_date):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_get_main_poll.return_value = self.poll
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)
        mock_get_flow_date.return_value = None

        pull_results_main_poll(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key="results-pull-main-poll")
        self.assertEqual(
            task_state.get_last_results()["flow-%s" % self.poll.flow_uuid],
            {
                "num_val_created": 1,
                "num_val_updated": 2,
                "num_val_ignored": 3,
                "num_path_created": 4,
                "num_path_updated": 5,
                "num_path_ignored": 6,
            },
        )

    @patch("ureport.polls.models.Poll.get_flow_date")
    @patch("dash.orgs.models.Org.get_backend")
    @patch("django.core.cache.cache.get")
    @patch("ureport.tests.TestBackend.pull_results")
    @patch("ureport.polls.models.Poll.get_other_polls")
    def test_pull_results_other_polls(
        self, mock_get_other_polls, mock_pull_results, mock_cache_get, mock_get_backend, mock_get_flow_date
    ):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_get_other_polls.return_value = self.polls_query
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)
        mock_cache_get.return_value = None
        mock_get_flow_date.return_value = None

        self.poll.created_on = timezone.now() - timedelta(days=8)
        self.poll.save()

        pull_results_other_polls(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key="results-pull-other-polls")
        self.assertEqual(
            task_state.get_last_results()["flow-%s" % self.poll.flow_uuid],
            {
                "num_val_created": 1,
                "num_val_updated": 2,
                "num_val_ignored": 3,
                "num_path_created": 4,
                "num_path_updated": 5,
                "num_path_ignored": 6,
            },
        )

        mock_pull_results.assert_called_once()

        mock_pull_results.reset_mock()
        mock_pull_results.side_effect = [TembaRateExceededError(3)]

        pull_results_other_polls(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key="results-pull-other-polls")
        self.assertEqual(task_state.get_last_results(), {})
        mock_pull_results.assert_called_once()

    @patch("ureport.polls.models.Poll.get_flow_date")
    @patch("dash.orgs.models.Org.get_backend")
    @patch("ureport.tests.TestBackend.pull_results")
    def test_backfill_poll_results(self, mock_pull_results, mock_get_backend, mock_get_flow_date):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)
        mock_get_flow_date.return_value = None

        self.poll.has_synced = True
        self.poll.save()

        backfill_poll_results(self.nigeria.pk)
        self.assertFalse(mock_pull_results.called)

        self.poll.has_synced = False
        self.poll.save()

        backfill_poll_results(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key="backfill-poll-results")
        self.assertEqual(
            task_state.get_last_results()["flow-%s" % self.poll.flow_uuid],
            {
                "num_val_created": 1,
                "num_val_updated": 2,
                "num_val_ignored": 3,
                "num_path_created": 4,
                "num_path_updated": 5,
                "num_path_ignored": 6,
            },
        )

        mock_pull_results.assert_called_once()
