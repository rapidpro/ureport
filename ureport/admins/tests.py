# -*- coding: utf-8 -*-

from mock import patch

from django.urls import reverse

from dash.dashblocks.models import DashBlock, DashBlockType
from ureport.admins import OrgCache
from ureport.tests import UreportTest


class PollTest(UreportTest):
    def setUp(self):
        super(PollTest, self).setUp()

    def test_refresh_cache_view(self):
        refresh_cache_url = reverse("admins.org_refresh_cache", args=[self.uganda.pk])

        post_data = dict(cache=1)

        with patch("ureport.admins.views.refresh_caches") as mock_refresh_caches:
            mock_refresh_caches.return_value = None

            response = self.client.get(refresh_cache_url, SERVER_NAME="uganda.ureport.io")
            self.assertLoginRedirect(response)

            response = self.client.post(refresh_cache_url, post_data, SERVER_NAME="uganda.ureport.io")
            self.assertLoginRedirect(response)

            self.login(self.admin)

            response = self.client.get(refresh_cache_url, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(403, response.status_code)

            response = self.client.post(refresh_cache_url, post_data, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(403, response.status_code)

            self.login(self.superuser)

            response = self.client.post(refresh_cache_url, post_data, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 302)
            mock_refresh_caches.assert_called_once_with(self.uganda, [OrgCache.boundaries])
            mock_refresh_caches.reset_mock()

            response = self.client.post(refresh_cache_url, post_data, SERVER_NAME="uganda.ureport.io", follow=True)
            self.assertEqual(response.context["org"], self.uganda)
            self.assertEqual(response.request["PATH_INFO"], reverse("orgs.org_home"))
            self.assertContains(response, "Refreshed boundaries cache for this organization")

            mock_refresh_caches.assert_called_once_with(self.uganda, [OrgCache.boundaries])


class CustomPageDashBlockTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.custom_page_type = DashBlockType.objects.get_or_create(
            slug="additional_menu",
            defaults=dict(name="Custom pages", has_link=True, created_by=self.admin, modified_by=self.admin),
        )[0]
        self.about_type = DashBlockType.objects.get_or_create(
            slug="about",
            defaults=dict(name="About", has_link=True, created_by=self.admin, modified_by=self.admin),
        )[0]

    def create_block(self, org, block_type, link):
        return DashBlock.objects.create(
            title="Block",
            content="Content",
            link=link,
            dashblock_type=block_type,
            org=org,
            created_by=self.admin,
            modified_by=self.admin,
        )

    def post_create(self, block_type, link):
        url = reverse("dashblocks.dashblock_create") + f"?type={block_type.id}"
        post_data = dict(title="Page", content="Content", link=link, priority=0)
        return self.client.post(url, post_data, SERVER_NAME="uganda.ureport.io")

    def test_create(self):
        self.login(self.admin)

        response = self.post_create(self.custom_page_type, "")
        self.assertFormError(response.context["form"], "link", "This field is required.")

        response = self.post_create(self.custom_page_type, "faq page")
        self.assertFormError(
            response.context["form"], "link", "The link can only contain letters, numbers, underscores and hyphens"
        )

        response = self.post_create(self.custom_page_type, "faq/page")
        self.assertFormError(
            response.context["form"], "link", "The link can only contain letters, numbers, underscores and hyphens"
        )

        response = self.post_create(self.custom_page_type, "faq-page_2")
        self.assertEqual(response.status_code, 302)
        block = DashBlock.objects.get(org=self.uganda, dashblock_type=self.custom_page_type)
        self.assertEqual(block.link, "faq-page_2")

        response = self.post_create(self.custom_page_type, "faq-page_2")
        self.assertFormError(response.context["form"], "link", "Another page already uses this link")

        # unicode letters are allowed
        response = self.post_create(self.custom_page_type, "à-propos")
        self.assertEqual(response.status_code, 302)

        # the same link can be used in another org
        self.create_block(self.nigeria, self.custom_page_type, "about")
        response = self.post_create(self.custom_page_type, "about")
        self.assertEqual(response.status_code, 302)

        # other block types are left alone
        response = self.post_create(self.about_type, "https://example.com/about us")
        self.assertEqual(response.status_code, 302)
        response = self.post_create(self.about_type, "")
        self.assertEqual(response.status_code, 302)

    def test_update(self):
        block = self.create_block(self.uganda, self.custom_page_type, "faq")
        self.create_block(self.uganda, self.custom_page_type, "contact")
        self.create_block(self.nigeria, self.custom_page_type, "help")
        url = reverse("dashblocks.dashblock_update", args=[block.id])

        def post_update(link):
            post_data = dict(title="Page", content="Content", link=link, priority=0, is_active=True)
            return self.client.post(url, post_data, SERVER_NAME="uganda.ureport.io")

        self.login(self.admin)

        response = post_update("")
        self.assertFormError(response.context["form"], "link", "This field is required.")

        response = post_update("f.a.q")
        self.assertFormError(
            response.context["form"], "link", "The link can only contain letters, numbers, underscores and hyphens"
        )

        response = post_update("contact")
        self.assertFormError(response.context["form"], "link", "Another page already uses this link")

        # keeping its own link is fine
        response = post_update("faq")
        self.assertEqual(response.status_code, 302)

        # the same link can be used in another org
        response = post_update("help")
        self.assertEqual(response.status_code, 302)
        block.refresh_from_db()
        self.assertEqual(block.link, "help")

        # other block types are left alone
        other = self.create_block(self.uganda, self.about_type, "contact")
        response = self.client.post(
            reverse("dashblocks.dashblock_update", args=[other.id]),
            dict(title="About", content="Content", link="", priority=0, is_active=True),
            SERVER_NAME="uganda.ureport.io",
        )
        self.assertEqual(response.status_code, 302)
