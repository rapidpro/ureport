# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals


from django.urls import reverse
from mock import patch
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
            self.assertLoginRedirect(response)

            response = self.client.post(refresh_cache_url, post_data, SERVER_NAME="uganda.ureport.io")
            self.assertLoginRedirect(response)

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
