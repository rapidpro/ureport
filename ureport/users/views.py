from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.mfa.models import Authenticator

from django import forms
from django.conf import settings
from django.contrib import auth, messages
from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from smartmin.users.views import UserCRUDL as SmartUserCRUDL
from smartmin.views import SmartUpdateView


class ProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name")


class UserCRUDL(SmartUserCRUDL):
    """
    Staff-side user management. Login, logout, password changes and password recovery are handled by allauth.
    """

    actions = ("create", "list", "update", "profile", "mimic", "disable_mfa")

    class List(SmartUserCRUDL.List):
        fields = ("username", "name", "group", "mfa", "last_login")
        field_config = {"mfa": dict(label=_("2FA"))}

        def get_queryset(self, **kwargs):
            return (
                super()
                .get_queryset(**kwargs)
                .prefetch_related(Prefetch("authenticator_set", queryset=Authenticator.objects.all()))
            )

        def get_mfa(self, obj):
            return "✓" if obj.authenticator_set.all() else ""

    class Profile(SmartUserCRUDL.Profile):
        form_class = ProfileForm
        fields = ("username", "email", "first_name", "last_name")
        field_config = {
            "username": dict(readonly=True, label=_("Username")),
            "email": dict(readonly=True, label=_("Email")),
        }
        template_name = "smartmin/users/user_profile.html"

        def has_permission(self, request, *args, **kwargs):
            return self.request.user.is_authenticated

    class Mimic(SmartUserCRUDL.Mimic):
        def pre_process(self, request, *args, **kwargs):
            user = self.get_object()

            auth.login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])

            return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)

    class DisableMfa(SmartUpdateView):
        """
        Removes a user's authenticators so they can log in with just their password again, e.g. after losing their
        phone and recovery codes.
        """

        fields = ("id",)

        def derive_queryset(self, **kwargs):
            # like mimicking, not something staff should be able to do to each other
            return super().derive_queryset(**kwargs).exclude(is_staff=True).exclude(is_superuser=True)

        def pre_process(self, request, *args, **kwargs):
            user = self.get_object()

            if request.method == "POST":
                user.authenticator_set.all().delete()
                get_account_adapter(request).send_notification_mail("mfa/email/totp_deactivated", user)
                messages.success(request, _("Two-factor authentication disabled for %s.") % user.username)

            return HttpResponseRedirect(reverse("users.user_update", args=[user.id]))
