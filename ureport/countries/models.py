# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import regex
import six
from django_countries.fields import CountryField
from smartmin.models import SmartModel

from django.db import models
from django.utils.translation import gettext_lazy as _


class CountryAlias(SmartModel):
    country = CountryField()
    name = models.CharField(max_length=128, help_text=_("The name for our alias"))

    @classmethod
    def normalize_name(cls, name):
        words = regex.split(r"\W+", six.text_type(name).lower(), flags=regex.UNICODE | regex.V0)
        return " ".join([word.lower() for word in words if word])

    @classmethod
    def get_or_create(cls, country, name, user):
        name = CountryAlias.normalize_name(name)
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
