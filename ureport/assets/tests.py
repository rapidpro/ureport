# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf import settings
from django.urls import reverse

from ureport.assets.models import Image
from ureport.tests import UreportTest


class ImageTest(UreportTest):
    def setUp(self):
        super(ImageTest, self).setUp()

    def clear_uploads(self):
        import os

        for bg in Image.objects.all():
            os.remove(bg.image.path)

    def test_assets_image(self):
        create_url = reverse("assets.image_create")

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].fields), 4)
        self.assertTrue("org" not in response.context["form"].fields)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "rb")

        post_data = dict(name="Orange Pattern", priority=0, image=upload)
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        uganda_org_bg = Image.objects.order_by("-pk")[0]
        self.assertEqual(uganda_org_bg.org, self.uganda)
        self.assertEqual(uganda_org_bg.name, "Orange Pattern")

        response = self.client.get(create_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].fields), 4)
        self.assertTrue("org" not in response.context["form"].fields)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "rb")

        post_data = dict(name="Orange Pattern", priority=1, image=upload)
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        nigeria_org_bg = Image.objects.order_by("-pk")[0]
        self.assertEqual(nigeria_org_bg.org, self.nigeria)
        self.assertEqual(nigeria_org_bg.name, "Orange Pattern")
        self.assertEqual(nigeria_org_bg.image_type, "A")

        list_url = reverse("assets.image_list")

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["object_list"]), 1)
        self.assertEqual(response.context["object_list"][0], uganda_org_bg)

        response = self.client.get(list_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(len(response.context["object_list"]), 1)
        self.assertEqual(response.context["object_list"][0], nigeria_org_bg)

        uganda_bg_update_url = reverse("assets.image_update", args=[uganda_org_bg.pk])
        nigeria_bg_update_url = reverse("assets.image_update", args=[nigeria_org_bg.pk])

        response = self.client.get(uganda_bg_update_url, SERVER_NAME="nigeria.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_bg_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_bg_update_url, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], uganda_bg_update_url)
        self.assertEqual(len(response.context["form"].fields), 5)
        self.assertTrue("org" not in response.context["form"].fields)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "rb")
        post_data = dict(name="Orange Pattern Updated", priority=0, image=upload)
        response = self.client.post(uganda_bg_update_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], list_url)
        self.assertEqual(len(response.context["object_list"]), 1)
        self.assertEqual(response.context["object_list"][0].name, "Orange Pattern Updated")

        self.login(self.superuser)
        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].fields), 6)
        self.assertTrue("org" in response.context["form"].fields)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "rb")

        post_data = dict(name="Blue Pattern", image_type="P", image=upload)
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertTrue("org" in response.context["form"].errors)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "rb")

        post_data = dict(name="Blue Pattern", image_type="P", priority=0, image=upload, org=self.uganda.pk)

        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue("form" not in response.context)
        blue_bg = Image.objects.get(name="Blue Pattern")
        self.assertEqual(blue_bg.org, self.uganda)

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["object_list"]), Image.objects.filter(org=self.uganda).count())

        response = self.client.get(nigeria_bg_update_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], nigeria_bg_update_url)
        self.assertEqual(len(response.context["form"].fields), 7)

        self.clear_uploads()
