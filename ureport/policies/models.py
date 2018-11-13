from gettext import gettext as _

import markdown
from smartmin.models import SmartModel

from django.db import models
from django.utils.safestring import mark_safe
from django.conf import settings


class Policy(SmartModel):
    TYPE_PRIVACY = "privacy"
    TYPE_TOS = "tos"
    TYPE_COOKIE = "cookie"

    TYPE_CHOICES = (
        (TYPE_PRIVACY, _("Privacy Policy")),
        (TYPE_TOS, _("Terms of Service")),
        (TYPE_COOKIE, _("Cookie Policy")),
    )

    language = models.CharField(choices=settings.LANGUAGES, max_length=16, help_text=_("Choose the language"))

    policy_type = models.CharField(choices=TYPE_CHOICES, max_length=16, help_text=_("Choose the type of policy"))

    body = models.TextField(help_text=_("Enter the content of the policy (Markdown permitted)"))

    def get_rendered_body(self):
        return mark_safe(markdown.markdown(self.body))

    def get_policy_language(self):
        return [lang[1] for lang in settings.LANGUAGES if lang[0] == self.language][0]

    class Meta:
        verbose_name_plural = _("Policies")
