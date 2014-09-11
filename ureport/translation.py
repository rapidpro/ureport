from modeltranslation.translator import translator, TranslationOptions

from nsms.text.models import *
from django.utils.translation import ugettext as _
from django.utils.translation import get_language as _get_language
from modeltranslation import utils

class TextTranslationOptions(TranslationOptions):
    fields = ('text',)

translator.register(Text, TextTranslationOptions)

# need to translate something for django translations to kick in
_("Something to trigger localizations")

# monkey patch a version of get_language that isn't broken
def get_language():
    lang = _get_language()
    return lang

utils.get_language = get_language

