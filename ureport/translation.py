# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.utils.translation import get_language as _get_language, ugettext as _

from modeltranslation import utils
from modeltranslation.translator import TranslationOptions, translator
from nsms.text.models import Text


class TextTranslationOptions(TranslationOptions):
    fields = ("text",)


translator.register(Text, TextTranslationOptions)


# need to translate something for django translations to kick in
_("Something to trigger localizations")


# monkey patch a version of get_language that isn't broken
def get_language():
    lang = _get_language()
    return lang


utils.get_language = get_language
