from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    SECRET_SESSION_KEY,
    format_hotp_value,
    hotp_value,
    yield_hotp_counters_from_time,
)
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialAccount, SocialLogin

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.test import RequestFactory, override_settings
from django.urls import URLPattern, URLResolver, reverse

from dash.orgs.middleware import ALLOW_NO_ORG
from ureport.tests import UreportTest

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

        # allauth sends the notification email once the activation commits
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                activate_url, {"code": self.totp_code(secret)}, SERVER_NAME="nigeria.ureport.io"
            )
        self.assertRedirect(response, reverse("mfa_view_recovery_codes"))
        self.assertEqual(["editor@nyaruka.com"], mail.outbox[-1].to)
        self.assertIn("Authenticator app activated", mail.outbox[-1].body)
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

        activated_secret = get_mfa_adapter().decrypt(
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

        # and the user is told
        self.assertEqual(["editor@nyaruka.com"], mail.outbox[-1].to)
        self.assertIn("Authenticator app deactivated", mail.outbox[-1].body)

        response = self.client.get(update_url, SERVER_NAME="nigeria.ureport.io")
        self.assertNotContains(response, disable_url)

        # staff can't do this to each other
        Authenticator.objects.create(user=self.superuser, type=Authenticator.Type.TOTP, data={"secret": "sesame"})
        response = self.client.post(
            reverse("users.user_disable_mfa", args=[self.superuser.id]), {}, SERVER_NAME="nigeria.ureport.io"
        )
        self.assertEqual(404, response.status_code)
        self.assertEqual(1, self.superuser.authenticator_set.count())


GOOGLE_PROVIDER = {
    "google": {
        "SCOPE": ["profile", "email"],
        "APP": {"client_id": "test-client", "secret": "test-secret", "key": ""},
    }
}


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_PROVIDER)
class SSOTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.editor = self.create_user("editor")
        self.editor.set_password("Qwerty123")
        self.editor.save()

    def test_login_buttons(self):
        login_url = reverse("account_login")

        # provider buttons start the login on the root host and come back to the host the user is on
        response = self.client.get(login_url, SERVER_NAME="nigeria.ureport.io")
        self.assertContains(response, "Sign In with Google")
        self.assertContains(
            response,
            'href="http://ureport.io/accounts/google/login/?process=login&amp;next=http%3A%2F%2Fnigeria.ureport.io%2Fmanage%2Forg%2Fchoose%2F"',
        )

        response = self.client.get(login_url + "?next=/manage/org/home/", SERVER_NAME="nigeria.ureport.io")
        self.assertContains(
            response,
            'href="http://ureport.io/accounts/google/login/?process=login&amp;next=http%3A%2F%2Fnigeria.ureport.io%2Fmanage%2Forg%2Fhome%2F"',
        )

        # clicking one goes straight to the provider
        response = self.client.get(
            "/accounts/google/login/?process=login&next=http%3A%2F%2Fnigeria.ureport.io%2Fmanage%2Forg%2Fhome%2F",
            SERVER_NAME="ureport.io",
        )
        self.assertEqual(302, response.status_code)
        self.assertTrue(response["Location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        # the callback is always on the root host, over https as ACCOUNT_DEFAULT_HTTP_PROTOCOL dictates
        self.assertIn(
            "redirect_uri=https%3A%2F%2Fureport.io%2Faccounts%2Fgoogle%2Flogin%2Fcallback%2F", response["Location"]
        )

        # no buttons when no provider is configured
        with override_settings(SOCIALACCOUNT_PROVIDERS={}):
            response = self.client.get(login_url, SERVER_NAME="nigeria.ureport.io")
            self.assertNotContains(response, "Sign In with")

    def social_login(self, extra_data, email_addresses=(), next_url="http://nigeria.ureport.io/manage/org/home/"):
        """
        Simulates the provider having authenticated a user, i.e. what happens after the callback
        """
        request = RequestFactory().get(reverse("google_callback"), SERVER_NAME="ureport.io")
        request.user = AnonymousUser()
        request.org = None  # the root host has no org
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)

        with context.request_context(request):
            provider = get_social_adapter().get_provider(request, "google")
            sociallogin = SocialLogin(
                user=User(email=extra_data.get("email", ""), first_name="Bob", last_name="Marley"),
                account=SocialAccount(provider="google", uid="12345", extra_data=extra_data),
                email_addresses=[EmailAddress(email=e, verified=True, primary=True) for e in email_addresses],
                provider=provider,
            )
            sociallogin.state = {"next": next_url, "process": "login"}
            response = complete_social_login(request, sociallogin)

        return request, response

    def test_social_login_existing_user(self):
        request, response = self.social_login(
            {"email": "editor@nyaruka.com", "verified_email": True}, email_addresses=["editor@nyaruka.com"]
        )
        self.assertEqual(302, response.status_code)
        self.assertEqual("http://nigeria.ureport.io/manage/org/home/", response["Location"])
        self.assertEqual(self.editor, request.user)

        # the social account is now connected to the existing user
        self.assertEqual(self.editor, SocialAccount.objects.get(provider="google", uid="12345").user)

    def test_social_login_by_upn(self):
        # some providers don't include an email claim but do identify the user by their principal name
        request, response = self.social_login({"upn": "Editor@nyaruka.com"})
        self.assertEqual(302, response.status_code)
        self.assertEqual(self.editor, request.user)
        self.assertEqual(self.editor, SocialAccount.objects.get(provider="google", uid="12345").user)

    def test_social_login_unknown_user(self):
        request, response = self.social_login(
            {"email": "stranger@nyaruka.com", "verified_email": True}, email_addresses=["stranger@nyaruka.com"]
        )
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Sign Up Closed")
        self.assertFalse(request.user.is_authenticated)
        self.assertFalse(User.objects.filter(email="stranger@nyaruka.com").exists())
        self.assertFalse(SocialAccount.objects.exists())

    def test_social_login_unverified_email(self):
        # an email claim the provider hasn't verified doesn't identify the user
        request = RequestFactory().get(reverse("google_callback"), SERVER_NAME="ureport.io")
        request.user = AnonymousUser()
        request.org = None
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)

        with context.request_context(request):
            provider = get_social_adapter().get_provider(request, "google")
            sociallogin = SocialLogin(
                user=User(email="editor@nyaruka.com"),
                account=SocialAccount(provider="google", uid="12345", extra_data={"email": "editor@nyaruka.com"}),
                email_addresses=[EmailAddress(email="editor@nyaruka.com", verified=False, primary=True)],
                provider=provider,
            )
            sociallogin.state = {"process": "login"}
            response = complete_social_login(request, sociallogin)

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Sign Up Closed")
        self.assertFalse(request.user.is_authenticated)
        self.assertFalse(SocialAccount.objects.exists())

    def test_social_login_inactive_user(self):
        self.editor.is_active = False
        self.editor.save()

        request, response = self.social_login({"upn": "editor@nyaruka.com"})
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Sign Up Closed")
        self.assertFalse(request.user.is_authenticated)

    def test_connections_page(self):
        self.login(self.editor)

        response = self.client.get(reverse("socialaccount_connections"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Account Connections")
