# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import zoneinfo
from datetime import timedelta
from urllib.parse import quote

import mock

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from dash.categories.models import Category
from dash.dashblocks.models import DashBlock, DashBlockType
from dash.orgs.models import TaskState
from dash.stories.models import Story
from ureport.assets.models import Image
from ureport.countries.models import CountryAlias
from ureport.news.models import NewsItem
from ureport.polls.models import Poll
from ureport.tests import MockTembaClient, UreportJobsTest, UreportTest


class PublicTest(UreportTest):
    def setUp(self):
        super(PublicTest, self).setUp()
        self.uganda = self.create_org("uganda", zoneinfo.ZoneInfo("Africa/Kampala"), self.admin)
        self.nigeria = self.create_org("nigeria", zoneinfo.ZoneInfo("Africa/Lagos"), self.admin)

        self.health_uganda = Category.objects.create(
            org=self.uganda, name="Health", created_by=self.admin, modified_by=self.admin
        )

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

    def test_org_config_fields(self):
        edit_url = reverse("orgs.org_edit")

        # make sure we only have one backend configured
        self.nigeria.backends.exclude(slug="rapidpro").delete()

        response = self.client.get(edit_url, SERVER_NAME="nigeria.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(edit_url, SERVER_NAME="nigeria.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 48)

        self.login(self.superuser)
        response = self.client.get(edit_url, SERVER_NAME="nigeria.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 71)

    def test_count(self):
        count_url = reverse("public.count")

        response = self.client.get(count_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertTrue("count" in response.context)
        self.assertEqual(response.context["count"], self.nigeria.get_reporters_count())
        self.assertEqual(response.context["view"].template_name, "public/count")

        response = self.client.get(count_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["org"], self.uganda)
        self.assertTrue("count" in response.context)
        self.assertEqual(response.context["count"], self.uganda.get_reporters_count())
        self.assertEqual(response.context["view"].template_name, "public/count")

    def test_has_better_domain_processors(self):
        home_url = reverse("public.index")

        # using subdomain wihout domain on org, login is shown and indexing should be allow
        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertNotContains(response, '<meta name="robots" content="noindex"')
        # self.assertContains(response, "nigeria.ureport.io/users/login/")

        self.nigeria.domain = "ureport.ng"
        self.nigeria.save()

        # using subdomain without domain on org, indexing is disallowed but login should be shown
        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertContains(response, '<meta name="robots" content="noindex"')
        # self.assertContains(response, "nigeria.ureport.io/users/login/")

        # using custom domain, login is hidden  and indexing should be allow
        response = self.client.get(home_url, HTTP_HOST="ureport.ng")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertNotContains(response, '<meta name="robots" content="noindex"')
        self.assertNotContains(response, "nigeria.ureport.io/users/login/")

    def test_org_lang_params_processors(self):
        home_url = reverse("public.index")

        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertFalse(response.context["is_rtl_org"])
        self.assertEqual(response.context["org_lang"], "en_US")

        self.nigeria.language = "ar"
        self.nigeria.save()

        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertTrue(response.context["is_rtl_org"])
        self.assertEqual(response.context["org_lang"], "ar_AR")

        self.nigeria.language = "es"
        self.nigeria.save()

        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertFalse(response.context["is_rtl_org"])
        self.assertEqual(response.context["org_lang"], "es_ES")

    def test_stories_link(self):
        home_url = reverse("public.index")
        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(reverse("public.stories"), response.context["stories_link"])

        self.nigeria.set_config("external_stories_link", "https://example.com/stories")

        home_url = reverse("public.index")
        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual("https://example.com/stories", response.context["stories_link"])

    def test_set_story_widget_url(self):
        home_url = reverse("public.index")
        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertTrue(response.context["story_widget_url"])

    @mock.patch("dash.orgs.models.TembaClient", MockTembaClient)
    @mock.patch("django.core.cache.cache.get")
    @mock.patch("ureport.public.views.get_global_count")
    def test_index(self, mock_get_global_count, mock_cache_get):
        mock_get_global_count.return_value = 0
        mock_cache_get.return_value = None
        home_url = reverse("public.index")

        response = self.client.get(home_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["view"].template_name, "public/index.html")

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertIsNone(response.context["latest_poll"])
        self.assertTrue("gender_stats" in response.context)
        self.assertTrue("age_stats" in response.context)
        self.assertTrue("reporters" in response.context)
        self.assertTrue("main_stories" in response.context)
        self.assertFalse(response.context["main_stories"])

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, has_synced=True)

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertIsNone(response.context["latest_poll"])

        self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertEqual(poll1, response.context["latest_poll"])

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, has_synced=True)

        self.create_poll_question(self.admin, poll2, "question poll 2", "uuid-202")

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertEqual(poll1, response.context["latest_poll"])

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin, has_synced=True)

        self.create_poll_question(self.admin, poll3, "question poll 3", "uuid-303")

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertEqual(poll3, response.context["latest_poll"])

        story1 = Story.objects.create(
            title="story 1",
            featured=True,
            content="body contents 1",
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["main_stories"])
        self.assertTrue(story1 in response.context["main_stories"])

        story2 = Story.objects.create(
            title="story 2",
            featured=True,
            content="body contents 2",
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["main_stories"])
        self.assertFalse(story2 in response.context["main_stories"])

        story3 = Story.objects.create(
            title="story 3",
            featured=False,
            content="body contents 3",
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["main_stories"])
        self.assertFalse(story3 in response.context["main_stories"])

        story4 = Story.objects.create(
            title="story 4",
            featured=True,
            content="body contents 4",
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["main_stories"])
        self.assertFalse(story2 in response.context["main_stories"])
        self.assertFalse(story3 in response.context["main_stories"])
        self.assertEqual(response.context["main_stories"][0].pk, story4.pk)

        story4.featured = False
        story4.save()

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertFalse(story4 in response.context["main_stories"])

    def test_additional_menu(self):
        additional_menu_url = reverse("public.custom_page", args=["faq"])
        custom_page_dashblock_type = DashBlockType.objects.get_or_create(
            name="Custom pages",
            slug="additional_menu",
            description="U-Report custom pages",
            has_title=True,
            has_image=True,
            has_rich_text=False,
            has_summary=False,
            has_link=True,
            has_gallery=False,
            has_color=False,
            has_video=False,
            has_tags=False,
            created_by=self.admin,
            modified_by=self.admin,
        )[0]

        DashBlock.objects.create(
            title="Custom page",
            content="Content...",
            dashblock_type=custom_page_dashblock_type,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(additional_menu_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/page/faq/")
        self.assertEqual(response.context["org"], self.nigeria)

    def test_about(self):
        about_url = reverse("public.about")

        response = self.client.get(about_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["view"].template_name, "public/about.html")

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        partner1_logo = Image.objects.create(
            name="partner1",
            image="images/image.jpg",
            image_type="A",
            priority=1,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["partners_logos"])
        self.assertTrue(partner1_logo in response.context["partners_logos"])

        partner2_logo = Image.objects.create(
            name="partner2",
            image="images/image.jpg",
            image_type="A",
            priority=1,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["partners_logos"])
        self.assertTrue(partner1_logo in response.context["partners_logos"])
        self.assertTrue(partner2_logo not in response.context["partners_logos"])

        partner3_logo = Image.objects.create(
            name="partner2",
            image="images/image.jpg",
            image_type="A",
            priority=1,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["partners_logos"])
        self.assertTrue(partner1_logo in response.context["partners_logos"])
        self.assertTrue(partner2_logo not in response.context["partners_logos"])
        self.assertTrue(partner3_logo in response.context["partners_logos"])

        partner1_logo.is_active = False
        partner1_logo.save()

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["partners_logos"])
        self.assertTrue(partner1_logo not in response.context["partners_logos"])
        self.assertTrue(partner2_logo not in response.context["partners_logos"])
        self.assertTrue(partner3_logo in response.context["partners_logos"])

    def test_join_engage(self):
        join_engage_url = reverse("public.join")

        response = self.client.get(join_engage_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/join/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["view"].template_name, "public/join_engage.html")

        response = self.client.get(join_engage_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/join/")
        self.assertEqual(response.context["org"], self.uganda)

        # add shortcode and a join dashblock
        self.uganda.set_config("common.shortcode", "3000")
        join_dashblock_type = DashBlockType.objects.filter(slug="join_engage").first()

        DashBlock.objects.create(
            title="Join",
            content="Join",
            dashblock_type=join_dashblock_type,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(join_engage_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/join/")
        self.assertEqual(response.context["org"], self.uganda)
        # self.assertContains(response, "All U-Report services (all msg on 3000) are free.")

    def test_poll_results(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, has_synced=True)

        question1 = self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")

        pollquestion_results_url = reverse("public.pollquestion_results", args=[question1.pk])

        response = self.client.get(pollquestion_results_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], f"/pollquestion/{question1.pk}/results/")

        response = self.client.get(
            pollquestion_results_url + "?segment=%0D%0ASPIHeader%3A%20SPIValue&", SERVER_NAME="uganda.ureport.io"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], f"/pollquestion/{question1.pk}/results/")

    def test_reporter_results(self):
        reporter_results_url = reverse("public.contact_field_results")

        response = self.client.get(reporter_results_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/contact_field_results/")

        response = self.client.get(
            reporter_results_url + "?segment=%0D%0ASPIHeader%3A%20SPIValue&", SERVER_NAME="nigeria.ureport.io"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/contact_field_results/")

    def test_engagement_data(self):
        ureporters_url = reverse("public.engagement_data")

        response = self.client.get(ureporters_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/engagement_data/")

        response = self.client.get(
            ureporters_url + "?results_params=%0D%0ASPIHeader%3A%20SPIValue&", SERVER_NAME="nigeria.ureport.io"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], "/engagement_data/")

    @mock.patch("ureport.utils.fetch_old_sites_count")
    def test_ureporters(self, mock_old_sites_count):
        mock_old_sites_count.return_value = []

        ureporters_url = reverse("public.engagement")

        response = self.client.get(ureporters_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/engagement/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["view"].template_name, "public/ureporters.html")

        self.assertTrue("months" in response.context)
        self.assertTrue("gender_stats" in response.context)
        self.assertTrue("age_stats" in response.context)
        self.assertTrue("registration_stats" in response.context)
        self.assertTrue("schemes_stats" in response.context)

        self.assertTrue("show_maps" in response.context)
        self.assertTrue("district_zoom" in response.context)
        self.assertTrue("ward_zoom" in response.context)
        self.assertTrue("show_age_stats" in response.context)
        self.assertTrue("show_gender_stats" in response.context)

        response = self.client.get(ureporters_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/engagement/")
        self.assertEqual(response.context["org"], self.uganda)

    @mock.patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_polls_list(self):
        polls_url = reverse("public.opinions")

        response = self.client.get(polls_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/opinions/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["tab"], "list")
        self.assertEqual(response.context["view"].template_name, "public/polls.html")
        self.assertFalse(response.context["latest_poll"])
        self.assertFalse(response.context["polls"])

        self.assertEqual(len(response.context["categories"]), 0)
        self.assertEqual(response.context["categories"], [])

        education_uganda = Category.objects.create(
            org=self.uganda, name="Education", created_by=self.admin, modified_by=self.admin
        )

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, has_synced=True)

        self.create_poll_question(self.admin, poll1, "question poll 1", "uuid-101")

        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", education_uganda, self.admin, has_synced=True)

        self.create_poll_question(self.admin, poll2, "question poll 2", "uuid-102")

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin, has_synced=True)
        self.create_poll_question(self.admin, poll3, "question poll 3", "uuid-103")

        poll4 = self.create_poll(self.nigeria, "Poll 4", "uuid-4", self.education_nigeria, self.admin, has_synced=True)

        self.create_poll_question(self.admin, poll4, "question poll 4", "uuid-104")

        response = self.client.get(polls_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/opinions/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["tab"], "list")
        self.assertEqual(response.context["view"].template_name, "public/polls.html")
        self.assertEqual(response.context["latest_poll"], poll4)

        self.assertEqual(len(response.context["categories"]), 1)
        self.assertEqual(response.context["categories"][0]["name"], self.education_nigeria.name)

        self.assertEqual(len(response.context["polls"]), 1)
        self.assertTrue(poll4 in response.context["polls"])
        self.assertTrue(poll1 not in response.context["polls"])
        self.assertTrue(poll2 not in response.context["polls"])
        self.assertTrue(poll3 not in response.context["polls"])

        story1 = Story.objects.create(
            title="story 1",
            content="body contents 1",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story2 = Story.objects.create(
            title="story 2",
            content="body contents 2",
            category=education_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story3 = Story.objects.create(
            title="story 3",
            content="body contents 3",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story4 = Story.objects.create(
            title="story 4",
            content="body contents 4",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(polls_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(len(response.context["main_stories"]), 0)
        self.assertTrue(story4 not in response.context["main_stories"])
        self.assertTrue(story1 not in response.context["main_stories"])
        self.assertTrue(story2 not in response.context["main_stories"])
        self.assertTrue(story3 not in response.context["main_stories"])

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/opinions/")
        self.assertEqual(response.context["org"], self.uganda)
        self.assertEqual(response.context["latest_poll"], poll3)

        self.assertEqual(len(response.context["categories"]), 2)
        self.assertEqual(response.context["categories"][0]["name"], education_uganda.name)
        self.assertEqual(response.context["categories"][1]["name"], self.health_uganda.name)

        self.assertEqual(len(response.context["polls"]), 3)
        self.assertTrue(poll4 not in response.context["polls"])
        self.assertTrue(poll1 in response.context["polls"])
        self.assertTrue(poll2 in response.context["polls"])
        self.assertTrue(poll3 in response.context["polls"])
        self.assertEqual(response.context["polls"][0], poll3)
        self.assertEqual(response.context["polls"][1], poll2)
        self.assertEqual(response.context["polls"][2], poll1)

        self.assertEqual(len(response.context["main_stories"]), 0)
        self.assertTrue(story4 not in response.context["main_stories"])
        self.assertTrue(story1 not in response.context["main_stories"])
        self.assertTrue(story2 not in response.context["main_stories"])
        self.assertTrue(story3 not in response.context["main_stories"])

        story1.featured = True
        story1.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["main_stories"]), 1)
        self.assertTrue(story1 in response.context["main_stories"])
        self.assertTrue(story4 not in response.context["main_stories"])
        self.assertTrue(story2 not in response.context["main_stories"])
        self.assertTrue(story3 not in response.context["main_stories"])
        self.assertEqual(response.context["main_stories"][0], story1)

        story1.is_active = False
        story1.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["main_stories"]), 0)
        self.assertTrue(story4 not in response.context["main_stories"])
        self.assertTrue(story1 not in response.context["main_stories"])
        self.assertTrue(story2 not in response.context["main_stories"])
        self.assertTrue(story3 not in response.context["main_stories"])

        poll1.is_featured = True
        poll1.save()
        Poll.find_main_poll(poll1.org)

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["latest_poll"], poll1)

        self.assertEqual(len(response.context["categories"]), 2)
        self.assertEqual(response.context["categories"][0]["name"], education_uganda.name)
        self.assertEqual(response.context["categories"][1]["name"], self.health_uganda.name)

        self.assertEqual(len(response.context["polls"]), 3)
        self.assertTrue(poll4 not in response.context["polls"])
        self.assertTrue(poll1 in response.context["polls"])
        self.assertTrue(poll2 in response.context["polls"])
        self.assertTrue(poll3 in response.context["polls"])
        self.assertEqual(response.context["polls"][0], poll3)
        self.assertEqual(response.context["polls"][1], poll2)
        self.assertEqual(response.context["polls"][2], poll1)

        poll1.poll_date = poll3.poll_date + timedelta(days=1)
        poll1.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["polls"][0], poll1)
        self.assertEqual(response.context["polls"][1], poll3)
        self.assertEqual(response.context["polls"][2], poll2)

        poll1.poll_date = poll1.created_on
        poll1.save()

        poll3.is_active = False
        poll3.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["latest_poll"], poll1)

        self.assertEqual(len(response.context["polls"]), 2)
        self.assertTrue(poll4 not in response.context["polls"])
        self.assertTrue(poll1 in response.context["polls"])
        self.assertTrue(poll2 in response.context["polls"])
        self.assertTrue(poll3 not in response.context["polls"])
        self.assertEqual(response.context["polls"][0], poll2)
        self.assertEqual(response.context["polls"][1], poll1)

        education_uganda.is_active = False
        education_uganda.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["latest_poll"], poll1)

        self.assertEqual(len(response.context["polls"]), 1)
        self.assertTrue(poll4 not in response.context["polls"])
        self.assertTrue(poll1 in response.context["polls"])
        self.assertTrue(poll2 not in response.context["polls"])
        self.assertTrue(poll3 not in response.context["polls"])
        self.assertEqual(response.context["polls"][0], poll1)

        poll1.has_synced = False
        poll1.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertFalse(response.context["polls"])

    @mock.patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_polls_read(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin)

        uganda_poll_read_url = reverse("public.opinion_read", args=[poll1.pk])
        nigeria_poll_read_url = reverse("public.opinion_read", args=[poll2.pk])

        response = self.client.get(uganda_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll1.has_synced = True
        poll1.save()

        response = self.client.get(uganda_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["object"], poll1)

        self.health_uganda.is_active = False
        self.health_uganda.save()

        response = self.client.get(uganda_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        response = self.client.get(nigeria_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll2.has_synced = True
        poll2.save()

        response = self.client.get(nigeria_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll1.is_active = False
        poll1.save()

        response = self.client.get(uganda_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll2.is_active = False
        poll2.save()

        response = self.client.get(nigeria_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

    @mock.patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_polls_preview(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin)

        uganda_poll_preview_url = reverse("public.opinion_preview", args=[poll1.pk])
        nigeria_poll_preview_url = reverse("public.opinion_preview", args=[poll2.pk])

        response = self.client.get(uganda_poll_preview_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(uganda_poll_preview_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["object"], poll1)
        self.assertContains(response, "Poll has not synced yet to be displayed to the public")

        poll1.has_synced = True
        poll1.save()

        response = self.client.get(uganda_poll_preview_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["object"], poll1)
        self.assertNotContains(response, "Poll has not synced yet to be displayed to the public")

        response = self.client.get(nigeria_poll_preview_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll2.has_synced = True
        poll2.save()

        response = self.client.get(nigeria_poll_preview_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll1.published = False
        poll1.save()

        response = self.client.get(uganda_poll_preview_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        poll1.is_active = False
        poll1.save()

        response = self.client.get(uganda_poll_preview_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll2.published = False
        poll2.save()

        response = self.client.get(nigeria_poll_preview_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll2.is_active = False
        poll2.save()

        response = self.client.get(nigeria_poll_preview_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

    def test_stories_list(self):
        stories_url = reverse("public.stories")

        education_uganda = Category.objects.create(
            org=self.uganda, name="Education", created_by=self.admin, modified_by=self.admin
        )

        story1 = Story.objects.create(
            title="story 1",
            content="body contents 1",
            category=self.health_uganda,
            featured=True,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story2 = Story.objects.create(
            title="story 2",
            content="body contents 2",
            category=education_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story3 = Story.objects.create(
            title="story 3",
            content="body contents 3",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story4 = Story.objects.create(
            title="story 4",
            content="body contents 4",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(stories_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(len(response.context["categories"]), 1)
        self.assertEqual(response.context["categories"][0], self.education_nigeria)
        self.assertEqual(len(response.context["main_stories"]), 0)

        response = self.client.get(stories_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["org"], self.uganda)
        self.assertEqual(len(response.context["categories"]), 2)
        self.assertEqual(response.context["categories"][0], education_uganda)
        self.assertEqual(response.context["categories"][1], self.health_uganda)

        self.assertEqual(len(response.context["main_stories"]), 1)
        self.assertEqual(response.context["main_stories"][0], story1)

        story2.is_active = False
        story2.save()

        response = self.client.get(stories_url, SERVER_NAME="uganda.ureport.io")

        self.assertEqual(len(response.context["main_stories"]), 1)
        self.assertEqual(response.context["main_stories"][0], story1)

        story2.is_active = True
        story2.save()
        education_uganda.is_active = False
        education_uganda.save()

        self.assertEqual(len(response.context["stories"]), 3)
        self.assertEqual(response.context["stories"][0], story1)
        self.assertTrue(story1 in response.context["stories"])
        self.assertTrue(story2 in response.context["stories"])
        self.assertTrue(story3 in response.context["stories"])
        self.assertFalse(story4 in response.context["stories"])

    def test_story_read(self):
        education_uganda = Category.objects.create(
            org=self.uganda, name="Education", created_by=self.admin, modified_by=self.admin
        )

        story1 = Story.objects.create(
            title="story 1",
            content="body contents 1",
            category=self.health_uganda,
            featured=True,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story2 = Story.objects.create(
            title="story 2",
            content="body contents 2",
            category=education_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story3 = Story.objects.create(
            title="story 3",
            content="body contents 3",
            category=self.health_uganda,
            featured=True,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story4 = Story.objects.create(
            title="story 4",
            content="body contents 4",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        uganda_story_read_url = reverse("public.story_read", args=[story1.pk])
        nigeria_story_read_url = reverse("public.story_read", args=[story4.pk])

        response = self.client.get(nigeria_story_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        response = self.client.get(uganda_story_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["org"], self.uganda)

        self.assertEqual(response.context["object"], story1)
        self.assertEqual(len(response.context["categories"]), 2)
        self.assertEqual(response.context["categories"][0], education_uganda)
        self.assertEqual(response.context["categories"][1], self.health_uganda)

        self.assertEqual(len(response.context["main_stories"]), 2)
        self.assertFalse(story4 in response.context["main_stories"])
        self.assertFalse(story2 in response.context["main_stories"])
        self.assertTrue(story1 in response.context["main_stories"])
        self.assertTrue(story3 in response.context["main_stories"])

    def test_news(self):
        news_url = reverse("public.news")

        self.uganda_news1 = NewsItem.objects.create(
            title="uganda news 1",
            description="uganda description 1",
            link="http://uganda.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(news_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(json.loads(response.content), dict(next=False, news=[self.uganda_news1.as_brick_json()]))

        response = self.client.get(news_url + "?page=1", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(json.loads(response.content), dict(next=False, news=[self.uganda_news1.as_brick_json()]))

        self.uganda_news2 = NewsItem.objects.create(
            title="uganda news 2",
            description="uganda description 2",
            link="http://uganda2.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.uganda_news3 = NewsItem.objects.create(
            title="uganda news 3",
            description="uganda description 3",
            link="http://uganda3.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.uganda_news4 = NewsItem.objects.create(
            title="uganda news 4",
            description="uganda description 4",
            link="http://uganda4.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.uganda_news5 = NewsItem.objects.create(
            title="uganda news 5",
            description="uganda description 5",
            link="http://uganda.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(news_url + "?page=1", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            json.loads(response.content),
            dict(
                next=True,
                news=[
                    self.uganda_news5.as_brick_json(),
                    self.uganda_news4.as_brick_json(),
                    self.uganda_news3.as_brick_json(),
                ],
            ),
        )

        response = self.client.get(news_url + "?page=2", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            json.loads(response.content),
            dict(next=False, news=[self.uganda_news2.as_brick_json(), self.uganda_news1.as_brick_json()]),
        )

        response = self.client.get(news_url + "?page=3", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(json.loads(response.content), dict(next=False, news=[]))

    def test_status_view(self):
        status_url = reverse("public.status")
        response = self.client.get(status_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(list(response.json())), 2)
        self.assertEqual(
            set(response.json()),
            set(
                {
                    "valkey_up",
                    "db_up",
                }
            ),
        )

    def test_task_status_view(self):
        status_url = reverse("public.task_status")
        response = self.client.get(status_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(list(response.json())), 3)
        self.assertEqual(set(response.json()), set({"contact_sync_up", "tasks", "failing_tasks"}))

        three_hours_ago = timezone.now() - timedelta(hours=3)
        TaskState.objects.create(
            org=self.uganda, task_key="contact-pull", last_successfully_started_on=three_hours_ago, is_disabled=False
        )
        response = self.client.get(status_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(list(response.json())), 3)
        self.assertEqual(set(response.json()), set({"contact_sync_up", "tasks", "failing_tasks"}))

        self.uganda.domain = "beta"
        self.uganda.save()

        response = self.client.get(status_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(list(response.json())), 3)
        self.assertEqual(set(response.json()), set({"contact_sync_up", "tasks", "failing_tasks"}))

    @mock.patch("django.core.cache.cache.get")
    def test_counts_status_view(self, mock_cache_get):
        mock_cache_get.return_value = {"mismatch_counts": {}, "error_counts": {}}

        status_url = reverse("public.counts_status")
        response = self.client.get(status_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        mock_cache_get.return_value = {
            "mismatch_counts": {},
            "error_counts": {f"{self.uganda.pk}": {"db": 0, "count": 1000, "count_diff": 1000, "pct_diff": 0}},
        }

        response = self.client.get(status_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 500)

    @override_settings(
        COUNTRY_FLAGS_SITES=[
            dict(
                name="Afghanistan",
                host="//afghanistan.ureport.in/",
                flag="flag_afghanistan.png",
                countries_codes=["AFG"],
                count_link="http://afghanistan.ureport.in/count/",
            ),
            dict(
                name="Argentina",
                host="//argentina.ureport.in/",
                flag="flag_argentina.png",
                countries_codes=["ARG"],
                count_link="http://argentina.ureport.in/count/",
            ),
            dict(
                name="South Asia",
                host="//southasia.ureport.in/",
                flag="flag_southasia.png",
                countries_codes=["AFG", "IND", "IDN", "NPL"],
                count_link="http://southasia.ureport.in/count/",
            ),
        ]
    )
    def test_shared_sites_count(self):
        shared_sites_count_url = reverse("public.shared_sites_count")

        response = self.client.post(shared_sites_count_url)
        self.assertEqual(response.status_code, 405)

        response = self.client.get(shared_sites_count_url)
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)

        self.assertTrue("global_count" in response_json)
        self.assertTrue("linked_sites" in response_json)
        self.assertTrue("countries_count" in response_json)
        self.assertEqual(response_json["countries_count"], 5)


class JobsTest(UreportJobsTest):
    def setUp(self):
        super(JobsTest, self).setUp()

    def test_jobs(self):
        fb_source_nigeria = self.create_fb_job_source(self.nigeria, self.nigeria.name)
        fb_source_uganda = self.create_fb_job_source(self.uganda, self.uganda.name)

        tw_source_nigeria = self.create_tw_job_source(self.nigeria, self.nigeria.name)
        tw_source_uganda = self.create_tw_job_source(self.uganda, self.uganda.name)

        jobs_url = reverse("public.jobs")

        response = self.client.get(jobs_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 404)

        self.nigeria.set_config("common.has_jobs", True)

        response = self.client.get(jobs_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["job_sources"])
        self.assertEqual(2, len(response.context["job_sources"]))
        self.assertEqual(set(response.context["job_sources"]), set([fb_source_nigeria, tw_source_nigeria]))

        response = self.client.get(jobs_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        self.uganda.set_config("common.has_jobs", True)

        response = self.client.get(jobs_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["job_sources"])
        self.assertEqual(2, len(response.context["job_sources"]))
        self.assertEqual(set(response.context["job_sources"]), set([fb_source_uganda, tw_source_uganda]))

        fb_source_nigeria.is_featured = True
        fb_source_nigeria.save()

        response = self.client.get(jobs_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["job_sources"])
        self.assertEqual(2, len(response.context["job_sources"]))
        self.assertEqual(fb_source_nigeria, response.context["job_sources"][0])
        self.assertEqual(tw_source_nigeria, response.context["job_sources"][1])

        fb_source_nigeria.is_active = False
        fb_source_nigeria.save()

        response = self.client.get(jobs_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["job_sources"])
        self.assertEqual(1, len(response.context["job_sources"]))
        self.assertTrue(tw_source_nigeria in response.context["job_sources"])

        tw_source_nigeria.is_active = False
        tw_source_nigeria.save()

        response = self.client.get(jobs_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["job_sources"])


class CountriesTest(UreportTest):
    def setUp(self):
        super(CountriesTest, self).setUp()

    def test_countries(self):
        countries_url = reverse("public.countries")

        response = self.client.post(countries_url, dict())
        self.assertEqual(response.status_code, 405)

        response = self.client.get(countries_url)
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("text" in response_json)
        self.assertEqual(response_json["exists"], "invalid")
        self.assertEqual(response_json["text"], "")
        self.assertFalse("country_code" in response_json)

        response = self.client.get(countries_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertEqual(response_json["exists"], "invalid")
        self.assertEqual(response_json["text"], "")
        self.assertFalse("country_code" in response_json)

        response = self.client.get(countries_url + "?text=OK")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertEqual(response_json["exists"], "invalid")
        self.assertEqual(response_json["text"], "OK")
        self.assertFalse("country_code" in response_json)

        response = self.client.get(countries_url + "?text=OK", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertEqual(response_json["exists"], "invalid")
        self.assertEqual(response_json["text"], "OK")
        self.assertFalse("country_code" in response_json)

        response = self.client.get(countries_url + "?text=RW")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "RW")

        response = self.client.get(countries_url + "?text=RW", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "RW")

        response = self.client.get(countries_url + "?text=USA")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        response = self.client.get(countries_url + "?text=rw")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "RW")

        response = self.client.get(countries_url + "?text=usa")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        CountryAlias.objects.create(name="Etats unies", country="US", created_by=self.admin, modified_by=self.admin)

        response = self.client.get(countries_url + "?text=Etats+Unies")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        # country text has quotes
        response = self.client.get(countries_url + '?text="Etats+Unies"')
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        # country text has quotes an spaces
        response = self.client.get(countries_url + '?text="    Etats+Unies  "')
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        # unicode aliases
        CountryAlias.objects.create(name="এ্যান্ডোরা", country="AD", created_by=self.admin, modified_by=self.admin)

        response = self.client.get(countries_url + "?text=%s" % quote("এ্যান্ডোরা"))

        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "AD")

        response = self.client.get(countries_url + '?text="   %s   "' % quote("এ্যান্ডোরা"))

        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "AD")

        # unicode aliases
        CountryAlias.objects.create(name="Madžarska", country="MD", created_by=self.admin, modified_by=self.admin)

        response = self.client.get(countries_url + "?text=%s" % quote("Madžarska"))

        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "MD")

        response = self.client.get(countries_url + '?text="   %s   "' % quote("Madžarska"))

        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "MD")
