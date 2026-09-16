from django import forms
from django.contrib.auth import get_user_model
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

    actions = ("create", "list", "update", "profile")

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
