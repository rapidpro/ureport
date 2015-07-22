import re
from django.contrib.auth.models import User
from django.db import models
from django_countries import countries
from smartmin.models import SmartModel
from django_countries.fields import CountryField
from django.utils.translation import ugettext_lazy as _

class CountryAlias(SmartModel):
    country = CountryField()
    name = models.CharField(max_length=128, help_text=_("The name for our alias"))

    @classmethod
    def name_stemming(cls, name):
        words = re.split(r'\W+', name, re.UNICODE)
        return " ".join([word.lower() for word in words if word])

    @classmethod
    def get_or_create(cls, country, name, user):

        name = CountryAlias.name_stemming(name)
        alias = cls.objects.filter(country=country, name=name).first()

        if not alias:
            alias = cls.objects.create(country=country, name=name, created_by=user, modified_by=user)

        return alias

    @classmethod
    def is_valid(cls, text):
        existing_alias = cls.objects.filter(name__iexact=text, is_active=True).first()

        if not existing_alias:
            return None

        return existing_alias.country






