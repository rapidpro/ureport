# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from gettext import gettext as _

from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView, SmartReadView

from django import forms

from .models import Policy


class PoliciesForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(PoliciesForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Policy
        fields = ("is_active", "policy_type", "language", "body", "summary")


class PoliciesCRUDL(SmartCRUDL):
    model = Policy
    actions = ("create", "update", "read", "admin", "history")

    class Admin(SmartListView):
        ordering = ("-created_on",)
        link_fields = ("policy_type",)
        title = _("Policies")
        paginate_by = 500

        def get_queryset(self, **kwargs):
            queryset = super().get_queryset(**kwargs)
            return queryset.filter(is_active=False)

        def get_context_data(self, **kwargs):
            context = super().get_context_data(**kwargs)
            context["active_policies"] = Policy.objects.filter(is_active=True).order_by(*self.ordering)
            return context

    class Update(OrgObjPermsMixin, SmartUpdateView):
        form_class = PoliciesForm
        success_url = "@policies.policy_admin"
        fields = ("is_active", "body", "summary", "policy_type", "language")

        def derive_title(self):
            return _("Edit %s") % self.get_object().get_policy_type_display()

        def get_form_kwargs(self):
            kwargs = super(PoliciesCRUDL.Update, self).get_form_kwargs()
            return kwargs

    class Create(OrgPermsMixin, SmartCreateView):
        form_class = PoliciesForm
        success_url = "@policies.policy_admin"

        def get_form_kwargs(self):
            kwargs = super(PoliciesCRUDL.Create, self).get_form_kwargs()
            return kwargs

        def derive_fields(self):
            return ("body", "summary", "policy_type", "language")

        def post_save(self, obj):
            Policy.objects.filter(policy_type=obj.policy_type, language=obj.language, is_active=True).exclude(id=obj.id).update(
                is_active=False
            )
            return obj

    class History(SmartReadView):
        def derive_title(self):
            return self.get_object().get_policy_type_display()

    class Read(History):
        @classmethod
        def derive_url_pattern(cls, path, action):
            archive_types = (choice[0] for choice in Policy.TYPE_CHOICES)
            return r"^%s/(%s)/$" % (path, "|".join(archive_types))

        def derive_title(self):
            return self.get_object().get_policy_type_display()

        def get_requested_policy_type(self):
            return self.request.path.split("/")[-2]

        def get_object(self):
            policy_type = self.get_requested_policy_type()
            return Policy.objects.filter(policy_type=policy_type, is_active=True).order_by("-created_on").first()
