# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
from datetime import datetime, timedelta

import pytz
import six
from dash.categories.fields import CategoryChoiceField
from dash.categories.models import Category, CategoryImage
from dash.orgs.models import TaskState
from mock import Mock, patch
from smartmin.csv_imports.models import ImportTask
from temba_client.exceptions import TembaRateExceededError

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Sum
from django.http import HttpRequest
from django.template import TemplateSyntaxError
from django.urls import reverse
from django.utils import timezone

from ureport.locations.models import Boundary
from ureport.polls.models import Poll, PollImage, PollQuestion, PollResponseCategory, PollResult, PollResultsCounter
from ureport.polls.tasks import (
    backfill_poll_results,
    fetch_old_sites_count,
    pull_refresh,
    pull_results_brick_polls,
    pull_results_main_poll,
    pull_results_other_polls,
    rebuild_counts,
    recheck_poll_flow_data,
    refresh_org_flows,
    update_or_create_questions,
    update_results_age_gender,
)
from ureport.polls.templatetags.ureport import question_segmented_results
from ureport.stats.models import AgeSegment, ContactActivity, GenderSegment, PollStats, PollWordCloud
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

    def test_prepare_fields(self):

        with self.assertRaises(Exception):
            Poll.prepare_fields(dict())

        with self.assertRaises(Exception):
            Poll.prepare_fields(dict(), dict())

        self.assertEqual(
            dict(org=self.uganda, created_by=self.superuser),
            Poll.prepare_fields(dict(), dict(org_id=self.uganda.pk), user=self.superuser),
        )

    def test_poll_create_instance(self):

        self.assertFalse(Poll.objects.filter(org=self.uganda))
        self.assertFalse(PollQuestion.objects.filter(poll__org=self.uganda))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict())

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda, created_by=self.superuser))

        with self.assertRaises(ValueError):
            Poll.create_instance(dict(org=self.uganda, created_by=self.superuser, category="Sports"))

        with self.assertRaises(ValueError):
            Poll.create_instance(
                dict(org=self.uganda, created_by=self.superuser, category="Sports", uuid="uuid-flow-1")
            )

        with self.assertRaises(ValueError):
            Poll.create_instance(
                dict(org=self.uganda, created_by=self.superuser, category="Sports", uuid="uuid-flow-1", name="Flow 1")
            )

        with self.assertRaises(ValueError):
            Poll.create_instance(
                dict(
                    org=self.uganda,
                    created_by=self.superuser,
                    category="Sports",
                    uuid="uuid-flow-1",
                    name="Flow 1",
                    created_on="2010-07-07T14:24:12.753000Z",
                )
            )

        with self.assertRaises(ValueError):
            Poll.create_instance(
                dict(
                    org=self.uganda,
                    created_by=self.superuser,
                    category="Sports",
                    uuid="uuid-flow-1",
                    name="Sport Activities",
                    created_on="2010-07-07T14:24:12.753000Z",
                    ruleset_uuid="question-uuid-1",
                )
            )

        poll = Poll.create_instance(
            dict(
                org=self.uganda,
                created_by=self.superuser,
                category="Sports",
                uuid="uuid-flow-1",
                name="Sport Activities",
                created_on="2010-07-07T14:24:12.753000Z",
                ruleset_uuid="question-uuid-1",
                question="Did you participate in #CarFreeDay?",
            )
        )

        self.assertTrue(Poll.objects.filter(org=self.uganda, flow_uuid="uuid-flow-1"))
        self.assertTrue(poll in Poll.objects.filter(org=self.uganda, flow_uuid="uuid-flow-1"))
        self.assertTrue(
            PollQuestion.objects.filter(
                poll__org=self.uganda, ruleset_uuid="question-uuid-1", title="Did you participate in #CarFreeDay?"
            )
        )

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 1)

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 1)

        # same row does not add duplicates
        Poll.create_instance(
            dict(
                org=self.uganda,
                created_by=self.superuser,
                category="Sports",
                uuid="uuid-flow-1",
                name="Sport Activities Here",
                created_on="2010-07-07T14:24:12.753000Z",
                ruleset_uuid="question-uuid-1",
                question="Did you participate in #CarFreeDay?",
            )
        )

        self.assertTrue(Poll.objects.filter(org=self.uganda, flow_uuid="uuid-flow-1"))
        self.assertTrue(
            PollQuestion.objects.filter(
                poll__org=self.uganda, ruleset_uuid="question-uuid-1", title="Did you participate in #CarFreeDay?"
            )
        )

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 1)
        poll = Poll.objects.filter(org=self.uganda).first()
        # however update the poll title
        self.assertEqual(poll.title, "Sport Activities Here")

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 1)

        # new row add new poll and its questions
        Poll.create_instance(
            dict(
                org=self.uganda,
                created_by=self.superuser,
                category="Music",
                uuid="uuid-flow-2",
                name="Showbiz",
                created_on="2010-07-07T14:24:12.753000Z",
                ruleset_uuid="question-uuid-2",
                question="Which concert?",
            )
        )

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 2)

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 2)

        # no hidden question
        self.assertFalse(PollQuestion.objects.filter(poll__org=self.uganda, is_active=False))

        # same flow without the question should add a new flow
        Poll.create_instance(
            dict(
                org=self.uganda,
                created_by=self.superuser,
                category="Music",
                uuid="uuid-flow-2",
                name="Sounds",
                created_on="2010-07-07T14:24:12.753000Z",
                ruleset_uuid="question-uuid-3",
                question="Which album?",
            )
        )

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 3)

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 3)
        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda, is_active=True).count(), 3)

        # no hidden question
        self.assertFalse(PollQuestion.objects.filter(poll__org=self.uganda, is_active=False))

        poll = Poll.objects.filter(org=self.uganda, flow_uuid="uuid-flow-2").first()
        question = PollQuestion.update_or_create(self.superuser, poll, "", "question-uuid-4", "wait_message")
        PollQuestion.objects.filter(pk=question.pk).update(is_active=True)

        # same flow with the ruleset question existing should hide old questions without new flow
        Poll.create_instance(
            dict(
                org=self.uganda,
                created_by=self.superuser,
                category="Music",
                uuid="uuid-flow-2",
                name="Sounds",
                created_on="2010-07-07T14:24:12.753000Z",
                ruleset_uuid="question-uuid-2",
                question="Which album?",
            )
        )

        self.assertEqual(Poll.objects.filter(org=self.uganda).count(), 3)

        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda).count(), 4)
        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda, is_active=True).count(), 3)

        # poll other questions are hidden
        self.assertEqual(PollQuestion.objects.filter(poll__org=self.uganda, is_active=False).count(), 1)
        self.assertEqual(
            PollQuestion.objects.filter(
                poll__org=self.uganda, is_active=False, ruleset_uuid="question-uuid-4"
            ).count(),
            1,
        )

    @patch("ureport.polls.models.Poll.update_or_create_questions_task")
    def test_poll_import_csv(self, mock_poll_update_or_create_questions_task):
        poll1 = self.create_poll(self.uganda, "Poll 1", "flow-uuid-1", self.health_uganda, self.admin)
        PollQuestion.objects.create(
            poll=poll1,
            title="question poll 1",
            ruleset_uuid="ruleset-uuid-1",
            created_by=self.admin,
            modified_by=self.admin,
        )
        poll2 = self.create_poll(self.uganda, "Poll 2", "flow-uuid-2", self.health_uganda, self.admin)

        PollQuestion.objects.create(
            poll=poll2,
            title="question poll 2",
            ruleset_uuid="ruleset-uuid-2",
            created_by=self.admin,
            modified_by=self.admin,
        )

        mock_poll_update_or_create_questions_task.side_effect = None

        import_params = dict(
            org_id=self.uganda.id, timezone=six.text_type(self.uganda.timezone), original_filename="polls.csv"
        )

        task = ImportTask.objects.create(
            created_by=self.superuser,
            modified_by=self.superuser,
            csv_file="test_imports/polls.csv",
            model_class="Poll",
            import_params=json.dumps(import_params),
            import_log="",
            task_id="A",
        )

        Poll.import_csv(task, log=None)

        place_poll = Poll.objects.filter(id=poll1.pk).first()
        time_poll = Poll.objects.filter(id=poll2.pk).first()

        self.assertEqual(place_poll.title, "Place poll")
        self.assertEqual(time_poll.title, "Time poll")

        mock_poll_update_or_create_questions_task.assert_called_once_with([place_poll, time_poll])

    def test_poll_import(self):
        import_url = reverse("polls.poll_import")

        response = self.client.get(import_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(import_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.superuser)

        response = self.client.get(import_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertTrue("csv_file" in response.context["form"].fields)

        csv_file = open("%s/test_imports/polls.csv" % settings.MEDIA_ROOT, "rb")
        post_data = dict(csv_file=csv_file)

        response = self.client.post(import_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(200, response.status_code)

        task = ImportTask.objects.get()
        self.assertEqual(
            json.loads(task.import_params),
            dict(timezone="Africa/Kampala", org_id=self.uganda.pk, original_filename="polls.csv"),
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
        tz = pytz.timezone("Africa/Kigali")
        with patch.object(timezone, "now", return_value=tz.localize(datetime(2015, 9, 4, 3, 4, 5, 0))):

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

            poll1.pull_refresh_task()

            now = timezone.now()
            mock_cache_set.assert_called_once_with(
                Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (poll1.org_id, poll1.pk),
                datetime_to_json_date(now.replace(tzinfo=pytz.utc)),
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

        self.health_uganda.is_active = True
        self.health_uganda.save()

        poll2.is_active = False
        poll2.save()

        self.assertFalse(Poll.get_public_polls(self.uganda))

    def test_poll_get_main_poll(self):
        self.assertIsNone(Poll.get_main_poll(self.uganda))
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, has_synced=True)

        self.assertEqual(six.text_type(poll1), "Poll 1")

        self.assertIsNone(Poll.get_main_poll(self.uganda))
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        PollQuestion.objects.create(
            poll=poll1, title="question poll 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        self.assertEqual(Poll.get_main_poll(self.uganda), poll1)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", self.health_uganda, self.admin, has_synced=True)

        PollQuestion.objects.create(
            poll=poll2, title="question poll 2", ruleset_uuid="uuid-202", created_by=self.admin, modified_by=self.admin
        )

        self.assertEqual(Poll.get_main_poll(self.uganda), poll2)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin, has_synced=True)

        PollQuestion.objects.create(
            poll=poll3, title="question poll 3", ruleset_uuid="uuid-303", created_by=self.admin, modified_by=self.admin
        )

        self.assertEqual(Poll.get_main_poll(self.uganda), poll3)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll1.is_featured = True
        poll1.save()

        self.assertEqual(Poll.get_main_poll(self.uganda), poll1)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        poll1.is_active = False
        poll1.save()

        self.assertEqual(Poll.get_main_poll(self.uganda), poll3)
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertIsNone(Poll.get_main_poll(self.uganda))
        self.assertIsNone(Poll.get_main_poll(self.nigeria))

    @patch("django.core.cache.cache.get")
    def test_brick_polls(self, mock_cache_get):
        mock_cache_get.return_value = None
        self.assertFalse(Poll.get_brick_polls_ids(self.uganda))
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        poll1 = self.create_poll(
            self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True, has_synced=True
        )

        self.assertFalse(Poll.get_brick_polls_ids(self.uganda))
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        PollQuestion.objects.create(
            poll=poll1, title="question poll 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        self.assertFalse(Poll.get_brick_polls_ids(self.uganda))
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", self.health_uganda, self.admin, has_synced=True)

        self.assertFalse(Poll.get_brick_polls_ids(self.uganda))
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        PollQuestion.objects.create(
            poll=poll2, title="question poll 2", ruleset_uuid="uuid-202", created_by=self.admin, modified_by=self.admin
        )

        self.assertTrue(Poll.get_brick_polls_ids(self.uganda))
        self.assertTrue(poll2.pk in Poll.get_brick_polls_ids(self.uganda))
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        poll2.is_active = False
        poll2.save()

        self.assertFalse(Poll.get_brick_polls_ids(self.uganda))
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        poll2.is_active = True
        poll2.save()
        self.health_uganda.is_active = False
        self.health_uganda.save()

        self.assertFalse(Poll.get_brick_polls_ids(self.uganda))
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        self.health_uganda.is_active = True
        self.health_uganda.save()

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin, has_synced=True)

        self.assertTrue(Poll.get_brick_polls_ids(self.uganda))
        self.assertTrue(poll2.pk in Poll.get_brick_polls_ids(self.uganda))
        self.assertTrue(poll3.pk not in Poll.get_brick_polls_ids(self.uganda))
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        PollQuestion.objects.create(
            poll=poll3, title="question poll 3", ruleset_uuid="uuid-303", created_by=self.admin, modified_by=self.admin
        )

        self.assertTrue(Poll.get_brick_polls_ids(self.uganda))
        self.assertTrue(poll2.pk in Poll.get_brick_polls_ids(self.uganda))
        self.assertTrue(poll3.pk in Poll.get_brick_polls_ids(self.uganda))

        with patch("ureport.polls.models.Poll.get_first_question") as mock_first_question:
            mock_first_question.return_value = None

            self.assertFalse(Poll.get_brick_polls_ids(self.uganda))

        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        poll3.is_featured = True
        poll3.save()

        self.assertTrue(Poll.get_brick_polls_ids(self.uganda))
        self.assertTrue(poll2.pk in Poll.get_brick_polls_ids(self.uganda))
        self.assertTrue(poll1.pk in Poll.get_brick_polls_ids(self.uganda))
        self.assertEqual(Poll.get_brick_polls_ids(self.uganda)[0], poll1.pk)
        self.assertEqual(Poll.get_brick_polls_ids(self.uganda)[1], poll2.pk)
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

        poll1.is_featured = False
        poll1.save()

        self.assertTrue(Poll.get_brick_polls_ids(self.uganda))
        self.assertTrue(poll2.pk in Poll.get_brick_polls_ids(self.uganda))
        self.assertTrue(poll1.pk in Poll.get_brick_polls_ids(self.uganda))
        self.assertEqual(Poll.get_brick_polls_ids(self.uganda)[0], poll2.pk)
        self.assertEqual(Poll.get_brick_polls_ids(self.uganda)[1], poll1.pk)
        self.assertFalse(Poll.get_brick_polls_ids(self.nigeria))

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
            PollQuestion.objects.create(
                poll=poll,
                title="question poll %s" % i,
                ruleset_uuid="uuid-10-%s" % i,
                created_by=self.admin,
                modified_by=self.admin,
            )

            polls.append(poll)

        self.assertTrue(Poll.get_other_polls(self.uganda))
        self.assertEqual(list(Poll.get_other_polls(self.uganda)), [polls[3], polls[2], polls[1], polls[0]])

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
            PollQuestion.objects.create(
                poll=poll,
                title="question poll %s" % i,
                ruleset_uuid="uuid-10-%s" % i,
                created_by=self.admin,
                modified_by=self.admin,
            )

            polls.append(poll)

        self.assertTrue(Poll.get_recent_polls(self.uganda))
        self.assertEqual(list(Poll.get_recent_polls(self.uganda)), list(reversed(polls[:9])))

        now = timezone.now()
        a_month_ago = now - timedelta(days=30)

        Poll.objects.filter(pk__in=[polls[0].pk, polls[1].pk]).update(created_on=a_month_ago)

        self.assertTrue(Poll.get_recent_polls(self.uganda))
        self.assertEqual(list(Poll.get_recent_polls(self.uganda)), list(reversed(polls[2:9])))

    def test_get_flow(self):
        with patch("dash.orgs.models.Org.get_flows") as mock:
            mock.return_value = {"uuid-1": "Flow"}

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

            self.assertEquals(poll1.get_flow(), "Flow")
            mock.assert_called_once_with(backend=poll1.backend)

    @patch("django.core.cache.cache.get")
    def test_most_responded_regions(self, mock_cache_get):
        mock_cache_get.return_value = None

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        PollQuestion.objects.create(
            poll=poll1, title="question poll 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        with patch("ureport.polls.models.PollQuestion.get_results") as mock:
            mock.return_value = [
                {
                    "open_ended": False,
                    "label": "Abia",
                    "set": 338,
                    "unset": 36,
                    "boundary": "R3713501",
                    "categories": [{"count": 80, "label": "Yes"}, {"count": 258, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Adamawa",
                    "set": 84,
                    "unset": 7,
                    "boundary": "R3720358",
                    "categories": [{"count": 41, "label": "Yes"}, {"count": 43, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Akwa Ibom",
                    "set": 149,
                    "unset": 14,
                    "boundary": "R3715359",
                    "categories": [{"count": 41, "label": "Yes"}, {"count": 108, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Anambra",
                    "set": 319,
                    "unset": 50,
                    "boundary": "R3715505",
                    "categories": [{"count": 81, "label": "Yes"}, {"count": 238, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Bauchi",
                    "set": 59,
                    "unset": 5,
                    "boundary": "R3722233",
                    "categories": [{"count": 20, "label": "Yes"}, {"count": 39, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Bayelsa",
                    "set": 102,
                    "unset": 11,
                    "boundary": "R3715844",
                    "categories": [{"count": 26, "label": "Yes"}, {"count": 76, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Benue",
                    "set": 267,
                    "unset": 27,
                    "boundary": "R3716076",
                    "categories": [{"count": 115, "label": "Yes"}, {"count": 152, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Borno",
                    "set": 76,
                    "unset": 5,
                    "boundary": "R3721167",
                    "categories": [{"count": 16, "label": "Yes"}, {"count": 60, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Cross River",
                    "set": 120,
                    "unset": 17,
                    "boundary": "R3716250",
                    "categories": [{"count": 29, "label": "Yes"}, {"count": 91, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Delta",
                    "set": 168,
                    "unset": 22,
                    "boundary": "R3716950",
                    "categories": [{"count": 39, "label": "Yes"}, {"count": 129, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Ebonyi",
                    "set": 134,
                    "unset": 14,
                    "boundary": "R3717071",
                    "categories": [{"count": 24, "label": "Yes"}, {"count": 110, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Edo",
                    "set": 193,
                    "unset": 17,
                    "boundary": "R3717119",
                    "categories": [{"count": 50, "label": "Yes"}, {"count": 143, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Ekiti",
                    "set": 151,
                    "unset": 22,
                    "boundary": "R3717154",
                    "categories": [{"count": 27, "label": "Yes"}, {"count": 124, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Enugu",
                    "set": 291,
                    "unset": 37,
                    "boundary": "R3717212",
                    "categories": [{"count": 109, "label": "Yes"}, {"count": 182, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Federal Capital Territory",
                    "set": 940,
                    "unset": 87,
                    "boundary": "R3717259",
                    "categories": [{"count": 328, "label": "Yes"}, {"count": 612, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Gombe",
                    "set": 73,
                    "unset": 7,
                    "boundary": "R3720422",
                    "categories": [{"count": 26, "label": "Yes"}, {"count": 47, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Imo",
                    "set": 233,
                    "unset": 14,
                    "boundary": "R3717825",
                    "categories": [{"count": 50, "label": "Yes"}, {"count": 183, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Jigawa",
                    "set": 69,
                    "unset": 5,
                    "boundary": "R3703236",
                    "categories": [{"count": 26, "label": "Yes"}, {"count": 43, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Kaduna",
                    "set": 291,
                    "unset": 34,
                    "boundary": "R3709353",
                    "categories": [{"count": 121, "label": "Yes"}, {"count": 170, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Kano",
                    "set": 222,
                    "unset": 23,
                    "boundary": "R3710302",
                    "categories": [{"count": 79, "label": "Yes"}, {"count": 143, "label": "No"}],
                },
                {
                    "open_ended": False,
                    "label": "Katsina",
                    "set": 293,
                    "unset": 23,
                    "boundary": "R3711481",
                    "categories": [{"count": 105, "label": "Yes"}, {"count": 188, "label": "No"}],
                },
            ]

            results = [
                {
                    "percent": 91,
                    "boundary": "Federal Capital Territory",
                    "total": 1027,
                    "type": "best",
                    "responded": 940,
                },
                {"percent": 90, "boundary": "Abia", "total": 374, "type": "best", "responded": 338},
                {"percent": 86, "boundary": "Anambra", "total": 369, "type": "best", "responded": 319},
                {"percent": 92, "boundary": "Katsina", "total": 316, "type": "best", "responded": 293},
                {"percent": 89, "boundary": "Kaduna", "total": 325, "type": "best", "responded": 291},
            ]

            self.assertEqual(poll1.most_responded_regions(), results)
            mock.assert_called_once_with(segment=dict(location="State"))
            mock.reset_mock()

            with patch("ureport.polls.models.PollQuestion.is_open_ended") as mock_open_ended:
                mock_open_ended.return_value = True

                self.assertEqual(poll1.most_responded_regions(), results)
                mock.assert_called_once_with(segment=dict(location="State"))

        with patch("ureport.polls.models.PollQuestion.get_results") as mock:
            mock.return_value = None

            results = []

            self.assertEqual(poll1.most_responded_regions(), results)
            mock.assert_called_once_with(segment=dict(location="State"))

    def test_runs(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEqual(poll1.runs(), "----")

        PollQuestion.objects.create(
            poll=poll1, title="question poll 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        with patch("ureport.polls.models.PollQuestion.get_polled") as mock:
            mock.return_value = 100

            self.assertEqual(poll1.runs(), 100)
            mock.assert_called_with()

    def test_responded_runs(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEqual(poll1.responded_runs(), "---")

        PollQuestion.objects.create(
            poll=poll1, title="question poll 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        with patch("ureport.polls.models.PollQuestion.get_responded") as mock:
            mock.return_value = 40

            self.assertEqual(poll1.responded_runs(), 40)
            mock.assert_called_once_with()

    def test_response_percentage(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        self.assertEqual(poll1.response_percentage(), "---")

        PollQuestion.objects.create(
            poll=poll1, title="question poll 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

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
            self.assertTrue("form" in response.context)

            self.assertEqual(len(response.context["form"].fields), 5)
            self.assertTrue("is_featured" in response.context["form"].fields)
            self.assertTrue("title" in response.context["form"].fields)
            self.assertTrue("category" in response.context["form"].fields)
            self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
            self.assertEqual(
                list(response.context["form"].fields["category"].choices),
                [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
            )
            self.assertTrue("category_image" in response.context["form"].fields)
            self.assertTrue("loc" in response.context["form"].fields)

            response = self.client.post(create_url, dict(), SERVER_NAME="uganda.ureport.io")
            self.assertTrue(response.context["form"].errors)

            self.assertEqual(len(response.context["form"].errors), 2)
            self.assertTrue("title" in response.context["form"].errors)
            self.assertTrue("category" in response.context["form"].errors)
            self.assertFalse(Poll.objects.all())

            post_data = dict(title="Poll 1", category=self.health_uganda.pk)

            response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
            self.assertTrue(Poll.objects.all())

            poll = Poll.objects.get()
            self.assertEquals(poll.title, "Poll 1")
            self.assertEquals(poll.backend.slug, "rapidpro")
            self.assertEquals(poll.org, self.uganda)

            self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_poll_flow", args=[poll.pk]))

            self.assertEqual(Poll.objects.all().count(), 1)

            # new submission should not create a new poll
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
            tz = pytz.timezone("Africa/Kigali")
            with patch.object(timezone, "now", return_value=tz.localize(datetime(2015, 9, 4, 3, 4, 5, 0))):
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
                self.assertTrue("form" in response.context)

                self.assertEqual(len(response.context["form"].fields), 5)
                self.assertFalse("backend" in response.context["form"].fields)

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
                self.assertTrue("form" in response.context)

                self.assertEqual(len(response.context["form"].fields), 6)
                self.assertTrue("is_featured" in response.context["form"].fields)
                self.assertTrue("title" in response.context["form"].fields)
                self.assertTrue("category" in response.context["form"].fields)
                self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
                self.assertEqual(
                    list(response.context["form"].fields["category"].choices),
                    [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
                )
                self.assertTrue("category_image" in response.context["form"].fields)
                self.assertTrue("loc" in response.context["form"].fields)

                self.assertTrue("backend" in response.context["form"].fields)
                self.assertEquals(len(response.context["form"].fields["backend"].choices), 3)
                self.assertEquals(
                    set(response.context["form"].fields["backend"].choices),
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
                poll.poll_date.astimezone(self.uganda.timezone).replace(tzinfo=pytz.UTC),
                yesterday.replace(microsecond=0),
            )

            self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_questions", args=[poll.pk]))

            tz = pytz.timezone("Africa/Kigali")
            with patch.object(timezone, "now", return_value=tz.localize(datetime(2015, 9, 4, 3, 4, 5, 0))):
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
            self.assertTrue("form" in response.context)

            self.assertEqual(len(response.context["form"].fields), 6)
            self.assertTrue("is_active" in response.context["form"].fields)
            self.assertTrue("is_featured" in response.context["form"].fields)
            self.assertTrue("title" in response.context["form"].fields)
            self.assertTrue("category" in response.context["form"].fields)
            self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
            self.assertEqual(
                list(response.context["form"].fields["category"].choices),
                [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
            )
            self.assertTrue("category_image" in response.context["form"].fields)
            self.assertTrue("loc" in response.context["form"].fields)

            response = self.client.post(uganda_update_url, dict(), SERVER_NAME="uganda.ureport.io")
            self.assertTrue("form" in response.context)
            self.assertTrue(response.context["form"].errors)
            self.assertEqual(len(response.context["form"].errors), 2)
            self.assertTrue("title" in response.context["form"].errors)
            self.assertTrue("category" in response.context["form"].errors)

            post_data = dict(title="title updated", category=self.health_uganda.pk, is_featured=False)
            response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
            updated_poll = Poll.objects.get(pk=poll1.pk)
            self.assertEqual(updated_poll.title, "title updated")
            self.assertFalse(updated_poll.is_featured)

            self.assertEqual(response.request["PATH_INFO"], reverse("polls.poll_poll_date", args=[updated_poll.pk]))

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
        self.assertRegexpMatches(response.content.decode("utf-8"), "Last synced 5(.*)minutes ago")

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

        PollQuestion.objects.create(
            poll=poll1,
            title="question poll 1",
            ruleset_label="question poll 1",
            ruleset_uuid="uuid-101",
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(uganda_questions_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 4)
        self.assertTrue("ruleset_uuid-101_include" in response.context["form"].fields)
        self.assertTrue("ruleset_uuid-101_priority" in response.context["form"].fields)
        self.assertTrue("ruleset_uuid-101_label" in response.context["form"].fields)
        self.assertTrue("ruleset_uuid-101_title" in response.context["form"].fields)
        self.assertEqual(response.context["form"].fields["ruleset_uuid-101_priority"].initial, 0)
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
        response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")

        self.assertTrue(PollQuestion.objects.filter(poll=poll1))

        poll_question = PollQuestion.objects.filter(poll=poll1)[0]
        self.assertEqual(poll_question.title, "electricity network coverage")
        self.assertEqual(poll_question.ruleset_label, "question poll 1")
        self.assertEqual(poll_question.priority, 5)

        with patch("ureport.polls.models.Poll.clear_brick_polls_cache") as mock:
            mock.return_value = "Cache cleared"

            post_data = dict()
            post_data["ruleset_uuid-101_include"] = True
            post_data["ruleset_uuid-101_title"] = "electricity network coverage"
            response = self.client.post(uganda_questions_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")

            mock.assert_called_once_with(poll1.org)

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
        from ureport.polls.templatetags.ureport import config, org_color, transparency, show_org_flags
        from ureport.polls.templatetags.ureport import org_host_link, org_arrow_link, question_results

        with patch("dash.orgs.models.Org.get_config") as mock:
            mock.return_value = "Done"

            self.assertIsNone(config(None, "field_name"))
            self.assertEquals(config(self.uganda, "field_name"), "Done")
            mock.assert_called_with("field_name")

        self.assertIsNone(org_color(None, 1))
        self.assertEqual(org_color(self.uganda, 0), "#FFD100")
        self.assertEqual(org_color(self.uganda, 1), "#1F49BF")
        self.assertEqual(org_color(self.uganda, 2), "#FFD100")
        self.assertEqual(org_color(self.uganda, 3), "#1F49BF")

        self.uganda.set_config("common.primary_color", "#aaaaaa")

        self.assertEqual(org_color(self.uganda, 0), "#FFD100")
        self.assertEqual(org_color(self.uganda, 1), "#1F49BF")
        self.assertEqual(org_color(self.uganda, 2), "#FFD100")
        self.assertEqual(org_color(self.uganda, 3), "#1F49BF")

        self.uganda.set_config("common.secondary_color", "#bbbbbb")

        self.assertEqual(org_color(self.uganda, 0), "#aaaaaa")
        self.assertEqual(org_color(self.uganda, 1), "#bbbbbb")
        self.assertEqual(org_color(self.uganda, 2), "#aaaaaa")
        self.assertEqual(org_color(self.uganda, 3), "#bbbbbb")

        self.uganda.set_config("common.colors", "#cccccc, #dddddd, #eeeeee, #111111, #222222, #333333, #444444")

        self.assertEqual(org_color(self.uganda, 0), "#cccccc")
        self.assertEqual(org_color(self.uganda, 1), "#dddddd")
        self.assertEqual(org_color(self.uganda, 2), "#eeeeee")
        self.assertEqual(org_color(self.uganda, 3), "#111111")
        self.assertEqual(org_color(self.uganda, 4), "#222222")
        self.assertEqual(org_color(self.uganda, 5), "#333333")
        self.assertEqual(org_color(self.uganda, 6), "#444444")
        self.assertEqual(org_color(self.uganda, 7), "#cccccc")
        self.assertEqual(org_color(self.uganda, 8), "#dddddd")
        self.assertEqual(org_color(self.uganda, 9), "#eeeeee")
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

            show_org_flags(dict(is_iorg=True, request=request))
            mock_get_linked_orgs.assert_called_with(True)

            request.user = Mock(spec=User, is_authenticated=False)
            show_org_flags(dict(is_iorg=True, request=request))
            mock_get_linked_orgs.assert_called_with(False)

        request = Mock(spec=HttpRequest)
        request.user = User.objects.get(pk=1)

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

            poll1_question = PollQuestion.objects.create(
                poll=poll1,
                title="question poll 1",
                ruleset_uuid="uuid-101",
                created_by=self.admin,
                modified_by=self.admin,
            )

            self.assertEqual(question_results(poll1_question), "Results")

            mock_results.side_effect = KeyError

            self.assertFalse(question_results(poll1_question))

        with patch("ureport.polls.models.PollQuestion.get_results") as mock_results:
            mock_results.return_value = ["Results"]

            poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

            poll1_question = PollQuestion.objects.create(
                poll=poll1,
                title="question poll 1",
                ruleset_uuid="uuid-101",
                created_by=self.admin,
                modified_by=self.admin,
            )

            self.assertEqual(question_segmented_results(poll1_question, "gender"), ["Results"])

            mock_results.side_effect = KeyError

            self.assertFalse(question_segmented_results(poll1_question, "gender"))

    def test_delete_poll_results_counter(self):
        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        poll_question = PollQuestion.objects.create(
            poll=poll, title="question 1", ruleset_uuid="step-uuid", created_by=self.admin, modified_by=self.admin
        )

        self.assertFalse(PollResultsCounter.objects.all())

        PollResult.objects.create(
            org=self.nigeria,
            flow=poll.flow_uuid,
            ruleset=poll_question.ruleset_uuid,
            date=timezone.now(),
            contact="contact-uuid",
            completed=False,
        )

        with self.settings(
            CACHES={
                "default": {
                    "BACKEND": "django_redis.cache.RedisCache",
                    "LOCATION": "127.0.0.1:6379:1",
                    "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
                }
            }
        ):
            poll.rebuild_poll_results_counts()

            self.assertTrue(PollResultsCounter.objects.all())

            poll.stopped_syncing = True
            poll.save()

            poll.delete_poll_results_counter()

            self.assertTrue(PollResultsCounter.objects.all())

            poll.stopped_syncing = False
            poll.save()

            poll.delete_poll_results_counter()

            self.assertFalse(PollResultsCounter.objects.all())

    def test_delete_poll_stats(self):
        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        poll_question = PollQuestion.objects.create(
            poll=poll, title="question 1", ruleset_uuid="step-uuid", created_by=self.admin, modified_by=self.admin
        )

        self.assertFalse(PollStats.objects.all())

        PollResult.objects.create(
            org=self.nigeria,
            flow=poll.flow_uuid,
            ruleset=poll_question.ruleset_uuid,
            date=timezone.now(),
            contact="contact-uuid",
            completed=False,
        )

        with self.settings(
            CACHES={
                "default": {
                    "BACKEND": "django_redis.cache.RedisCache",
                    "LOCATION": "127.0.0.1:6379:1",
                    "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
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

    def test_delete_poll_results(self):
        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        poll_question = PollQuestion.objects.create(
            poll=poll, title="question 1", ruleset_uuid="step-uuid", created_by=self.admin, modified_by=self.admin
        )
        PollResult.objects.create(
            org=self.nigeria,
            flow=poll.flow_uuid,
            ruleset=poll_question.ruleset_uuid,
            date=timezone.now(),
            contact="contact-uuid",
            completed=False,
        )

        poll.delete_poll_results()

        self.assertFalse(PollResult.objects.filter(org=self.nigeria, flow=poll.flow_uuid))

    @patch("dash.orgs.models.Org.get_backend")
    @patch("ureport.tests.TestBackend.pull_results")
    def test_poll_pull_results(self, mock_pull_results, mock_get_backend):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

        poll = self.create_poll(self.nigeria, "Poll 1", "flow-uuid", self.education_nigeria, self.admin)

        self.assertFalse(poll.has_synced)
        Poll.pull_results(poll.pk)

        poll = Poll.objects.get(pk=poll.pk)
        self.assertTrue(poll.has_synced)

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

        poll_question1 = PollQuestion.objects.create(
            poll=poll1, title="question 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-1", "Yes")
        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-2", "No")

        calculated_results = [
            dict(open_ended=False, set=0, unset=0, categories=[dict(count=0, label="Yes"), dict(count=0, label="No")])
        ]

        self.assertEqual(poll_question1.calculate_results(), calculated_results)

        PollResponseCategory.objects.all().delete()

        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-2", "No")
        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-1", "Yes")

        calculated_results = [
            dict(open_ended=False, set=0, unset=0, categories=[dict(count=0, label="No"), dict(count=0, label="Yes")])
        ]

        self.assertEqual(poll_question1.calculate_results(), calculated_results)

    def test_poll_question_model(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, featured=True)

        poll_question1 = PollQuestion.objects.create(
            poll=poll1, title="question 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        self.assertEqual(six.text_type(poll_question1), "question 1")

        # no response category are ignored
        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-4", "No Response")

        self.assertFalse(poll_question1.is_open_ended())

        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-1", "Yes")

        self.assertTrue(poll_question1.is_open_ended())

        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-2", "No")
        PollResponseCategory.objects.filter(category="No").update(is_active=False)

        self.assertTrue(poll_question1.is_open_ended())

        PollResponseCategory.objects.filter(category="No").update(is_active=True)

        self.assertFalse(poll_question1.is_open_ended())

        # should be ignored in calculated results
        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-3", "Other")

        now = timezone.now()

        PollResult.objects.create(
            org=self.uganda,
            flow=poll1.flow_uuid,
            ruleset=poll_question1.ruleset_uuid,
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
            ruleset=poll_question1.ruleset_uuid,
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
            ruleset=poll_question1.ruleset_uuid,
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
            ruleset=poll_question1.ruleset_uuid,
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
            ruleset=poll_question1.ruleset_uuid,
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
            ruleset=poll_question1.ruleset_uuid,
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
            ruleset=poll_question1.ruleset_uuid,
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
            self.assertEquals(PollWordCloud.objects.all().count(), 1)

            # another run will keep the same DB object
            poll_question1.generate_word_cloud()
            self.assertTrue(PollWordCloud.objects.all())
            self.assertEquals(PollWordCloud.objects.all().count(), 1)

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

        poll_question1 = PollQuestion.objects.create(
            poll=poll1, title="question 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        self.assertEqual(six.text_type(poll_question1), "question 1")

        # no response category are ignored
        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-4", "No Response")

        self.assertFalse(poll_question1.is_open_ended())

        yes_category = PollResponseCategory.update_or_create(poll_question1, "rule-uuid-1", "Yes")

        self.assertTrue(poll_question1.is_open_ended())

        no_category = PollResponseCategory.update_or_create(poll_question1, "rule-uuid-2", "No")
        PollResponseCategory.objects.filter(category="No").update(is_active=False)

        self.assertTrue(poll_question1.is_open_ended())

        PollResponseCategory.objects.filter(category="No").update(is_active=True)

        self.assertFalse(poll_question1.is_open_ended())

        # should be ignored in calculated results
        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-3", "Other")

        male_gender = GenderSegment.objects.filter(gender="M").first()
        female_gender = GenderSegment.objects.filter(gender="F").first()

        age_segment_20 = AgeSegment.objects.filter(min_age=20).first()
        age_segment_25 = AgeSegment.objects.filter(min_age=25).first()

        now = timezone.now()

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=None,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=yes_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=no_category,
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
            category=no_category,
            age_segment=None,
            gender_segment=male_gender,
            location=None,
            date=None,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=no_category,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=None,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=yes_category,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=None,
            count=3,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=None,
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
            category=no_category,
            age_segment=age_segment_20,
            gender_segment=None,
            location=None,
            date=None,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=no_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=None,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=yes_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=None,
            count=3,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=None,
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

        poll_question1 = PollQuestion.objects.create(
            poll=poll1, title="question 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        self.assertEqual(six.text_type(poll_question1), "question 1")

        # no response category are ignored
        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-4", "No Response")

        self.assertFalse(poll_question1.is_open_ended())

        yes_category = PollResponseCategory.update_or_create(poll_question1, "rule-uuid-1", "Yes")

        self.assertTrue(poll_question1.is_open_ended())

        no_category = PollResponseCategory.update_or_create(poll_question1, "rule-uuid-2", "No")
        PollResponseCategory.objects.filter(category="No").update(is_active=False)

        self.assertTrue(poll_question1.is_open_ended())

        PollResponseCategory.objects.filter(category="No").update(is_active=True)

        self.assertFalse(poll_question1.is_open_ended())

        # should be ignored in calculated results
        PollResponseCategory.update_or_create(poll_question1, "rule-uuid-3", "Other")

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
            category=None,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=yes_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=no_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=no_category,
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
            category=no_category,
            age_segment=None,
            gender_segment=None,
            location=None,
            date=now,
            count=4,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=no_category,
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
            category=no_category,
            age_segment=None,
            gender_segment=male_gender,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=no_category,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=yes_category,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=None,
            count=3,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=None,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=now,
            count=5,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=None,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=now,
            count=4,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=None,
            age_segment=None,
            gender_segment=female_gender,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
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
            category=None,
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
            category=no_category,
            age_segment=age_segment_20,
            gender_segment=None,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=no_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=yes_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=3,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=None,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=5,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=yes_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=4,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=None,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=2,
        )

        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=yes_category,
            age_segment=age_segment_25,
            gender_segment=None,
            location=None,
            date=now,
            count=1,
        )
        PollStats.objects.create(
            org=self.uganda,
            question=poll_question1,
            category=None,
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
        self.org = self.create_org("burundi", pytz.timezone("Africa/Bujumbura"), self.admin)

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

        self.poll_question = PollQuestion.objects.create(
            poll=self.poll, title="question 1", ruleset_uuid="step-uuid", created_by=self.admin, modified_by=self.admin
        )

        self.now = timezone.now()
        self.last_week = self.now - timedelta(days=7)
        self.last_month = self.now - timedelta(days=30)

    def test_poll_results_counters(self):
        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), dict())

        poll_result = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
            date=self.now,
            contact="contact-uuid",
            completed=False,
        )

        self.poll.rebuild_poll_results_counts()

        expected = dict()
        expected["ruleset:%s:total-ruleset-polled" % self.poll_question.ruleset_uuid] = 1

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

        poll_result.state = "R-LAGOS"
        poll_result.save()
        self.poll.rebuild_poll_results_counts()

        expected["ruleset:%s:nocategory:state:R-LAGOS" % self.poll_question.ruleset_uuid] = 1
        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

        poll_result.category = "Yes"
        poll_result.save()
        self.poll.rebuild_poll_results_counts()

        expected = dict()
        expected["ruleset:%s:total-ruleset-polled" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:category:yes:state:R-LAGOS" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:category:yes" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:total-ruleset-responded" % self.poll_question.ruleset_uuid] = 1

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
            contact="contact-uuid",
            category="No",
            text="Nah",
            completed=False,
            date=self.now,
            state="R-LAGOS",
            district="R-oyo",
            ward="R-IKEJA",
        )

        self.poll.rebuild_poll_results_counts()

        expected = dict()
        expected["ruleset:%s:total-ruleset-polled" % self.poll_question.ruleset_uuid] = 2
        expected["ruleset:%s:total-ruleset-responded" % self.poll_question.ruleset_uuid] = 2
        expected["ruleset:%s:category:yes" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:category:no" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:category:yes:state:R-LAGOS" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:category:no:state:R-LAGOS" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:category:no:district:R-OYO" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:category:no:ward:R-IKEJA" % self.poll_question.ruleset_uuid] = 1

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

    def test_poll_results_without_category(self):

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), dict())

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
            date=self.now,
            contact="contact-uuid",
            completed=False,
            state="R-LAGOS",
            district="R-OYO",
            ward="R-IKEJA",
        )

        self.poll.rebuild_poll_results_counts()

        expected = dict()
        expected["ruleset:%s:total-ruleset-polled" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:nocategory:state:R-LAGOS" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:nocategory:district:R-OYO" % self.poll_question.ruleset_uuid] = 1
        expected["ruleset:%s:nocategory:ward:R-IKEJA" % self.poll_question.ruleset_uuid] = 1

        self.assertEqual(PollResultsCounter.get_poll_results(self.poll), expected)

    def test_contact_activity(self):
        self.assertFalse(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
            date=self.now,
            contact="contact-uuid",
            completed=False,
        )

        self.assertFalse(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
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

        PollResult.objects.create(
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
        )

        self.assertTrue(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid"))
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid").count(), 12)
        self.assertFalse(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid").exclude(born=None))
        self.assertFalse(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid")
            .exclude(gender="")
            .exclude(gender=None)
        )
        self.assertTrue(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid")
            .exclude(state="")
            .exclude(state=None)
        )
        self.assertTrue(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid")
            .exclude(district="")
            .exclude(district=None)
        )
        self.assertTrue(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid")
            .exclude(ward="")
            .exclude(ward=None)
        )

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid2",
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

        self.assertTrue(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid2"))
        self.assertEqual(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid2").count(), 12)
        self.assertTrue(ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid2").exclude(born=None))
        self.assertTrue(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid2")
            .exclude(gender="")
            .exclude(gender=None)
        )
        self.assertTrue(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid2")
            .exclude(state="")
            .exclude(state=None)
        )
        self.assertTrue(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid2")
            .exclude(district="")
            .exclude(district=None)
        )
        self.assertTrue(
            ContactActivity.objects.filter(org=self.nigeria, contact="contact-uuid2")
            .exclude(ward="")
            .exclude(ward=None)
        )

    def test_poll_result_generate_stats(self):
        poll_result1 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
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
                    self.poll_question.ruleset_uuid,
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
                    self.now.replace(hour=0, minute=0, second=0, microsecond=0),
                )
            ],
        )

        poll_result5 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
            date=None,
            contact="contact-uuid",
            completed=False,
        )

        gen_stats = poll_result5.generate_poll_stats()
        self.assertEqual(len(gen_stats.keys()), 1)
        self.assertEqual(
            list(gen_stats.keys()), [(self.nigeria.id, self.poll_question.ruleset_uuid, "", "", "", "", "", "", None)]
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
            name="NigerLagosia",
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

        yes_category = PollResponseCategory.objects.create(question=self.poll_question, category="Yes")

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
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
        self.assertEqual(poll_stat.question, self.poll_question)
        self.assertEqual(poll_stat.category, yes_category)
        self.assertEqual(poll_stat.location, ikeja_boundary)
        self.assertEqual(poll_stat.gender_segment, GenderSegment.objects.get(gender="M"))
        self.assertEqual(poll_stat.age_segment, AgeSegment.objects.get(min_age=0))
        self.assertEqual(poll_stat.date, self.now.replace(hour=0, minute=0, second=0, microsecond=0))

        PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
            contact="contact-uuid",
            category="Yes",
            text="Yeah",
            completed=False,
            date=self.now,
        )

        self.poll.rebuild_poll_results_counts()
        self.assertEqual(PollStats.objects.all().count(), 2)
        self.assertEqual(
            PollStats.objects.filter(question=self.poll_question).aggregate(Sum("count"))["count__sum"], 2
        )
        self.assertEqual(PollStats.objects.filter(category=yes_category).aggregate(Sum("count"))["count__sum"], 2)
        self.assertEqual(PollStats.objects.filter(location=ikeja_boundary).aggregate(Sum("count"))["count__sum"], 1)

    def test_poll_result_generate_counters(self):
        poll_result1 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset=self.poll_question.ruleset_uuid,
            date=self.now,
            contact="contact-uuid",
            completed=False,
        )

        gen_counters = poll_result1.generate_counters()
        self.assertEqual(len(gen_counters.keys()), 1)
        self.assertTrue("ruleset:%s:total-ruleset-polled" % self.poll_question.ruleset_uuid in gen_counters.keys())

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
        )

        gen_counters = poll_result2.generate_counters()

        ruleset = poll_result2.ruleset.lower()
        category = poll_result2.category.lower()
        state = poll_result2.state.upper()
        district = poll_result2.district.upper()
        ward = poll_result2.ward.upper()

        self.assertEqual(len(gen_counters.keys()), 6)

        self.assertTrue("ruleset:%s:total-ruleset-polled" % ruleset in gen_counters.keys())
        self.assertTrue("ruleset:%s:total-ruleset-responded" % ruleset in gen_counters.keys())
        self.assertTrue("ruleset:%s:category:%s" % (ruleset, category) in gen_counters.keys())
        self.assertTrue("ruleset:%s:category:%s:state:%s" % (ruleset, category, state) in gen_counters.keys())
        self.assertTrue("ruleset:%s:category:%s:district:%s" % (ruleset, category, district) in gen_counters.keys())
        self.assertTrue("ruleset:%s:category:%s:ward:%s" % (ruleset, category, ward) in gen_counters.keys())

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
        )

        gen_counters = poll_result3.generate_counters()

        ruleset = poll_result3.ruleset.lower()
        state = poll_result3.state.upper()
        district = poll_result3.district.upper()
        ward = poll_result3.ward.upper()

        self.assertEqual(len(gen_counters.keys()), 4)

        self.assertTrue("ruleset:%s:total-ruleset-polled" % ruleset in gen_counters.keys())
        self.assertFalse("ruleset:%s:total-ruleset-responded" % ruleset in gen_counters.keys())  # no response ignored
        self.assertTrue("ruleset:%s:nocategory:state:%s" % (ruleset, state) in gen_counters.keys())
        self.assertTrue("ruleset:%s:nocategory:district:%s" % (ruleset, district) in gen_counters.keys())
        self.assertTrue("ruleset:%s:nocategory:ward:%s" % (ruleset, ward) in gen_counters.keys())

        poll_result4 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid",
            category="No Response",
            text="Some text",
            completed=False,
            date=self.now,
            state="R-LAGOS",
            district="R-oyo",
            ward="R-IKEJA",
        )

        gen_counters = poll_result4.generate_counters()

        ruleset = poll_result4.ruleset.lower()
        state = poll_result4.state.upper()
        district = poll_result4.district.upper()
        ward = poll_result4.ward.upper()

        self.assertEqual(len(gen_counters.keys()), 4)

        self.assertTrue("ruleset:%s:total-ruleset-polled" % ruleset in gen_counters.keys())
        self.assertFalse(
            "ruleset:%s:total-ruleset-responded" % ruleset in gen_counters.keys()
        )  # no response should be ignored
        self.assertTrue("ruleset:%s:nocategory:state:%s" % (ruleset, state) in gen_counters.keys())
        self.assertTrue("ruleset:%s:nocategory:district:%s" % (ruleset, district) in gen_counters.keys())
        self.assertTrue("ruleset:%s:nocategory:ward:%s" % (ruleset, ward) in gen_counters.keys())

        poll_result5 = PollResult.objects.create(
            org=self.nigeria,
            flow=self.poll.flow_uuid,
            ruleset="other-uuid",
            contact="contact-uuid",
            category="Other",
            text="Some suprise",
            completed=False,
            date=self.now,
            state="R-LAGOS",
            district="R-oyo",
            ward="R-IKEJA",
        )

        gen_counters = poll_result5.generate_counters()

        ruleset = poll_result5.ruleset.lower()
        state = poll_result5.state.upper()
        district = poll_result5.district.upper()
        ward = poll_result5.ward.upper()

        self.assertEqual(len(gen_counters.keys()), 4)

        self.assertTrue("ruleset:%s:total-ruleset-polled" % ruleset in gen_counters.keys())
        self.assertFalse("ruleset:%s:total-ruleset-responded" % ruleset in gen_counters.keys())  # Other ignored
        self.assertTrue("ruleset:%s:nocategory:state:%s" % (ruleset, state) in gen_counters.keys())
        self.assertTrue("ruleset:%s:nocategory:district:%s" % (ruleset, district) in gen_counters.keys())
        self.assertTrue("ruleset:%s:nocategory:ward:%s" % (ruleset, ward) in gen_counters.keys())


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

    @patch("dash.orgs.models.Org.get_backend")
    @patch("ureport.tests.TestBackend.pull_results")
    @patch("ureport.polls.models.Poll.get_main_poll")
    def test_pull_results_main_poll(self, mock_get_main_poll, mock_pull_results, mock_get_backend):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_get_main_poll.return_value = self.poll
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

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

    @patch("dash.orgs.models.Org.get_backend")
    @patch("ureport.tests.TestBackend.pull_results")
    @patch("ureport.polls.models.Poll.get_brick_polls_ids")
    def test_pull_results_brick_polls(self, mock_get_brick_polls_ids, mock_pull_results, mock_get_backend):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_get_brick_polls_ids.return_value = [poll.pk for poll in self.polls_query]
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

        pull_results_brick_polls(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key="results-pull-brick-polls")
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

        pull_results_brick_polls(self.nigeria.pk)

        task_state = TaskState.objects.get(org=self.nigeria, task_key="results-pull-brick-polls")
        self.assertEqual(task_state.get_last_results(), {})
        mock_pull_results.assert_called_once()

    @patch("dash.orgs.models.Org.get_backend")
    @patch("django.core.cache.cache.get")
    @patch("ureport.tests.TestBackend.pull_results")
    @patch("ureport.polls.models.Poll.get_other_polls")
    def test_pull_results_other_polls(self, mock_get_other_polls, mock_pull_results, mock_cache_get, mock_get_backend):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_get_other_polls.return_value = self.polls_query
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)
        mock_cache_get.return_value = None

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

    @patch("dash.orgs.models.Org.get_backend")
    @patch("ureport.tests.TestBackend.pull_results")
    def test_backfill_poll_results(self, mock_pull_results, mock_get_backend):
        mock_get_backend.return_value = TestBackend(self.rapidpro_backend)
        mock_pull_results.return_value = (1, 2, 3, 4, 5, 6)

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
