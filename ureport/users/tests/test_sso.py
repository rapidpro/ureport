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
        "APP": {"client_id": "test-client", "secret": "test-secret", "key": ""},
    },
    "openid_connect": {
        "APPS": [
            {
                "provider_id": "oidc",
                "name": "Acme",
                "client_id": "test-client",
                "secret": "test-secret",
                "settings": {
                    "server_url": "https://login.example.com",
                    "verified_email": ["trusted.example.com"],
                    "identity_claim": "preferred_username",
                    "identity_claim_domains": ["nyaruka.com"],
                },
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

    def test_google_login_unverified_local_address(self):
        # an account whose address we don't hold as verified (e.g. it was shared with another account when we
        # migrated) can't be entered by SSO, which would otherwise wipe its password
        self.editor.emailaddress_set.update(verified=False)

        request, response = self.social_login("google", self.google_data("editor@nyaruka.com"))
        self.assertSignupClosed(request, response)
        self.editor.refresh_from_db()
        self.assertTrue(self.editor.has_usable_password())

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

    def test_oidc_login_by_identity_claim(self):
        # no email claim at all, but the ID token identifies the user by a claim the deployment trusts for the domain
        request, response = self.social_login(
            "oidc", self.oidc_data({"name": "Bob"}, {"preferred_username": "Editor@Nyaruka.com"})
        )
        self.assertSignedIn(request, response, self.editor)
        self.assertEqual(self.editor, SocialAccount.objects.get(provider="oidc", uid="abcde").user)

        # not for a domain the claim isn't trusted for
        SocialAccount.objects.all().delete()
        self.editor.email = "editor@other.example.com"
        self.editor.save()
        verify_email(self.editor)

        request, response = self.social_login(
            "oidc", self.oidc_data({"name": "Bob"}, {"preferred_username": "editor@other.example.com"})
        )
        self.assertSignupClosed(request, response)

        # and not at all for a provider without the claim configured
        self.editor.email = "editor@nyaruka.com"
        self.editor.save()
        verify_email(self.editor)

        request, response = self.social_login(
            "google", {"sub": "12345", "name": "Bob", "preferred_username": "editor@nyaruka.com"}
        )
        self.assertSignupClosed(request, response)

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
