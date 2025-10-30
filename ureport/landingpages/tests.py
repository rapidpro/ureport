from django.urls import reverse

from ureport.bots.models import Bot
from ureport.landingpages.models import LandingPage
from ureport.tests import UreportTest


class LandingPageTest(UreportTest):
    def test_create(self):
        create_url = reverse("landingpages.landingpage_create")

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].fields), 7)
        self.assertNotIn("org", response.context["form"].fields)

        post_data = dict()
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue(response.context["form"].errors)
        self.assertIn("title", response.context["form"].errors)

        post_data = dict(
            title="Welcome",
            content="Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            slug="lorem=2025",
        )

        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue(response.context["form"].errors)
        self.assertIn("slug", response.context["form"].errors)
        self.assertEqual(
            "The slug can only contain letters, numbers, underscores and hyphens",
            response.context["form"].errors["slug"][0],
        )

        post_data = dict(
            title="Welcome",
            content="Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
            slug="lorem",
        )

        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        landing_page = LandingPage.objects.order_by("-pk")[0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("landingpages.landingpage_list"))
        self.assertEqual(landing_page.title, "Welcome")
        self.assertEqual(landing_page.slug, "lorem")

        self.login(self.superuser)
        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].fields), 7)
        self.assertNotIn("org", response.context["form"].fields)

        post_data = dict(
            title="Foo Bar",
            content="Phasellus id arcu quis urna faucibus eleifend.",
            slug="foo",
        )

        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        landing_page = LandingPage.objects.order_by("-pk")[0]
        self.assertEqual(landing_page.title, "Foo Bar")
        self.assertEqual(landing_page.slug, "foo")

    def test_list(self):
        uganda_foo_lp = LandingPage.objects.create(
            org=self.uganda,
            title="foo",
            slug="foo",
            content="Foo, Foo.",
            created_by=self.admin,
            modified_by=self.admin,
        )

        uganda_bar_lp = LandingPage.objects.create(
            org=self.uganda,
            title="bar",
            slug="bar",
            content="Bar, Bar.",
            created_by=self.admin,
            modified_by=self.admin,
        )

        nigeria_foo_lp = LandingPage.objects.create(
            org=self.nigeria,
            title="foo",
            slug="foo",
            content="Foo, Foo.",
            created_by=self.admin,
            modified_by=self.admin,
        )

        list_url = reverse("landingpages.landingpage_list")

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["object_list"]), 2)

        self.assertNotIn(nigeria_foo_lp, response.context["object_list"])
        self.assertIn(uganda_foo_lp, response.context["object_list"])
        self.assertIn(uganda_bar_lp, response.context["object_list"])

        response = self.client.get(list_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(len(response.context["object_list"]), 1)
        self.assertNotIn(uganda_foo_lp, response.context["object_list"])
        self.assertNotIn(uganda_bar_lp, response.context["object_list"])
        self.assertIn(nigeria_foo_lp, response.context["object_list"])
        self.assertEqual(len(response.context["fields"]), 3)

        self.login(self.superuser)
        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["fields"]), 3)
        self.assertEqual(len(response.context["object_list"]), 2)
        self.assertIn(uganda_foo_lp, response.context["object_list"])
        self.assertIn(uganda_bar_lp, response.context["object_list"])
        self.assertNotIn(nigeria_foo_lp, response.context["object_list"])

    def test_bot_update(self):
        uganda_fb_bot = Bot.objects.create(
            org=self.uganda,
            featured=False,
            title="Facebook Bot",
            channel="HereWeGo",
            keyword="participate",
            facebook_deeplink="https://example.com/herewego",
            description="The Facebook channel",
            priority=2,
            created_by=self.admin,
            modified_by=self.admin,
        )

        # bot from othre org
        Bot.objects.create(
            org=self.nigeria,
            featured=True,
            title="WhatsApp",
            channel="+12555",
            keyword="join",
            facebook_deeplink="https://example.com/12555",
            description="The main channel",
            priority=1,
            created_by=self.admin,
            modified_by=self.admin,
        )

        uganda_foo_lp = LandingPage.objects.create(
            org=self.uganda,
            title="foo",
            slug="foo",
            content="Foo, Foo.",
            created_by=self.admin,
            modified_by=self.admin,
        )

        nigeria_foo_lp = LandingPage.objects.create(
            org=self.nigeria,
            title="foo",
            slug="foo",
            content="Foo, Foo.",
            created_by=self.admin,
            modified_by=self.admin,
        )

        uganda_update_url = reverse("landingpages.landingpage_update", args=[uganda_foo_lp.pk])
        nigeria_update_url = reverse("landingpages.landingpage_update", args=[nigeria_foo_lp.pk])

        response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(uganda_update_url, SERVER_NAME="nigeria.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].fields), 8)
        self.assertEqual(
            list(response.context["form"].fields["bots"].choices),
            [(uganda_fb_bot.pk, "Facebook Bot")],
        )

        post_data = dict(
            title="Bar Bar",
            content="Phasellus id arcu quis urna faucibus eleifend.",
            slug="bar",
        )

        response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], reverse("landingpages.landingpage_list"))
        landing_page = LandingPage.objects.get(pk=uganda_foo_lp.pk)
        self.assertEqual(landing_page.title, "Bar Bar")
        self.assertEqual(landing_page.slug, "bar")
        self.assertEqual(landing_page.content, "Phasellus id arcu quis urna faucibus eleifend.")
