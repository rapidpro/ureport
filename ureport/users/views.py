from django import forms
from django.conf import settings
from django.contrib import auth
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

from smartmin.users.views import UserCRUDL as SmartUserCRUDL


class ProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name")


class UserCRUDL(SmartUserCRUDL):
    """
    Staff-side user management. Login, logout, password changes and password recovery are handled by allauth.
    """

    actions = ("create", "list", "update", "profile", "mimic")

    class Create(SmartUserCRUDL.Create):
        fields = ("username", "new_password", "first_name", "last_name", "email", "groups")

    class Update(SmartUserCRUDL.Update):
        fields = ("username", "new_password", "first_name", "last_name", "email", "is_active", "last_login", "groups")

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
