from allauth.core import context
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialAccount

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.test import RequestFactory, override_settings
from django.urls import reverse

from ureport.tests import UreportTest

from .test_account import verify_email

User = get_user_model()


SSO_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "EMAIL_AUTHENTICATION": True,
        "APP": {"client_id": "test-client", "secret": "test-secret", "key": ""},
    },
    "openid_connect": {
        "EMAIL_AUTHENTICATION": True,
        "APPS": [
            {
                "provider_id": "oidc",
                "name": "Acme",
                "client_id": "test-client",
                "secret": "test-secret",
                "settings": {"server_url": "https://login.example.com", "verified_email": ["trusted.example.com"]},
            }
        ],
    },
}


@override_settings(SOCIALACCOUNT_PROVIDERS=SSO_PROVIDERS)
class SSOTest(UreportTest):
    def setUp(self):
        super().setUp()

        self.editor = self.create_user("editor")
        self.editor.set_password("Qwerty123")
        self.editor.save()
        verify_email(self.editor)

    def test_login_buttons(self):
        login_url = reverse("account_login")

        # provider buttons start the login on the root host and come back to the host the user is on
        response = self.client.get(login_url, SERVER_NAME="nigeria.ureport.io")
        self.assertContains(response, "Sign In with Google")
        self.assertContains(response, "Sign In with Acme")
        self.assertContains(
            response,
            'href="https://ureport.io/accounts/google/login/?process=login&amp;next=https%3A%2F%2Fnigeria.ureport.io%2Fmanage%2Forg%2Fchoose%2F"',
        )
        self.assertContains(
            response,
            'href="https://ureport.io/accounts/oidc/oidc/login/?process=login&amp;next=https%3A%2F%2Fnigeria.ureport.io%2Fmanage%2Forg%2Fchoose%2F"',
        )

        response = self.client.get(login_url + "?next=/manage/org/home/", SERVER_NAME="nigeria.ureport.io")
        self.assertContains(
            response,
            'href="https://ureport.io/accounts/google/login/?process=login&amp;next=https%3A%2F%2Fnigeria.ureport.io%2Fmanage%2Forg%2Fhome%2F"',
        )

        # clicking one goes straight to the provider, with the callback on the root host
        response = self.client.get(
            "/accounts/google/login/?process=login&next=https%3A%2F%2Fnigeria.ureport.io%2Fmanage%2Forg%2Fhome%2F",
            SERVER_NAME="ureport.io",
        )
        self.assertEqual(302, response.status_code)
        self.assertIn(
            "redirect_uri=https%3A%2F%2Fureport.io%2Faccounts%2Fgoogle%2Flogin%2Fcallback%2F", response["Location"]
        )
        self.assertEqual(
            "https://nigeria.ureport.io/manage/org/home/",
            self.client.session["socialaccount_states"].popitem()[1][0]["next"],
        )

        # a return URL off the site is dropped before it reaches the provider state
        self.client.session.flush()
        response = self.client.get(
            "/accounts/google/login/?process=login&next=https%3A%2F%2Fevil.example.com%2F", SERVER_NAME="ureport.io"
        )
        self.assertEqual(302, response.status_code)
        self.assertNotIn("next", self.client.session["socialaccount_states"].popitem()[1][0])

        # no buttons when no provider is configured
        with override_settings(SOCIALACCOUNT_PROVIDERS={}):
            response = self.client.get(login_url, SERVER_NAME="nigeria.ureport.io")
            self.assertNotContains(response, "Sign In with")

    def social_login(self, provider_id, data, process="login", user=None):
        """
        Simulates the provider having authenticated a user, i.e. what happens after the callback, using the data
        shape allauth builds for that provider.
        """
        request = RequestFactory().get("/accounts/", SERVER_NAME="ureport.io")
        request.user = user or AnonymousUser()
        request.org = None  # the root host has no org
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)

        with context.request_context(request):
            provider = get_social_adapter().get_provider(request, provider_id)
            sociallogin = provider.sociallogin_from_response(request, data)
            sociallogin.state = {"next": "https://nigeria.ureport.io/manage/org/home/", "process": process}
            response = complete_social_login(request, sociallogin)

        return request, response

    def google_data(self, email, verified=True):
        return {"sub": "12345", "email": email, "email_verified": verified, "name": "Bob Marley"}

    def oidc_data(self, userinfo, id_token):
        return {"userinfo": {"sub": "abcde", **userinfo}, "id_token": {"sub": "abcde", **id_token}}

    def assertSignedIn(self, request, response, user):
        self.assertEqual(302, response.status_code)
        self.assertEqual("https://nigeria.ureport.io/manage/org/home/", response["Location"])
        self.assertEqual(user, request.user)

    def assertSignupClosed(self, request, response):
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Sign Up Closed")
        self.assertFalse(request.user.is_authenticated)
        self.assertFalse(SocialAccount.objects.exists())

    def test_google_login(self):
        request, response = self.social_login("google", self.google_data("Editor@nyaruka.com"))
        self.assertSignedIn(request, response, self.editor)

        # the social account is now connected to the existing user and they still have their password
        self.assertEqual(self.editor, SocialAccount.objects.get(provider="google", uid="12345").user)
        self.editor.refresh_from_db()
        self.assertTrue(self.editor.has_usable_password())
        self.assertEqual(["editor@nyaruka.com"], mail.outbox[-1].to)
        self.assertIn("Third-Party Account Connected", mail.outbox[-1].subject)

        # and next time is recognized by the social account alone
        request, response = self.social_login("google", self.google_data("editor@nyaruka.com"))
        self.assertSignedIn(request, response, self.editor)

    def test_google_login_unverified_email(self):
        # an email claim the provider hasn't verified doesn't identify the user
        request, response = self.social_login("google", self.google_data("editor@nyaruka.com", verified=False))
        self.assertSignupClosed(request, response)

    def test_google_login_unknown_user(self):
        request, response = self.social_login("google", self.google_data("stranger@nyaruka.com"))
        self.assertSignupClosed(request, response)
        self.assertFalse(User.objects.filter(email="stranger@nyaruka.com").exists())

    def test_google_login_inactive_user(self):
        self.editor.is_active = False
        self.editor.save()

        request, response = self.social_login("google", self.google_data("editor@nyaruka.com"))
        self.assertSignupClosed(request, response)
        self.assertEqual(0, len(mail.outbox))

    def test_google_login_verifies_local_address(self):
        # a trusted provider vouching for the address is as good as the user confirming it, so an account that never
        # did (e.g. one created by staff that has only ever used single sign-on) gets in and keeps its password
        self.editor.emailaddress_set.all().delete()

        request, response = self.social_login("google", self.google_data("editor@nyaruka.com"))
        self.assertSignedIn(request, response, self.editor)
        self.assertEqual(
            ["editor@nyaruka.com"], [a.email for a in self.editor.emailaddress_set.filter(verified=True, primary=True)]
        )
        self.editor.refresh_from_db()
        self.assertTrue(self.editor.has_usable_password())

    def test_untrusted_provider(self):
        # a provider that isn't trusted to identify users by email can't log anyone in, however verified the email
        providers = {"google": {**SSO_PROVIDERS["google"], "EMAIL_AUTHENTICATION": False}}
        with override_settings(SOCIALACCOUNT_PROVIDERS=providers):
            with self.assertLogs("ureport.users.adapter", level="WARNING") as logs:
                request, response = self.social_login("google", self.google_data("editor@nyaruka.com"))
        self.assertSignupClosed(request, response)
        self.assertIn("fell through to closed signup: provider=google email='editor@nyaruka.com'", logs.output[0])

    def test_oidc_login_by_verified_email(self):
        request, response = self.social_login(
            "oidc", self.oidc_data({"email": "editor@nyaruka.com", "email_verified": True}, {})
        )
        self.assertSignedIn(request, response, self.editor)
        self.assertEqual(self.editor, SocialAccount.objects.get(provider="oidc", uid="abcde").user)

    def test_oidc_login_by_trusted_domain(self):
        # the provider doesn't say the email is verified but it's in a domain the deployment trusts it for
        self.editor.email = "editor@trusted.example.com"
        self.editor.save()
        verify_email(self.editor)

        request, response = self.social_login("oidc", self.oidc_data({"email": "editor@trusted.example.com"}, {}))
        self.assertSignedIn(request, response, self.editor)

        # but not for a domain it isn't trusted for
        SocialAccount.objects.all().delete()
        self.editor.email = "editor@nyaruka.com"
        self.editor.save()
        verify_email(self.editor)

        request, response = self.social_login("oidc", self.oidc_data({"email": "editor@nyaruka.com"}, {}))
        self.assertSignupClosed(request, response)

    def test_oidc_login_by_principal_name(self):
        # no email claim at all, but the ID token identifies the user by a principal name in a trusted domain
        self.editor.email = "editor@trusted.example.com"
        self.editor.save()
        verify_email(self.editor)

        request, response = self.social_login(
            "oidc", self.oidc_data({"name": "Bob"}, {"preferred_username": "Editor@Trusted.example.com"})
        )
        self.assertSignedIn(request, response, self.editor)
        self.assertEqual(self.editor, SocialAccount.objects.get(provider="oidc", uid="abcde").user)

        # not for a domain the provider isn't trusted for
        SocialAccount.objects.all().delete()
        self.editor.email = "editor@nyaruka.com"
        self.editor.save()
        verify_email(self.editor)

        request, response = self.social_login(
            "oidc", self.oidc_data({"name": "Bob"}, {"preferred_username": "editor@nyaruka.com"})
        )
        self.assertSignupClosed(request, response)

        # and not at all for a provider without trusted domains, or a principal name that isn't an email
        request, response = self.social_login(
            "google", {"sub": "12345", "name": "Bob", "preferred_username": "editor@nyaruka.com"}
        )
        self.assertSignupClosed(request, response)

        request, response = self.social_login("oidc", self.oidc_data({"name": "Bob"}, {"upn": "editor"}))
        self.assertSignupClosed(request, response)

    def test_sso_only_domains(self):
        login_url = reverse("account_login")
        credentials = {"login": self.editor.email, "password": "Qwerty123"}

        with override_settings(SSO_ONLY_DOMAINS={"Nyaruka.com": "Use Sign In with Acme instead."}):
            # a user whose email domain requires single sign-on is sent back to the login page with the error
            response = self.client.post(login_url, credentials, SERVER_NAME="nigeria.ureport.io")
            self.assertRedirect(response, login_url)
            self.assertFalse(response.wsgi_request.user.is_authenticated)

            response = self.client.get(login_url, SERVER_NAME="nigeria.ureport.io")
            self.assertContains(response, "Use Sign In with Acme instead.")

            # and keeps where they were going
            response = self.client.post(
                f"{login_url}?next=/manage/org/home/", credentials, SERVER_NAME="nigeria.ureport.io"
            )
            self.assertEqual(f"{login_url}?next=%2Fmanage%2Forg%2Fhome%2F", response["Location"])

            # whereas single sign-on for the same user is allowed through
            request, response = self.social_login("google", self.google_data("editor@nyaruka.com"))
            self.assertSignedIn(request, response, self.editor)

            # and other domains aren't affected
            verify_email(self.admin)
            response = self.client.post(
                login_url,
                {"login": "administrator@nyaruka.com", "password": "Administrator"},
                SERVER_NAME="nigeria.ureport.io",
            )
            self.assertRedirect(response, login_url)  # still nyaruka.com, so still blocked
            self.client.logout()

        with override_settings(SSO_ONLY_DOMAINS={"other.example.com": "Nope."}):
            response = self.client.post(login_url, credentials, SERVER_NAME="nigeria.ureport.io")
            self.assertEqual(self.editor, response.wsgi_request.user)

    def test_authentication_error_is_logged(self):
        request = RequestFactory().get("/accounts/google/login/callback/?error=access_denied", SERVER_NAME="ureport.io")
        request.user = AnonymousUser()
        request.org = None
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)

        with context.request_context(request):
            provider = get_social_adapter().get_provider(request, "google")
            with self.assertLogs("ureport.users.adapter", level="WARNING") as logs:
                get_social_adapter().on_authentication_error(request, provider, error="cancelled")

        self.assertIn("social login failed: provider=google error=cancelled", logs.output[0])
        self.assertIn("idp_error='access_denied'", logs.output[0])

    def test_connect(self):
        self.login(self.editor)

        # the connections page offers to connect rather than sign in
        response = self.client.get(reverse("socialaccount_connections"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Connect Google")
        self.assertContains(response, 'href="https://ureport.io/accounts/google/login/?process=connect&amp;')

        # connecting a provider identity that isn't linked to any account links it to the logged in user
        request, response = self.social_login(
            "google", self.google_data("bob@gmail.example.com"), process="connect", user=self.editor
        )
        self.assertEqual(302, response.status_code)
        self.assertEqual(self.editor, request.user)
        self.assertEqual(self.editor, SocialAccount.objects.get(provider="google", uid="12345").user)

        response = self.client.get(reverse("socialaccount_connections"), SERVER_NAME="nigeria.ureport.io")
        self.assertContains(response, "bob@gmail.example.com")
