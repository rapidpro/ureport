from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    SECRET_SESSION_KEY,
    format_hotp_value,
    hotp_value,
    yield_hotp_counters_from_time,
)

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import URLPattern, URLResolver, reverse

from dash.orgs.middleware import ALLOW_NO_ORG
from ureport.tests import UreportTest

from .adapter import MFAAdapter

User = get_user_model()


class LoginTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.editor = self.create_user("editor")
        self.editor.email = "editor@nyaruka.com"
        self.editor.set_password("Qwerty123")
        self.editor.save()

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

        self.client.logout()
        response = self.client.post(
            reverse("account_login"),
            {"login": "Administrator@nyaruka.com", "password": "Administrator"},
            SERVER_NAME="nigeria.ureport.io",
        )
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

    def test_mimic(self):
        mimic_url = reverse("users.user_mimic", args=[self.admin.pk])

        self.login(self.superuser)

        response = self.client.post(mimic_url, {}, SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, settings.LOGIN_REDIRECT_URL)
        self.assertEqual(self.admin, response.wsgi_request.user)

    def test_removed_actions(self):
        self.login(self.superuser)

        for path in (
            "/users/user/forget/",
            "/users/user/failed/",
            "/users/user/expired/",
            "/users/user/newpassword/0/",
        ):
            response = self.client.get(path, SERVER_NAME="nigeria.ureport.io")
            self.assertEqual(404, response.status_code, path)


class EmailAddressSyncTest(UreportTest):
    def assertEmailAddresses(self, user, *emails):
        self.assertEqual(
            list(emails),
            list(user.emailaddress_set.filter(verified=True, primary=True).values_list("email", flat=True)),
        )

    def test_sync_on_save(self):
        # emails are lowercased, as allauth expects
        user = User.objects.create_user("jim", " Jim@Nyaruka.com ", "Qwerty123")
        self.assertEqual("jim@nyaruka.com", user.email)
        self.assertEmailAddresses(user, "jim@nyaruka.com")

        # changing the email replaces the address
        user.email = "jim.bob@nyaruka.com"
        user.save()
        self.assertEmailAddresses(user, "jim.bob@nyaruka.com")
        self.assertEqual(1, user.emailaddress_set.count())

        # a user without an email gets no address
        bob = User.objects.create_user("bob", "", "Qwerty123")
        self.assertEmailAddresses(bob)

        # an email already belonging to another account is left alone
        bob.email = "JIM.BOB@nyaruka.com"
        bob.save()
        self.assertEmailAddresses(bob)
        self.assertEmailAddresses(user, "jim.bob@nyaruka.com")

        # clearing an email removes the address so it can no longer be used to log in
        user.email = ""
        user.save()
        self.assertEqual(0, user.emailaddress_set.count())

        # and now bob can have it
        bob.save()
        self.assertEmailAddresses(bob, "jim.bob@nyaruka.com")

    def test_backfill_migration(self):
        from importlib import import_module

        migration = import_module("ureport.users.migrations.0001_backfill_email_addresses")

        user1 = User.objects.create_user("user1", "user1@nyaruka.com", "Qwerty123")
        user2 = User.objects.create_user("user2", "shared@nyaruka.com", "Qwerty123")
        user3 = User.objects.create_user("user3", "SHARED@nyaruka.com", "Qwerty123")
        user4 = User.objects.create_user("user4", "", "Qwerty123")
        User.objects.filter(pk=user3.pk).update(last_login="2026-01-01T00:00:00Z", email="SHARED@nyaruka.com")
        EmailAddress.objects.all().delete()

        migration.backfill_email_addresses(apps, None)

        self.assertEmailAddresses(user1, "user1@nyaruka.com")
        self.assertEmailAddresses(user2)  # lost out to user3 who logged in more recently
        self.assertEmailAddresses(user3, "shared@nyaruka.com")
        self.assertEmailAddresses(user4)

        # running again changes nothing
        count = EmailAddress.objects.count()
        migration.backfill_email_addresses(apps, None)
        self.assertEqual(count, EmailAddress.objects.count())


class MFATest(UreportTest):
    def setUp(self):
        super().setUp()

        self.editor = self.create_user("editor")
        self.editor.set_password("Qwerty123")
        self.editor.save()

    def totp_code(self, secret):
        return format_hotp_value(hotp_value(secret, next(yield_hotp_counters_from_time())))

    def password_login(self, user):
        response = self.client.post(
            reverse("account_login"), {"login": user.email, "password": "Qwerty123"}, SERVER_NAME="nigeria.ureport.io"
        )
        self.assertEqual(302, response.status_code)
        return response

    def test_activate_and_login(self):
        activate_url = reverse("mfa_activate_totp")

        self.password_login(self.editor)

        response = self.client.get(reverse("mfa_index"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "An authenticator app is not active.")
        self.assertContains(response, activate_url)

        # we just logged in so we don't need to reauthenticate to get the QR code
        response = self.client.get(activate_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "scan the QR code below")

        secret = self.client.session[SECRET_SESSION_KEY]

        response = self.client.post(activate_url, {"code": "000000"}, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(self.editor.authenticator_set.exists())

        response = self.client.post(activate_url, {"code": self.totp_code(secret)}, SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, reverse("mfa_view_recovery_codes"))
        self.assertEqual(
            {Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES},
            set(self.editor.authenticator_set.values_list("type", flat=True)),
        )

        response = self.client.get(reverse("mfa_view_recovery_codes"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Unused codes")

        response = self.client.get(reverse("mfa_index"), SERVER_NAME="nigeria.ureport.io")
        self.assertContains(response, "Authentication using an authenticator app is active.")

        # logging in with a password now needs a code as well
        self.client.logout()
        response = self.password_login(self.editor)
        self.assertRedirect(response, reverse("mfa_authenticate"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        response = self.client.get(reverse("mfa_authenticate"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)

        response = self.client.post(reverse("mfa_authenticate"), {"code": "000000"}, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        activated_secret = MFAAdapter().decrypt(
            self.editor.authenticator_set.get(type=Authenticator.Type.TOTP).data["secret"]
        )
        response = self.client.post(
            reverse("mfa_authenticate"), {"code": self.totp_code(activated_secret)}, SERVER_NAME="nigeria.ureport.io"
        )
        self.assertRedirect(response, settings.LOGIN_REDIRECT_URL)
        self.assertEqual(self.editor, response.wsgi_request.user)

    def test_reauthentication_required(self):
        # a session without a recent password login must reauthenticate before touching MFA settings
        self.login(self.editor)

        response = self.client.get(reverse("mfa_activate_totp"), SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, reverse("account_reauthenticate"))

        response = self.client.get(reverse("account_reauthenticate"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Confirm Access")

    def test_staff_disable(self):
        Authenticator.objects.create(user=self.editor, type=Authenticator.Type.TOTP, data={"secret": "sesame"})
        Authenticator.objects.create(
            user=self.editor, type=Authenticator.Type.RECOVERY_CODES, data={"migrated_codes": ["abc"]}
        )

        list_url = reverse("users.user_list")
        update_url = reverse("users.user_update", args=[self.editor.id])
        disable_url = reverse("users.user_disable_mfa", args=[self.editor.id])

        # only staff can see or do this
        self.login(self.admin)
        response = self.client.post(disable_url, {}, SERVER_NAME="nigeria.ureport.io")
        self.assertLoginRedirect(response)
        self.assertEqual(2, self.editor.authenticator_set.count())

        self.login(self.superuser)

        response = self.client.get(list_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "2FA")
        self.assertEqual("✓", response.context["view"].get_mfa(self.editor))
        self.assertEqual("", response.context["view"].get_mfa(self.admin))

        response = self.client.get(update_url, SERVER_NAME="nigeria.ureport.io")
        self.assertContains(response, disable_url)

        response = self.client.post(disable_url, {}, SERVER_NAME="nigeria.ureport.io")
        self.assertRedirect(response, update_url)
        self.assertEqual(0, self.editor.authenticator_set.count())

        response = self.client.get(update_url, SERVER_NAME="nigeria.ureport.io")
        self.assertNotContains(response, disable_url)
