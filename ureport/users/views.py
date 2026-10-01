from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from django.http import HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from smartmin.users.views import (
    UserCRUDL as SmartUserCRUDL,
    UserForm as SmartUserForm,
    UserUpdateForm as SmartUserUpdateForm,
)
from smartmin.views import SmartUpdateView


class UniqueEmailMixin:
    """
    Users are identified by their email so it has to be unique, which Django's user model doesn't enforce itself
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        others = get_user_model().objects.filter(email=email)
        if self.instance.pk:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError(_("A user with this email already exists."))

        return email


class UserForm(UniqueEmailMixin, SmartUserForm):
    pass


class UserUpdateForm(UniqueEmailMixin, SmartUserUpdateForm):
    pass


class ProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name")


class UserCRUDL(SmartUserCRUDL):
    """
    Staff-side user management. Login, logout, password changes and password recovery are handled by allauth. Users
    are identified by their email everywhere, and their username is kept equal to it.
    """

    actions = ("create", "list", "update", "profile", "disable_mfa")

    class List(SmartUserCRUDL.List):
        search_fields = ("email__icontains", "first_name__icontains", "last_name__icontains")
        fields = ("email", "name", "group", "verified", "mfa", "last_login")
        link_fields = ("email", "name")
        default_order = "email"
        field_config = {"mfa": dict(label=_("2FA"))}

        def get_queryset(self, **kwargs):
            return (
                super()
                .get_queryset(**kwargs)
                .prefetch_related(
                    Prefetch("authenticator_set", queryset=Authenticator.objects.all()),
                    Prefetch("emailaddress_set", queryset=EmailAddress.objects.filter(verified=True)),
                )
            )

        def get_verified(self, obj):
            verified = any(a.email == obj.email for a in obj.emailaddress_set.all())
            return render_to_string("users/verified_tag.html", {"verified": verified})

        def get_mfa(self, obj):
            return render_to_string("users/mfa_tag.html", {"mfa": bool(obj.authenticator_set.all())})

    class Create(SmartUserCRUDL.Create):
        form_class = UserForm
        fields = ("email", "new_password", "first_name", "last_name", "groups")

        def pre_save(self, obj):
            obj.username = obj.email
            return super().pre_save(obj)

    class Update(SmartUserCRUDL.Update):
        form_class = UserUpdateForm
        fields = ("email", "new_password", "first_name", "last_name", "is_active", "last_login", "groups")

        def pre_save(self, obj):
            obj.username = obj.email
            return super().pre_save(obj)

    class Profile(SmartUserCRUDL.Profile):
        form_class = ProfileForm
        fields = ("email", "first_name", "last_name")
        field_config = {"email": dict(readonly=True, label=_("Email"))}
        template_name = "smartmin/users/user_profile.html"

        def has_permission(self, request, *args, **kwargs):
            return self.request.user.is_authenticated

    class DisableMfa(SmartUpdateView):
        """
        Removes a user's authenticators so they can log in with just their password again, e.g. after losing their
        phone and recovery codes.
        """

        fields = ("id",)

        def derive_queryset(self, **kwargs):
            # not something staff should be able to do to each other
            return super().derive_queryset(**kwargs).exclude(is_staff=True).exclude(is_superuser=True)

        def pre_process(self, request, *args, **kwargs):
            user = self.get_object()

            if request.method == "POST":
                user.authenticator_set.all().delete()
                get_account_adapter(request).send_notification_mail("mfa/email/totp_deactivated", user)
                messages.success(request, _("Two-factor authentication disabled for %s.") % user.email)

            return HttpResponseRedirect(reverse("users.user_update", args=[user.id]))
