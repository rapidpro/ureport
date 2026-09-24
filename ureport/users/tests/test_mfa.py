from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    SECRET_SESSION_KEY,
    format_hotp_value,
    hotp_value,
    yield_hotp_counters_from_time,
)

from django.conf import settings
from django.core import mail
from django.urls import reverse

from ureport.tests import UreportTest

from .test_account import verify_email


class MFATest(UreportTest):
    def setUp(self):
        super().setUp()

        self.editor = self.create_user("editor")
        self.editor.set_password("Qwerty123")
        self.editor.save()
        verify_email(self.editor)

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
        self.assertEqual(403, response.status_code)
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
