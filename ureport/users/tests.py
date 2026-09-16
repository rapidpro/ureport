import re

from allauth.account.models import EmailAddress

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import URLPattern, URLResolver, reverse

from dash.orgs.middleware import ALLOW_NO_ORG
from ureport.tests import UreportTest

User = get_user_model()


def verify_email(user):
    """
    Marks the user's email as verified, as allauth does the first time they confirm it
    """
    EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"verified": True, "primary": True})


class LoginTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.editor = self.create_user("editor")
        self.editor.email = "editor@nyaruka.com"
        self.editor.set_password("Qwerty123")
        self.editor.save()
        verify_email(self.editor)

    def test_login(self):
        login_url = reverse("account_login")

        response = self.client.get(login_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Forgot Password?")
        self.assertContains(response, "Enter Dashboard")

        # fields on the login form are unlabeled with the label used as a placeholder
        self.assertContains(response, f'placeholder="{response.context["form"]["login"].label}"')

        # login is by email, not username
        response = self.client.post(
            login_url, {"login": "editor", "password": "Qwerty123"}, SERVER_NAME="nigeria.ureport.io"
        )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        response = self.client.post(
            login_url, {"login": "editor@nyaruka.com", "password": "wrong"}, SERVER_NAME="nigeria.ureport.io"
        )
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "The email address and/or password you specified are not correct.")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        response = self.client.post(
            login_url, {"login": "editor@nyaruka.com", "password": "Qwerty123"}, SERVER_NAME="nigeria.ureport.io"
        )
        self.assertRedirect(response, settings.LOGIN_REDIRECT_URL)
        self.assertEqual(self.editor, response.wsgi_request.user)

    def test_login_with_mixed_case_email(self):
        # the test base class creates users with mixed case emails, as staff might
        self.assertEqual("administrator@nyaruka.com", self.admin.email)
        verify_email(self.admin)

        self.client.logout()
        response = self.client.post(
            reverse("account_login"),
            {"login": "Administrator@nyaruka.com", "password": "Administrator"},
            SERVER_NAME="nigeria.ureport.io",
        )
        self.assertRedirect(response, settings.LOGIN_REDIRECT_URL)
        self.assertEqual(self.admin, response.wsgi_request.user)

    def test_login_requires_verified_email(self):
        login_url = reverse("account_login")
        credentials = {"login": self.admin.email, "password": "Administrator"}

        # existing users have never verified their email, so their first login sends them a confirmation
        response = self.client.post(login_url, credentials, SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, reverse("account_email_verification_sent"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual([self.admin.email], mail.outbox[0].to)
        confirm_url = re.search(
            r"https://nigeria\.ureport\.io(/accounts/confirm-email/\S+/)", mail.outbox[0].body
        ).group(1)

        response = self.client.get(reverse("account_email_verification_sent"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)

        # confirming is a click on the emailed page, not the link itself
        response = self.client.get(confirm_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, self.admin.email)
        self.assertFalse(EmailAddress.objects.get(user=self.admin).verified)

        response = self.client.post(confirm_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(302, response.status_code)
        self.assertTrue(EmailAddress.objects.get(user=self.admin).verified)

        # after which logging in works
        response = self.client.post(login_url, credentials, SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, settings.LOGIN_REDIRECT_URL)
        self.assertEqual(self.admin, response.wsgi_request.user)

    def test_login_redirects_within_site_hosts(self):
        login_url = reverse("account_login")
        credentials = {"login": "editor@nyaruka.com", "password": "Qwerty123"}

        # each org site lives on its own subdomain so redirects back to them must be honored
        response = self.client.post(
            login_url, {**credentials, "next": "https://uganda.ureport.io/manage/org/home/"}, SERVER_NAME="ureport.io"
        )
        self.assertEqual(302, response.status_code)
        self.assertEqual("https://uganda.ureport.io/manage/org/home/", response["Location"])

        # but not to anywhere else
        for unsafe in (
            "https://evil.example.com/",
            "//evil.example.com/",
            "///evil.example.com/",
            "\\\\\\evil.example.com/",
            "/\\/evil.example.com/",
            "https://ureport.io.example.com/",
            "javascript:alert(1)",
        ):
            self.client.logout()
            response = self.client.post(login_url, {**credentials, "next": unsafe}, SERVER_NAME="ureport.io")
            self.assertEqual(302, response.status_code)
            self.assertNotIn("example.com", response["Location"], unsafe)
            self.assertNotIn("javascript", response["Location"], unsafe)

        # relative paths are fine
        self.client.logout()
        response = self.client.post(login_url, {**credentials, "next": "/manage/org/home/"}, SERVER_NAME="ureport.io")
        self.assertRedirect(response, "/manage/org/home/")

    def test_logout(self):
        self.login(self.editor)

        response = self.client.post(reverse("account_logout") + "?next=/", SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, "/")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_legacy_urls(self):
        response = self.client.get("/users/login/?next=/manage/", SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, "/accounts/login/")
        self.assertEqual("/accounts/login/?next=/manage/", response["Location"])

        response = self.client.get("/users/logout/", SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, "/accounts/logout/")

    def test_account_pages_render(self):
        self.login(self.editor)

        for url_name in (
            "account_email",
            "account_change_password",
            "account_logout",
            "account_reauthenticate",
            "account_reset_password",
            "account_reset_password_done",
            "account_inactive",
        ):
            response = self.client.get(reverse(url_name), SERVER_NAME="nigeria.ureport.io")
            self.assertEqual(200, response.status_code, url_name)

        response = self.client.get(reverse("account_email"), SERVER_NAME="nigeria.ureport.io")
        self.assertContains(response, "editor@nyaruka.com")

    def test_signup_closed(self):
        response = self.client.get(reverse("account_signup"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Sign Up Closed")

    def test_password_reset(self):
        reset_url = reverse("account_reset_password")

        response = self.client.get(reset_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)

        response = self.client.post(reset_url, {"email": "editor@nyaruka.com"}, SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, reverse("account_reset_password_done"))

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(["editor@nyaruka.com"], mail.outbox[0].to)
        self.assertEqual("[U-Report] Password Reset Email", mail.outbox[0].subject)
        self.assertIn("https://nigeria.ureport.io/accounts/password/reset/key/", mail.outbox[0].body)
        self.assertNotIn("example.com", mail.outbox[0].body)

    def test_protected_pages_redirect_to_login(self):
        response = self.client.get(reverse("orgs.org_home"), SERVER_NAME="nigeria.ureport.io")
        self.assertLoginRedirect(response)

    def test_account_pages_need_no_org(self):
        # the root host has no org, so the org middleware must let every allauth page through
        def url_names(patterns):
            for pattern in patterns:
                if isinstance(pattern, URLResolver):
                    yield from url_names(pattern.url_patterns)
                elif isinstance(pattern, URLPattern) and pattern.name:
                    yield pattern.name

        from allauth.urls import urlpatterns

        allowed = set(ALLOW_NO_ORG) | set(settings.SITE_ALLOW_NO_ORG)
        missing = sorted(set(url_names(urlpatterns)) - allowed)
        self.assertEqual([], missing)

        response = self.client.get(reverse("account_login"), SERVER_NAME="ureport.io")
        self.assertEqual(200, response.status_code)


class UserCRUDLTest(UreportTest):
    def test_profile(self):
        profile_url = reverse("users.user_profile", args=[self.admin.pk])

        response = self.client.get(profile_url, SERVER_NAME="nigeria.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(profile_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertIn("first_name", response.context["form"].fields)
        self.assertNotIn("email", response.context["form"].fields)
        self.assertNotIn("new_password", response.context["form"].fields)
        self.assertContains(response, reverse("account_change_password"))
        self.assertContains(response, reverse("account_email"))

        response = self.client.post(
            profile_url, {"first_name": "Ad", "last_name": "Min"}, SERVER_NAME="nigeria.ureport.io"
        )
        self.assertEqual(302, response.status_code)

        self.admin.refresh_from_db()
        self.assertEqual("Ad", self.admin.first_name)
        self.assertEqual("Min", self.admin.last_name)

    def test_removed_actions(self):
        self.login(self.superuser)

        for path in (
            "/users/user/forget/",
            "/users/user/failed/",
            "/users/user/expired/",
            "/users/user/newpassword/0/",
            "/users/user/mimic/1/",
        ):
            response = self.client.get(path, SERVER_NAME="nigeria.ureport.io")
            self.assertEqual(404, response.status_code, path)


class EmailAddressSyncTest(UreportTest):
    def test_sync_on_save(self):
        # emails are lowercased, as allauth expects
        user = User.objects.create_user("jim", " Jim@Nyaruka.com ", "Qwerty123")
        self.assertEqual("jim@nyaruka.com", user.email)

        # nothing is verified until the user confirms it themselves
        self.assertEqual(0, user.emailaddress_set.count())
        verify_email(user)

        # changing the email drops the old address so it can no longer be used to log in
        user.email = "jim.bob@nyaruka.com"
        user.save()
        self.assertEqual(0, user.emailaddress_set.count())
        verify_email(user)

        # as does clearing it
        user.email = ""
        user.save()
        self.assertEqual(0, user.emailaddress_set.count())
