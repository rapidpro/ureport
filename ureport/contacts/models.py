from dash.orgs.models import Org
from django.db import models
from django.utils.translation import ugettext_lazy as _
from smartmin.models import SmartModel


class Contact(SmartModel):
    """
    Corresponds to a RapidPro contact
    """
    MALE = 'M'
    FEMALE = 'F'
    GENDER_CHOICES = ((MALE, _("Male")), (FEMALE, _("Female")))

    uuid = models.CharField(max_length=36, unique=True)

    org = models.ForeignKey(Org, verbose_name=_("Organization"), related_name="contacts")

    gender = models.CharField(max_length=1, verbose_name=_("Gender"), choices=GENDER_CHOICES,
                              help_text=_("Gender of the contact"))

    born = models.CharField(max_length=255, verbose_name=_("Born Field"))

    occupation = models.CharField(max_length=255, verbose_name=_("Occupation Field"))

    registered = models.CharField(max_length=255, verbose_name=_("Registration Date"))

    state = models.CharField(max_length=255, verbose_name=_("State Field"))

    district = models.CharField(max_length=255, verbose_name=_("District Field"))

