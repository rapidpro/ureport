from django.urls import reverse

from ureport.bots.models import Bot
from ureport.tests import UreportTest


class BotTest(UreportTest):
    def test_create_bot(self):
        create_url = reverse("bots.bot_create")

        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].fields), 12)
        self.assertNotIn("org", response.context["form"].fields)

        post_data = dict()
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertTrue(response.context["form"].errors)
        self.assertIn("title", response.context["form"].errors)

        post_data = dict(
            featured=True,
            landing_page_only=False,
            title="WhatsApp",
            channel="+12345",
            keyword="join",
            facebook_deeplink="https://example.com/12345",
            description="The main channel",
            priority=1,
        )
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        bot = Bot.objects.order_by("-pk")[0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("bots.bot_list"))
        self.assertEqual(bot.title, "WhatsApp")
        self.assertEqual(bot.org, self.uganda)
        self.assertEqual(bot.channel, "+12345")
        self.assertEqual(bot.keyword, "join")
        self.assertEqual(bot.facebook_deeplink, "https://example.com/12345")
        self.assertEqual(bot.description, "The main channel")
        self.assertEqual(bot.priority, 1)
        self.assertTrue(bot.featured)
        self.assertFalse(bot.landing_page_only)

        self.login(self.superuser)
        response = self.client.get(create_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].fields), 12)
        self.assertNotIn("org", response.context["form"].fields)

        post_data = dict(
            title="Facebook",
            channel="HereWeGo",
            keyword="participate",
            facebook_deeplink="https://example.com/herewego",
            description="The Facebook channel",
            priority=2,
        )
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        bot = Bot.objects.order_by("-pk")[0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request["PATH_INFO"], reverse("bots.bot_list"))
        self.assertEqual(bot.title, "Facebook")
        self.assertEqual(bot.org, self.uganda)
        self.assertEqual(bot.channel, "HereWeGo")
        self.assertEqual(bot.keyword, "participate")
        self.assertEqual(bot.facebook_deeplink, "https://example.com/herewego")
        self.assertEqual(bot.description, "The Facebook channel")
        self.assertEqual(bot.priority, 2)
        self.assertFalse(bot.featured)
        self.assertFalse(bot.landing_page_only)

    def test_list(self):
        uganda_wa_bot = Bot.objects.create(
            org=self.uganda,
            featured=True,
            landing_page_only=False,
            title="WhatsApp",
            channel="+12345",
            keyword="join",
            facebook_deeplink="https://example.com/12345",
            description="The main channel",
            priority=1,
            created_by=self.admin,
            modified_by=self.admin,
        )

        uganda_fb_bot = Bot.objects.create(
            org=self.uganda,
            featured=False,
            landing_page_only=False,
            title="Facebook",
            channel="HereWeGo",
            keyword="participate",
            facebook_deeplink="https://example.com/herewego",
            description="The Facebook channel",
            priority=2,
            created_by=self.admin,
            modified_by=self.admin,
        )

        nigeria_wa_bot = Bot.objects.create(
            org=self.nigeria,
            featured=True,
            landing_page_only=False,
            title="WhatsApp",
            channel="+12555",
            keyword="join",
            facebook_deeplink="https://example.com/12555",
            description="The main channel",
            priority=1,
            created_by=self.admin,
            modified_by=self.admin,
        )

        list_url = reverse("bots.bot_list")

        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["object_list"]), 2)
        self.assertNotIn(nigeria_wa_bot, response.context["object_list"])
        self.assertIn(uganda_wa_bot, response.context["object_list"])
        self.assertIn(uganda_fb_bot, response.context["object_list"])

        response = self.client.get(list_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(len(response.context["object_list"]), 1)
        self.assertNotIn(uganda_wa_bot, response.context["object_list"])
        self.assertNotIn(uganda_wa_bot, response.context["object_list"])
        self.assertIn(nigeria_wa_bot, response.context["object_list"])
        self.assertEqual(len(response.context["fields"]), 5)

        self.login(self.superuser)
        response = self.client.get(list_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["fields"]), 5)
        self.assertEqual(len(response.context["object_list"]), 2)
        self.assertIn(uganda_wa_bot, response.context["object_list"])
        self.assertIn(uganda_wa_bot, response.context["object_list"])
        self.assertNotIn(nigeria_wa_bot, response.context["object_list"])

    def test_bot_update(self):
        uganda_fb_bot = Bot.objects.create(
            org=self.uganda,
            featured=False,
            landing_page_only=False,
            title="Facebook",
            channel="HereWeGo",
            keyword="participate",
            facebook_deeplink="https://example.com/herewego",
            description="The Facebook channel",
            priority=2,
            created_by=self.admin,
            modified_by=self.admin,
        )

        nigeria_wa_bot = Bot.objects.create(
            org=self.nigeria,
            featured=True,
            landing_page_only=False,
            title="WhatsApp",
            channel="+12555",
            keyword="join",
            facebook_deeplink="https://example.com/12555",
            description="The main channel",
            priority=1,
            created_by=self.admin,
            modified_by=self.admin,
        )

        uganda_update_url = reverse("bots.bot_update", args=[uganda_fb_bot.pk])
        nigeria_update_url = reverse("bots.bot_update", args=[nigeria_wa_bot.pk])

        response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(uganda_update_url, SERVER_NAME="nigeria.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_update_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["form"].fields), 13)

        post_data = dict(
            is_active=True,
            featured=True,
            landing_page_only=True,
            title="WhatsApp",
            channel="+12345",
            keyword="join",
            facebook_deeplink="https://example.com/12345",
            description="The main channel",
            priority=3,
        )
        response = self.client.post(uganda_update_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], reverse("bots.bot_list"))
        bot = Bot.objects.get(pk=uganda_fb_bot.pk)
        self.assertEqual(bot.title, "WhatsApp")
        self.assertEqual(bot.org, self.uganda)
        self.assertEqual(bot.channel, "+12345")
        self.assertEqual(bot.keyword, "join")
        self.assertEqual(bot.facebook_deeplink, "https://example.com/12345")
        self.assertEqual(bot.description, "The main channel")
        self.assertEqual(bot.priority, 3)
        self.assertTrue(bot.featured)
        self.assertTrue(bot.landing_page_only)
