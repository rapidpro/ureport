# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import reverse
from django.utils import formats

from dash.categories.fields import CategoryChoiceField
from dash.categories.models import Category
from ureport.news.models import NewsItem, Video
from ureport.tests import UreportTest


class NewsTest(UreportTest):
    def setUp(self):
        super(NewsTest, self).setUp()

        self.health_uganda = Category.objects.create(
            org=self.uganda, name="Health", created_by=self.admin, modified_by=self.admin
        )

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

    def test_newsItem_model(self):
        self.uganda_news1 = NewsItem.objects.create(
            title="uganda news 1",
            description="uganda description 1",
            link="http://uganda.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.assertTrue(self.uganda_news1.short_description(), "uganda description 1")

        self.uganda_news1.description = "a b" * 120
        self.assertTrue(self.uganda_news1.short_description(), "a b" * 100 + "...")

        self.assertEqual(
            self.uganda_news1.as_brick_json(),
            dict(
                title="uganda news 1",
                description="a b" * 100 + "...",
                link="http://uganda.ug",
                created_on=formats.date_format(self.uganda_news1.created_on, format="b d, Y", use_l10n=True),
            ),
        )

    def test_create_newsItem(self):
        create_url = reverse("news.newsitem_create")

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["form"].fields), 5)
        self.assertTrue("org" not in response.context["form"].fields)
        self.assertTrue("title" in response.context["form"].fields)
        self.assertTrue("description" in response.context["form"].fields)
        self.assertTrue("link" in response.context["form"].fields)
        self.assertTrue("category" in response.context["form"].fields)
        self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
        self.assertEqual(
            list(response.context["form"].fields["category"].choices),
            [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
        )
        self.assertTrue("loc" in response.context["form"].fields)

        self.assertEqual(NewsItem.objects.count(), 0)

        response = self.client.post(create_url, dict(), SERVER_NAME="uganda.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(response.context["form"].errors.keys()), 3)
        self.assertTrue("title" in response.context["form"].errors.keys())
        self.assertTrue("link" in response.context["form"].errors.keys())
        self.assertTrue("category" in response.context["form"].errors.keys())

        post_data = dict(title="news 1", link="http://google.com", follow=True, category=self.health_uganda.pk)
        response = self.client.post(create_url, post_data, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(NewsItem.objects.count(), 1)
        newsItem = NewsItem.objects.get()

        self.assertEqual(newsItem.title, "news 1")
        self.assertEqual(newsItem.category, self.health_uganda)
        self.assertEqual(newsItem.link, "http://google.com")

        self.login(self.superuser)

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["form"].fields), 6)
        self.assertTrue("org" in response.context["form"].fields)
        self.assertTrue("title" in response.context["form"].fields)
        self.assertTrue("description" in response.context["form"].fields)
        self.assertTrue("link" in response.context["form"].fields)
        self.assertTrue("category" in response.context["form"].fields)
        self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
        self.assertEqual(
            list(response.context["form"].fields["category"].choices),
            [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
        )
        self.assertTrue("loc" in response.context["form"].fields)

        response = self.client.post(create_url, dict(), SERVER_NAME="uganda.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(response.context["form"].errors.keys()), 4)
        self.assertTrue("org" in response.context["form"].errors.keys())
        self.assertTrue("title" in response.context["form"].errors.keys())
        self.assertTrue("link" in response.context["form"].errors.keys())
        self.assertTrue("category" in response.context["form"].errors.keys())

        post_data = dict(
            title="news 1", link="http://google.com", follow=True, category=self.health_uganda.pk, org=self.uganda.pk
        )
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertFalse("form" in response.context)
        self.assertEqual(NewsItem.objects.count(), 2)

    def test_list_newsItem(self):
        list_url = reverse("news.newsitem_list")

        self.uganda_news1 = NewsItem.objects.create(
            title="uganda news 1",
            description="uganda description 1",
            link="http://uganda.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.nigeria_news1 = NewsItem.objects.create(
            title="nigeria news 1",
            description="nigeria description 1",
            link="http://nigeria.ng",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["object_list"]), 1)
        self.assertTrue(self.uganda_news1 in response.context["object_list"])
        self.assertFalse(self.nigeria_news1 in response.context["object_list"])

    def test_update_newsItem(self):
        self.uganda_news1 = NewsItem.objects.create(
            title="uganda news 1",
            description="uganda description 1",
            link="http://uganda.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.nigeria_news1 = NewsItem.objects.create(
            title="nigeria news 1",
            description="nigeria description 1",
            link="http://nigeria.ng",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        uganda_update_url = reverse("news.newsitem_update", args=[self.uganda_news1.pk])
        nigeria_update_url = reverse("news.newsitem_update", args=[self.nigeria_news1.pk])

        response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 6)
        self.assertTrue("is_active" in response.context["form"].fields)
        self.assertTrue("title" in response.context["form"].fields)
        self.assertTrue("description" in response.context["form"].fields)
        self.assertTrue("link" in response.context["form"].fields)
        self.assertTrue("category" in response.context["form"].fields)
        self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
        self.assertEqual(
            list(response.context["form"].fields["category"].choices),
            [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
        )
        self.assertTrue("loc" in response.context["form"].fields)

        post_data = dict(
            title="title updated",
            description="description updated",
            link="http://updated.com",
            category=self.health_uganda.pk,
            is_active=False,
        )

        response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertFalse("form" in response.context)

        updated_news = NewsItem.objects.get(pk=self.uganda_news1.pk)
        self.assertFalse(updated_news.is_active)
        self.assertEqual(updated_news.title, "title updated")
        self.assertEqual(updated_news.description, "description updated")
        self.assertEqual(updated_news.link, "http://updated.com")


class VideoTest(UreportTest):
    def setUp(self):
        super(VideoTest, self).setUp()

        self.health_uganda = Category.objects.create(
            org=self.uganda, name="Health", created_by=self.admin, modified_by=self.admin
        )

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

    def test_create_video(self):
        create_url = reverse("news.video_create")

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["form"].fields), 5)
        self.assertTrue("org" not in response.context["form"].fields)
        self.assertTrue("title" in response.context["form"].fields)
        self.assertTrue("description" in response.context["form"].fields)
        self.assertTrue("video_id" in response.context["form"].fields)
        self.assertTrue("category" in response.context["form"].fields)
        self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
        self.assertEqual(
            list(response.context["form"].fields["category"].choices),
            [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
        )
        self.assertTrue("loc" in response.context["form"].fields)

        self.assertEqual(Video.objects.count(), 0)

        response = self.client.post(create_url, dict(), SERVER_NAME="uganda.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(response.context["form"].errors.keys()), 3)
        self.assertTrue("title" in response.context["form"].errors.keys())
        self.assertTrue("video_id" in response.context["form"].errors.keys())
        self.assertTrue("category" in response.context["form"].errors.keys())

        post_data = dict(
            title="video 1", description="awesome video", video_id="YoutubeID", category=self.health_uganda.pk
        )

        response = self.client.post(create_url, post_data, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(Video.objects.count(), 1)
        video = Video.objects.get()

        self.assertEqual(video.title, "video 1")
        self.assertEqual(video.description, "awesome video")
        self.assertEqual(video.video_id, "YoutubeID")
        self.assertEqual(video.category, self.health_uganda)
        self.assertEqual(video.org, self.uganda)

        self.login(self.superuser)

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["form"].fields), 6)
        self.assertTrue("org" in response.context["form"].fields)
        self.assertTrue("title" in response.context["form"].fields)
        self.assertTrue("description" in response.context["form"].fields)
        self.assertTrue("video_id" in response.context["form"].fields)
        self.assertTrue("category" in response.context["form"].fields)
        self.assertTrue("loc" in response.context["form"].fields)

        response = self.client.post(create_url, dict(), SERVER_NAME="uganda.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(response.context["form"].errors.keys()), 4)
        self.assertTrue("org" in response.context["form"].errors.keys())
        self.assertTrue("title" in response.context["form"].errors.keys())
        self.assertTrue("video_id" in response.context["form"].errors.keys())
        self.assertTrue("category" in response.context["form"].errors.keys())

        post_data = dict(
            title="video 1",
            description="awesome video",
            video_id="YoutubeID",
            category=self.health_uganda.pk,
            org=self.uganda.pk,
        )

        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertFalse("form" in response.context)
        self.assertEqual(Video.objects.count(), 2)

    def test_video_list(self):
        list_url = reverse("news.video_list")

        self.uganda_video = Video.objects.create(
            title="Visit Kampala",
            description="You are welcome to Kampala",
            video_id="Kplatown",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.nigeria_video = Video.objects.create(
            title="Football team",
            description="Nigerian national team",
            video_id="nigteam",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["object_list"]), 1)
        self.assertTrue(self.uganda_video in response.context["object_list"])
        self.assertFalse(self.nigeria_video in response.context["object_list"])

    def test_video_update(self):
        self.uganda_video = Video.objects.create(
            title="Visit Kampala",
            description="You are welcome to Kampala",
            video_id="Kplatown",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.nigeria_video = Video.objects.create(
            title="Football team",
            description="Nigerian national team",
            video_id="nigteam",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        uganda_update_url = reverse("news.video_update", args=[self.uganda_video.pk])
        nigeria_update_url = reverse("news.video_update", args=[self.nigeria_video.pk])

        response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(nigeria_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 6)
        self.assertTrue("is_active" in response.context["form"].fields)
        self.assertTrue("title" in response.context["form"].fields)
        self.assertTrue("description" in response.context["form"].fields)
        self.assertTrue("video_id" in response.context["form"].fields)
        self.assertTrue("category" in response.context["form"].fields)
        self.assertIsInstance(response.context["form"].fields["category"].choices.field, CategoryChoiceField)
        self.assertEqual(
            list(response.context["form"].fields["category"].choices),
            [("", "---------"), (self.health_uganda.pk, "uganda - Health")],
        )
        self.assertTrue("loc" in response.context["form"].fields)

        post_data = dict(
            title="title updated",
            description="description updated",
            video_id="newID",
            category=self.health_uganda.pk,
            is_active=False,
        )

        response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertFalse("form" in response.context)

        updated_video = Video.objects.get(pk=self.uganda_video.pk)
        self.assertEqual(updated_video.title, "title updated")
        self.assertEqual(updated_video.description, "description updated")
        self.assertEqual(updated_video.video_id, "newID")
        self.assertFalse(updated_video.is_active)
