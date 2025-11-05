# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
from datetime import timedelta

import sentry_sdk
from celery.schedules import crontab
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger

from django.forms import Textarea
from django.utils.translation import gettext_lazy as _

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

if SENTRY_DSN:  # pragma: no cover
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration(), LoggingIntegration()],
        send_default_pii=True,
        traces_sample_rate=0.0,
    )
    ignore_logger("django.security.DisallowedHost")


# -----------------------------------------------------------------------------------
# Sets TESTING to True if this configuration is read during a unit test
# -----------------------------------------------------------------------------------
TESTING = sys.argv[1:2] == ["test"]

DEBUG = True
THUMBNAIL_DEBUG = DEBUG

ADMINS = (("Nyaruka", "code@nyaruka.com"),)

MANAGERS = ADMINS

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",  # Add 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        "NAME": "dash.sqlite",  # Or path to database file if using sqlite3.
        "USER": "",  # Not used with sqlite3.
        "PASSWORD": "",  # Not used with sqlite3.
        "HOST": "",  # Set to empty string for localhost. Not used with sqlite3.
        "PORT": "",  # Set to empty string for default. Not used with sqlite3.
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# set the mail settings, we send throught gmail
EMAIL_HOST = "smtp.gmail.com"
EMAIL_HOST_USER = "server@nyaruka.com"
DEFAULT_FROM_EMAIL = "server@nyaruka.com"
EMAIL_HOST_PASSWORD = "NOTREAL"
EMAIL_USE_TLS = True

EMPTY_SUBDOMAIN_HOST = "http://localhost:8000"
SITE_API_HOST = "http://localhost:8001"
SITE_API_USER_AGENT = "ureport/0.1"
HOSTNAME = "localhost:8000"
SITE_CHOOSER_TEMPLATE = "public/index.html"
SITE_CHOOSER_URL_NAME = "public.index"


SITE_BACKEND = "ureport.backend.rapidpro.RapidProBackend"


# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone
TIME_ZONE = "GMT"
USER_TIME_ZONE = "GMT"
USE_TZ = True

MODELTRANSLATION_TRANSLATION_REGISTRY = "translation"

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = "en"

# Available languages for translation
LANGUAGES = (
    ("bn", "Bengali"),
    ("bs", "Bosnian"),
    ("en", "English"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("ar", "Arabic"),
    ("pt", "Portuguese"),
    ("pt-br", "Brazilian Portuguese"),
    ("uk", "Ukrainian"),
    ("uz", "Uzbek"),
    ("my", "Burmese"),
    ("mk-mk", "Macedonian"),
    ("id", "Indonesian"),
    ("it", "Italian"),
    ("ro", "Romanian"),
    ("vi", "Vietnamese"),
    ("sr-rs@latin", "Serbian (Latin, Serbia)"),
    ("bg", "Bulgarian"),
    ("hr-hr", "Croatian"),
    ("no", "Norwegian"),
    ("sv-se", "Swedish"),
    ("ru", "Russian"),
    ("kk", "Kazakh"),
    ("el", "Greek"),
    ("th", "Thai"),
    ("sl", "Slovenian"),
)

DEFAULT_LANGUAGE = "en"
RTL_LANGUAGES = ["ar"]

ORG_LANG_MAP = {
    "ar": "ar_AR",
    "en": "en_US",
    "es": "es_ES",
    "fr": "fr_FR",
    "id": "id_ID",
    "it": "it_IT",
    "my": "my_MM",
    "pt": "pt_PT",
    "pt-br": "pt_BR",
    "uk": "uk_UA",
    "vi": "vi_VN",
}


SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale
USE_L10N = True

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = "/sitestatic/"
COMPRESS_URL = "/sitestatic/"

# URL prefix for admin static files -- CSS, JavaScript and images.
# Make sure to use a trailing slash.
# Examples: "http://foo.com/static/admin/", "/static/admin/".
ADMIN_MEDIA_PREFIX = "/sitestatic/admin/"

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
)

COMPRESS_PRECOMPILERS = (
    ("text/coffeescript", "coffee --compile --stdio"),
    ("text/less", "lessc {infile} {outfile}"),
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = "bangbangrootplaydeadn7#^+-u-#1wm=y3a$-#^jps5tihx5v_@-_(kxumq_$+$5r)bxo"

MIDDLEWARE = (
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "dash.orgs.middleware.SetOrgMiddleware",
    # "debug_toolbar.middleware.DebugToolbarMiddleware",
)

X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_AGE = 900
CSRF_COOKIE_AGE = 7200


ROOT_URLCONF = "ureport.urls"

DATA_API_BACKENDS_CONFIG = {
    "rapidpro": {
        "name": "RapidPro",
        "slug": "rapidpro",
        "class_type": "ureport.backend.rapidpro.RapidProBackend",
    }
}

DATA_API_BACKEND_TYPES = (
    ("ureport.backend.rapidpro.RapidProBackend", "RapidPro Backend Type"),
    ("ureport.backend.floip.FLOIPBackend", "FLOIP Backend Type"),
)


DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB

BACKENDS_ORG_CONFIG_FIELDS = [
    dict(
        name="reporter_group",
        field=dict(help_text=_("The name of the Contact Group that contains registered reporters")),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="born_label",
        field=dict(help_text=_("The label of the Contact Field that contains the birth date of reporters")),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="gender_label",
        field=dict(help_text=_("The label of the Contact Field that contains the gender of reporters")),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="occupation_label",
        field=dict(
            help_text=_("The label of the Contact Field that contains the occupation of reporters"),
            required=False,
        ),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="registration_label",
        field=dict(help_text=_("The label of the Contact Field that contains the registration date of reporters")),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="state_label",
        field=dict(
            help_text=_("The label of the Contact Field that contains the State of reporters"),
            required=False,
        ),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="district_label",
        field=dict(
            help_text=_("The label of the Contact Field that contains the District of reporters"),
            required=False,
        ),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="ward_label",
        field=dict(
            help_text=_("The label of the Contact Field that contains the Ward of reporters"),
            required=False,
        ),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="male_label",
        field=dict(help_text=_("The label assigned to U-Reporters that are Male.")),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="female_label",
        field=dict(help_text=_("The label assigned to U-Reporters that are Female.")),
        superuser_only=True,
        read_only=True,
    ),
]

ORG_CONFIG_FIELDS = [
    dict(
        name="is_on_landing_page",
        field=dict(
            help_text=_("Whether this org should be show on the landing page"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="has_count_on_link_only",
        field=dict(
            help_text=_("Whether this org count should consider the count from link only"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="shortcode",
        field=dict(
            help_text=_("The shortcode that users will use to contact U-Report locally"),
            label="Shortcode",
            required=False,
        ),
    ),
    dict(
        name="whatsapp_number",
        field=dict(
            help_text=_("The WhatsApp number that users will use to contact U-Report if you have one"),
            label="WhatApp Number",
            required=False,
        ),
    ),
    dict(
        name="telegram_bot",
        field=dict(
            help_text=_("The Telegram bot that users will use to contact U-Report if you have one"),
            label="Telegram Bot",
            required=False,
        ),
    ),
    dict(
        name="viber_username",
        field=dict(
            help_text=_("The viber username that users will use to contact U-Report if you have one"),
            label="Viber Username",
            required=False,
        ),
    ),
    dict(
        name="line_link",
        field=dict(
            help_text=_("The Line bot link that users will use to contact U-Report if you have one"),
            label="Line Link",
            required=False,
        ),
    ),
    dict(
        name="has_ureport_app",
        field=dict(
            help_text=_("If there is a U-Report app available."),
            label="Display U-Report App",
            required=False,
        ),
    ),
    dict(
        name="join_button_text",
        field=dict(
            help_text=_("The join button text"),
            label="Join Button Text",
            required=False,
        ),
    ),
    dict(
        name="join_text",
        field=dict(
            help_text=_("The short text used to direct visitors to join U-Report"),
            label="Join Text",
            required=False,
        ),
    ),
    dict(
        name="join_text_top",
        field=dict(
            help_text=_("The call to action text to join on the top section on U-Report"),
            label="Join Call to Action Text",
            required=False,
        ),
    ),
    dict(
        name="external_stories_link",
        field=dict(
            help_text=_("The link for the external stories."),
            label="External Stories URL",
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="extra_menu_text",
        field=dict(
            help_text=_("A short text for the extra menu."),
            label="Extra Menu Text",
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="extra_menu_link",
        field=dict(
            help_text=_("The link for the extra menu."),
            label="Extra Menu Link",
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="homepage_join_video_id",
        field=dict(
            help_text=_("The YouTube video ID for how to join U-Report section"),
            label="Homepage Video ID",
            required=False,
        ),
    ),
    dict(
        name="photos_section_title",
        field=dict(
            help_text=_("The title of the photos section U-Report homepage"),
            label="Photos Section Title",
            required=False,
        ),
    ),
    dict(
        name="photos_section_description",
        field=dict(
            help_text=_("The description of the photos section U-Report homepage"),
            label="Photos Description",
            required=False,
        ),
    ),
    dict(
        name="opinions_description",
        field=dict(
            help_text=_("The description of the opinions page"),
            label="Opinions Description",
            required=False,
        ),
    ),
    dict(
        name="stories_description",
        field=dict(
            help_text=_("The description of the stories page"),
            label="Stories Description",
            required=False,
        ),
    ),
    dict(
        name="engagement_description",
        field=dict(
            help_text=_("The description of the engagement page"),
            label="Engagement Description",
            required=False,
        ),
    ),
    dict(
        name="engagement_footer_callout",
        field=dict(
            help_text=_("The callout message on the footer engagement section"),
            label="Egagement callout messages",
            required=False,
        ),
    ),
    dict(
        name="dark1_color",
        field=dict(
            help_text=_("The primary color for styling for this organization, should be dark"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="dark2_color",
        field=dict(
            help_text=_("The secondary color for styling for this organization, should be dark"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="dark3_color",
        field=dict(
            help_text=_("The tertiary color for styling for this organization, should be dark"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="light1_color",
        field=dict(
            help_text=_("The primary highlight color for styling for this organization, should be light"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="light2_color",
        field=dict(
            help_text=_("The secondary highlight color for styling for this organization, should be light"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="colors",
        field=dict(
            help_text=_("Up to 6 colors for styling charts, use comma between colors"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="colors_map",
        field=dict(
            help_text=_("11 colors for styling maps, use comma between colors, not used if not 11 colors"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="limit_states",
        field=dict(help_text=_("The states to show on maps only"), required=False),
        superuser_only=True,
    ),
    dict(
        name="limit_poll_states",
        field=dict(
            help_text=_("The states to show on maps only, used to filter poll results"),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="google_tag_manager_id",
        field=dict(
            help_text=_("The Google Tag Manager ID for this organization"),
            label="Google Tag Manager ID",
            required=False,
        ),
    ),
    dict(
        name="google_tracking_id",
        field=dict(
            help_text=_("The Google Analytics Tracking ID for this organization"),
            label="Google Tracking ID",
            required=False,
        ),
    ),
    dict(
        name="youtube_channel_url",
        field=dict(
            help_text=_("The URL to the Youtube channel for this organization"),
            label="Youtube Channel URL",
            required=False,
        ),
    ),
    dict(
        name="facebook_meta_verification",
        field=dict(
            help_text=_("The content for the meta tag for Facebook Domain Verification"),
            label="Facebook Domain Verification",
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="facebook_page_url",
        field=dict(
            help_text=_("The URL to the Facebook page for this organization"),
            label="Facebook Page URL",
            required=False,
        ),
    ),
    dict(
        name="facebook_page_id",
        field=dict(
            help_text=_("The integer id to the Facebook page for this organization (optional)"),
            label="Facebook Page ID",
            required=False,
        ),
    ),
    dict(
        name="facebook_app_id",
        field=dict(
            help_text=_("The integer id to the Facebook app for this organization's chat app (optional)"),
            label="Facebook App ID",
            required=False,
        ),
    ),
    dict(
        name="facebook_welcome_text",
        field=dict(
            help_text=_("The short text used to greet users on Facebook Messenger Plugin"),
            label="Facebook Welcome Text",
            required=False,
        ),
    ),
    dict(
        name="facebook_pixel_id",
        field=dict(
            help_text=_("The id of the Facebook Pixel for this organization (optional)"),
            label="Facebook Pixel ID",
            required=False,
        ),
    ),
    dict(
        name="instagram_username",
        field=dict(
            help_text=_("The Instagram username for this organization"),
            label="Instagram Username",
            required=False,
        ),
    ),
    dict(
        name="has_instagram_deeplink",
        field=dict(
            help_text=_("The Instagram username should be shown on the join page as deeplink for this organization"),
            label="Instagram Deeplink",
            required=False,
        ),
    ),
    dict(
        name="instagram_lightwidget_id",
        field=dict(
            help_text=_("The Instagram widget id from lightwidget.com"),
            label="Instagram LightWidget ID",
            required=False,
        ),
    ),
    dict(
        name="twitter_handle",
        field=dict(
            help_text=_("The Twitter handle for this organization"),
            label="Twitter Handle",
            required=False,
        ),
    ),
    dict(
        name="twitter_search_widget",
        field=dict(
            help_text=_("The Twitter widget used for searching"),
            label="Twitter Search Widget ID",
            required=False,
        ),
    ),
    dict(
        name="ignore_words",
        field=dict(
            help_text=_("The words to filter out from the results on public site"),
            label="Ignore Words",
            required=False,
        ),
    ),
    dict(
        name="has_jobs",
        field=dict(
            help_text=_("If there are jobs to be shown on the public site."),
            label="Display Jobs Tab",
            required=False,
        ),
    ),
    dict(
        name="is_global",
        field=dict(
            help_text=_("If this org if for global data. e.g: It shows a world map instead of a country map."),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="has_extra_gender",
        field=dict(help_text=_("Whether to activate an extra gender."), required=False),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="has_new_brand",
        field=dict(
            help_text=_("Whether to use the new 2024 brand with UNICEF in the logo and a common theme."),
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="has_charts_hidden",
        field=dict(
            help_text=_("Whether to hide the engagement breakdown charts."),
            required=False,
        ),
    ),
    dict(
        name="has_footer_unicef_logo",
        field=dict(
            help_text=_("Whether to show the UNICEF logo in the footer."),
            required=False,
        ),
    ),
    dict(
        name="iso_code",
        field=dict(
            help_text=_(
                "The alpha-3 ISO code of the organization so that it appears the stories widget U-Report App. Example: BRA, NIG, CMR (Use GLOBAL if U-Report is Global)."
            ),
            label="Country ISO code",
            required=False,
        ),
    ),
    dict(
        name="headline_font",
        field=dict(help_text=_("The font used for headline texts"), required=False),
        superuser_only=True,
    ),
    dict(
        name="text_font",
        field=dict(help_text=_("The font used for normal text"), required=False),
        superuser_only=True,
    ),
    dict(
        name="is_participation_hidden",
        field=dict(help_text=_("Hide participation stats"), required=False),
        superuser_only=True,
    ),
    dict(
        name="ureport_announcement",
        field=dict(
            help_text=_("The text to describe the sponsors of free messages"),
            label="Announcement",
            required=False,
        ),
        superuser_only=True,
    ),
    dict(
        name="text_small_font",
        field=dict(help_text=_("The font used for small text"), required=False),
        superuser_only=True,
    ),
    dict(
        name="custom_html",
        field=dict(
            help_text=_(
                "If you need to include some custom HTML codes in you org pages, like custom analytics code snippets"
            ),
            label="Custom HTML",
            required=False,
            widget=Textarea,
        ),
    ),
    dict(
        name="other_languages_sites",
        field=dict(help_text=_("Other language sites links"), required=False),
        superuser_only=True,
    ),
]


INSTALLED_APPS = (
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # the django admin
    "django.contrib.admin",
    # "debug_toolbar",
    # compress our CSS and js
    "compressor",
    # thumbnail
    "sorl.thumbnail",
    # smartmin
    "smartmin",
    # smartmin users
    "smartmin.users",
    # dash apps
    "dash.orgs",
    "dash.dashblocks",
    "dash.stories",
    "dash.utils",
    "dash.categories",
    "dash.tags",
    # ureport apps
    "ureport.admins",
    "ureport.api",
    "ureport.assets",
    "ureport.bots",
    "ureport.contacts",
    "ureport.countries",
    "ureport.flows",
    "ureport.jobs",
    "ureport.landingpages",
    "ureport.locations",
    "ureport.news",
    "ureport.polls",
    "ureport.stats",
    "django_countries",
    "rest_framework",
    "drf_yasg",
)

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"},
        "simple": {"format": "%(levelname)s %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        }
    },
    "loggers": {
        "httprouterthread": {"handlers": ["console"], "level": "INFO"},
        "django.request": {"handlers": ["console"], "level": "ERROR"},
    },
}

# -----------------------------------------------------------------------------------
# Directory Configuration
# -----------------------------------------------------------------------------------

PROJECT_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)))
RESOURCES_DIR = os.path.join(PROJECT_DIR, "../resources")

LOCALE_PATHS = (os.path.join(PROJECT_DIR, "../locale"),)
FIXTURE_DIRS = (os.path.join(PROJECT_DIR, "../fixtures"),)
TESTFILES_DIR = os.path.join(PROJECT_DIR, "../testfiles")
STATICFILES_DIRS = (
    os.path.join(PROJECT_DIR, "../static"),
    os.path.join(PROJECT_DIR, "../media"),
)
STATIC_ROOT = os.path.join(PROJECT_DIR, "../sitestatic")
MEDIA_ROOT = os.path.join(PROJECT_DIR, "../media")
MEDIA_URL = "/media/"


# -----------------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------------

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# -----------------------------------------------------------------------------------
# Templates Configuration
# -----------------------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(PROJECT_DIR, "../templates")],
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.request",
                "dash.orgs.context_processors.user_group_perms_processor",
                "dash.orgs.context_processors.set_org_processor",
                "ureport.public.context_processors.set_has_better_domain",
                "ureport.public.context_processors.set_is_iorg",
                "ureport.public.context_processors.set_linked_sites",
                "ureport.public.context_processors.set_config_display_flags",
                "ureport.public.context_processors.set_org_lang_params",
                "ureport.public.context_processors.set_story_widget_url",
            ],
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            "debug": False if TESTING else DEBUG,
        },
    }
]


# -----------------------------------------------------------------------------------
# Permission Management
# -----------------------------------------------------------------------------------

# this lets us easily create new permissions across our objects
PERMISSIONS = {
    "*": (
        "create",  # can create an object
        "read",  # can read an object, viewing it's details
        "update",  # can update an object
        "delete",  # can delete an object,
        "list",
    ),  # can view a list of the objects
    "dashblocks.dashblock": ("html",),
    "orgs.org": (
        "choose",
        "edit",
        "home",
        "manage_accounts",
        "create_login",
        "join",
        "refresh_cache",
    ),
    "polls.poll": (
        "questions",
        "responses",
        "images",
        "pull_refresh",
        "poll_date",
        "poll_flow",
    ),
    "stories.story": ("html", "images"),
}

# assigns the permissions that each group should have
GROUP_PERMISSIONS = {
    "Administrators": (
        "assets.image.*",
        "bots.bot.*",
        "categories.category.*",
        "categories.categoryimage.*",
        "dashblocks.dashblock.*",
        "dashblocks.dashblocktype.*",
        "jobs.jobsource.*",
        "landingpages.landingpage.*",
        "news.newsitem.*",
        "news.video.*",
        "orgs.org_edit",
        "orgs.org_home",
        "orgs.org_manage_accounts",
        "polls.poll.*",
        "polls.pollcategory.*",
        "polls.pollimage.*",
        "polls.featuredresponse.*",
        "stories.story.*",
        "stories.storyimage.*",
        "tags.tag.*",
    ),
    "Editors": (
        "assets.image.*",
        "bots.bot.*",
        "categories.category.*",
        "categories.categoryimage.*",
        "dashblocks.dashblock.*",
        "dashblocks.dashblocktype.*",
        "jobs.jobsource.*",
        "landingpages.landingpage.*",
        "news.newsitem.*",
        "news.video.*",
        "orgs.org_home",
        "polls.poll.*",
        "polls.pollcategory.*",
        "polls.pollimage.*",
        "polls.featuredresponse.*",
        "stories.story.*",
        "stories.storyimage.*",
        "tags.tag.*",
    ),
    "Global": ("countries.countryalias.*",),
}

# -----------------------------------------------------------------------------------
# Login / Logout
# -----------------------------------------------------------------------------------
LOGIN_URL = "/users/login/"
LOGOUT_URL = "/users/logout/"
LOGIN_REDIRECT_URL = "/manage/org/choose/"
LOGOUT_REDIRECT_URL = "/"

# -----------------------------------------------------------------------------------
# Auth Configuration
# -----------------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = ("django.contrib.auth.backends.ModelBackend",)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

ANONYMOUS_USER_NAME = "AnonymousUser"

# -----------------------------------------------------------------------------------
# Valkey Configuration
# -----------------------------------------------------------------------------------

# by default, celery doesn't have any timeout on our valkey connections, this fixes that
BROKER_TRANSPORT_OPTIONS = {"socket_timeout": 5}

CELERY_BROKER_URL = "redis://localhost:6379/1"

CELERY_RESULT_BACKEND = CELERY_BROKER_URL

# by default, celery doesn't have any timeout on our valkey connections, this fixes that
CELERY_BROKER_TRANSPORT_OPTIONS = {"socket_timeout": 5}

CELERY_TIMEZONE = "UTC"

CACHES = {
    "default": {
        "BACKEND": "django_valkey.cache.ValkeyCache",
        "LOCATION": CELERY_BROKER_URL,
    }
}

if "test" in sys.argv:
    CACHES["default"]["LOCATION"] = "redis://127.0.0.1:6379/15"

# -----------------------------------------------------------------------------------
# SMS Configs
# -----------------------------------------------------------------------------------

RAPIDSMS_TABS = []
SMS_APPS = ["mileage"]

# change this to your specific backend for your install
DEFAULT_BACKEND = "console"

# change this to the country code for your install
DEFAULT_COUNTRY_CODE = "250"

# -----------------------------------------------------------------------------------
# Debug Toolbar
# -----------------------------------------------------------------------------------

INTERNAL_IPS = ("127.0.0.1",)

# -----------------------------------------------------------------------------------
# Crontab Settings
# -----------------------------------------------------------------------------------

CELERY_TIMEZONE = "UTC"

CELERY_BEAT_SCHEDULE = {
    "refresh_flows": {
        "task": "polls.refresh_org_flows",
        "schedule": timedelta(minutes=20),
        "relative": True,
    },
    "recheck_poll_flow_data": {
        "task": "polls.recheck_poll_flow_data",
        "schedule": timedelta(minutes=15),
        "relative": True,
    },
    "fetch_old_sites_count": {
        "task": "polls.fetch_old_sites_count",
        "schedule": timedelta(minutes=20),
        "relative": True,
    },
    "check_contact_mismatch": {
        "task": "contacts.check_contacts_count_mismatch",
        "schedule": timedelta(minutes=30),
        "relative": True,
    },
    "contact-pull": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": crontab(minute=[0, 10, 20, 30, 40, 50]),
        "args": ("ureport.contacts.tasks.pull_contacts",),
    },
    "update-org-contact-counts": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": crontab(minute=[10, 30, 50]),
        "args": ("ureport.contacts.tasks.update_org_contact_count",),
    },
    "backfill-poll-results": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": timedelta(minutes=10),
        "relative": True,
        "args": ("ureport.polls.tasks.backfill_poll_results",),
    },
    "results-pull-main-poll": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": crontab(minute=[5, 25, 45]),
        "args": ("ureport.polls.tasks.pull_results_main_poll", "sync"),
    },
    "results-pull-recent-polls": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": timedelta(hours=1),
        "relative": True,
        "args": ("ureport.polls.tasks.pull_results_recent_polls", "sync"),
    },
    "results-pull-other-polls": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": timedelta(hours=1),
        "relative": True,
        "args": ("ureport.polls.tasks.pull_results_other_polls", "sync"),
    },
    "refresh-engagement-data": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": crontab(hour=2, minute=0),
        "args": ("ureport.stats.tasks.refresh_engagement_data", "slow"),
    },
    "delete-old-contact-activity": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": crontab(hour=22, minute=0),
        "args": ("ureport.stats.tasks.delete_old_contact_activities", "slow"),
    },
    "rebuild-poll-results-count": {
        "task": "polls.rebuild_counts",
        "schedule": crontab(hour=4, minute=0),
    },
    "clear-old-results": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": crontab(hour=6, minute=0),
        "args": ("ureport.polls.tasks.clear_old_poll_results", "slow"),
    },
    "polls_stats_squash": {
        "task": "polls.polls_stats_squash",
        "schedule": timedelta(minutes=30),
        "relative": True,
        "options": {"queue": "slow"},
    },
    "stats_activities_squash": {
        "task": "stats.squash_contact_activities_counts",
        "schedule": timedelta(minutes=15),
        "relative": True,
        "options": {"queue": "slow"},
    },
}

# -----------------------------------------------------------------------------------
# U-Report Defaults
# -----------------------------------------------------------------------------------
UREPORT_DEFAULT_PRIMARY_COLOR = "#FFD100"
UREPORT_DEFAULT_SECONDARY_COLOR = "#1F49BF"


# -----------------------------------------------------------------------------------
# non org urls
# -----------------------------------------------------------------------------------
SITE_ALLOW_NO_ORG = (
    "public.countries",
    "public.status",
    "public.task_status",
    "public.shared_sites_count",
    "api",
    "api.v1",
    "api.v1.docs",
    "api.v1.org_list",
    "api.v1.org_details",
    "api.v1.org_poll_list",
    "api.v1.org_poll_featured",
    "api.v1.poll_details",
    "api.v1.org_newsitem_list",
    "api.v1.newsitem_details",
    "api.v1.org_video_list",
    "api.v1.video_details",
    "api.v1.org_asset_list",
    "api.v1.asset_details",
    "api.v1.org_story_list",
    "api.v1.story_details",
)


# -----------------------------------------------------------------------------------
# Country flags
# -----------------------------------------------------------------------------------
COUNTRY_FLAGS_SITES = [
    dict(
        name="Afghanistan",
        host="//afghanistan.ureport.in/",
        flag="flag_afghanistan.png",
        countries_codes=["AFG"],
        count_link="http://afghanistan.ureport.in/count/",
        region="ROSA",
    ),
    dict(
        name="Angola",
        host="//angola.ureport.in",
        flag="flag_angola.png",
        countries_codes=["AGO"],
        count_link="http://angola.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Argentina",
        host="//argentina.ureport.in/",
        flag="flag_argentina.png",
        countries_codes=["ARG"],
        count_link="http://argentina.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Australia",
        host="//australia.ureport.in",
        flag="",
        countries_codes=["AUS"],
        count_link="http://australia.ureport.in/count/",
        region="NATCOM",
    ),
    dict(
        name="Bangladesh",
        host="//bangladesh.ureport.in/",
        flag="flag_bangladesh.png",
        countries_codes=["BGD"],
        count_link="http://bangladesh.ureport.in/count/",
        region="ROSA",
    ),
    dict(
        name="Barbados",
        host="//barbados.ureport.in/",
        flag="flag_barbados.png",
        countries_codes=["BRB"],
        count_link="http://barbados.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Belize",
        host="//belize.ureport.in/",
        flag="flag_belize.png",
        countries_codes=["BLZ"],
        count_link="http://belize.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Benin",
        host="//benin.ureport.in/",
        flag="flag_benin.png",
        countries_codes=["BEN"],
        count_link="http://benin.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Bolivia",
        host="//bolivia.ureport.in/",
        flag="flag_bolivia.png",
        countries_codes=["BOL"],
        count_link="http://bolivia.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Bosnia and Herzegovina",
        host="//bih.ureport.in/",
        flag="flag_bih.png",
        countries_codes=["BIH"],
        count_link="http://bih.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Brazil",
        host="//brasil.ureport.in/",
        flag="flag_brasil.png",
        countries_codes=["BRA"],
        count_link="http://brasil.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Bulgaria",
        host="//bulgaria.ureport.in/",
        flag="flag_bulgaria.png",
        countries_codes=["BGA"],
        count_link="http://bulgaria.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Botswana",
        host="//botswana.ureport.in/",
        flag="flag_botswana.png",
        countries_codes=["BWA"],
        count_link="http://botswana.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Burkina Faso",
        host="//burkinafaso.ureport.in/",
        flag="flag_burkinafaso.png",
        countries_codes=["BFA"],
        count_link="http://burkinafaso.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Burundi",
        host="//burundi.ureport.in/",
        flag="flag_burundi.png",
        countries_codes=["BDI"],
        count_link="http://burundi.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Canada",
        host="//canada-en.ureport.in/",
        flag="flag_canada-en.png",
        countries_codes=["CAN"],
        count_link="http://canada-en.ureport.in/count/",
        region="NATCOM",
    ),
    dict(
        name="Cameroun",
        host="//cameroon.ureport.in/",
        flag="flag_cameroon.png",
        countries_codes=["CMR"],
        count_link="http://cameroon.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="CAR",
        host="//centrafrique.ureport.in/",
        flag="flag_centrafrique.png",
        countries_codes=["CAF"],
        count_link="http://centrafrique.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Chile",
        host="//chile.ureport.in/",
        flag="flag_chile.png",
        countries_codes=["CHL"],
        count_link="http://chile.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Congo Brazzaville",
        host="//congobrazzaville.ureport.in/",
        flag="flag_congobrazzaville.png",
        countries_codes=["COG"],
        count_link="http://congobrazzaville.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Costa Rica",
        host="//costarica.ureport.in/",
        flag="flag_costarica.png",
        countries_codes=["CRI"],
        count_link="https://costarica.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Cote d'ivoire",
        host="//cotedivoire.ureport.in/",
        flag="flag_cotedivoire.png",
        countries_codes=["CIV"],
        count_link="http://cotedivoire.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Croatia",
        host="//croatia.ureport.in/",
        flag="flag_croatia.png",
        countries_codes=["HRV"],
        count_link="http://croatia.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Dominican Republic",
        host="//republicadominicana.ureport.in/",
        flag="",
        countries_codes=["DOM"],
        count_link="https://republicadominicana.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="DRC",
        host="//drc.ureport.in/",
        flag="flag_drc.png",
        countries_codes=["COD"],
        count_link="http://drc.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Eastern Caribbean Area",
        host="//eca.ureport.in/",
        flag="flag_eca.png",
        countries_codes=["ECA"],
        count_link="http://eca.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Ecuador",
        host="//ecuador.ureport.in/",
        flag="flag_ecuador.png",
        countries_codes=["ECU"],
        count_link="http://ecuador.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="El Salvador",
        host="//elsalvador.ureport.in/",
        flag="flag_elsalvador.png",
        countries_codes=["SLV"],
        count_link="http://elsalvador.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Eswatini",
        host="//eswatini.ureport.in/",
        flag="flag_eswatini.png",
        countries_codes=["SWZ"],
        count_link="http://eswatini.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Ethiopia",
        host="//ethiopia.ureport.in/",
        flag="",
        countries_codes=["ETH"],
        count_link="http://ethiopia.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Europe",
        host="//europe-uk.ureport.in/",
        flag="flag_europe-uk.png",
        countries_codes=["UKR"],
        count_link="http://europe-uk.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="France",
        host="//france.ureport.in",
        flag="flag_france.png",
        countries_codes=["FRA"],
        count_link="http://france.ureport.in/count/",
        region="NATCOM",
    ),
    dict(
        name="Gabon",
        host="//gabon.ureport.in/",
        flag="flag_gabon.png",
        countries_codes=["GAB"],
        count_link="http://gabon.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Gambia",
        host="//gambia.ureport.in/",
        flag="flag_gambia.png",
        countries_codes=["GMB"],
        count_link="http://gambia.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Ghana",
        host="//ghana.ureport.in/",
        flag="flag_ghana.png",
        countries_codes=["GHA"],
        count_link="http://ghana.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Greece",
        host="//greece.ureport.in/",
        flag="flag_greece.png",
        countries_codes=["GRC"],
        count_link="http://greece.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Guatemala",
        host="//guatemala.ureport.in/",
        flag="flag_guatemala.png",
        countries_codes=["GTM"],
        count_link="http://guatemala.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Guinea",
        host="//guinea.ureport.in/",
        flag="flag_guinea.png",
        countries_codes=["GIN"],
        count_link="http://guinea.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Guinea Ecuatorial",
        host="//guineaecuatorial.ureport.in/",
        flag="flag_guineaecuatorial.png",
        countries_codes=["GNQ"],
        count_link="http://guineaecuatorial.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Haiti",
        host="//haiti.ureport.in/",
        flag="flag_haiti.png",
        countries_codes=["HTI"],
        count_link="http://haiti.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Honduras",
        host="//honduras.ureport.in",
        flag="flag_honduras.png",
        countries_codes=["HND"],
        count_link="http://honduras.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="India",
        host="//india.ureport.in",
        flag="flag_india.png",
        countries_codes=["IND"],
        count_link="http://india.ureport.in/count/",
        region="ROSA",
    ),
    dict(
        name="Indonesia",
        host="//indonesia.ureport.in",
        flag="flag_indonesia.png",
        countries_codes=["IDN"],
        count_link="http://indonesia.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="Iraq",
        host="//iraq.ureport.in",
        flag="flag_iraq.png",
        countries_codes=["IRQ"],
        count_link="http://iraq.ureport.in/count/",
        region="MENA",
    ),
    dict(
        name="Ireland",
        host="//ireland.ureport.in",
        flag="flag_ireland.png",
        countries_codes=["IRL"],
        count_link="http://ireland.ureport.in/count/",
        region="NATCOM",
    ),
    dict(
        name="Italia",
        host="//italia.ureport.in",
        flag="flag_italia.png",
        countries_codes=["ITA"],
        count_link="http://italia.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Jamaica",
        host="//jamaica.ureport.in/",
        flag="flag_jamaica.png",
        countries_codes=["JAM"],
        count_link="http://jamaica.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Jordan",
        host="//jordan.ureport.in/",
        flag="flag_jordan.png",
        countries_codes=["JOR"],
        count_link="http://jordan.ureport.in/count/",
        region="MENA",
    ),
    dict(
        name="Kazakhstan",
        host="//kazakhstan-ru.ureport.in/",
        flag="",
        countries_codes=["KAZ"],
        count_link="http://kazakhstan-ru.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Kenya",
        host="//yunitok.in/",
        flag="flag_kenya.png",
        countries_codes=["KEN"],
        count_link="http://kenya.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Kiribati",
        host="//kiribati.ureport.in/",
        flag="flag_kiribati.png",
        countries_codes=["KIR"],
        count_link="http://kiribati.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="Kyrgyzstan",
        host="//kyrgyzstan.ureport.in/",
        flag="flag_kyrgyzstan.png",
        countries_codes=["KGZ"],
        count_link="http://kyrgyzstan.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Lebanon",
        host="//lebanon.ureport.in/",
        flag="flag_lebanon.png",
        countries_codes=["LBN"],
        count_link="http://lebanon.ureport.in/count/",
        region="MENA",
    ),
    dict(
        name="Lesotho",
        host="//les.ureport.in/",
        flag="flag_les.png",
        countries_codes=["LSO"],
        count_link="http://les.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Liberia",
        host="//liberia.ureport.in/",
        flag="flag_liberia.png",
        countries_codes=["LBR"],
        count_link="http://liberia.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="North Macedonia",
        host="//mk.ureport.in/",
        flag="flag_mk.png",
        countries_codes=["MKD"],
        count_link="http://mk.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Madagascar",
        host="//madagascar.ureport.in/",
        flag="flag_madagascar.png",
        countries_codes=["MG"],
        count_link="http://madagascar.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Malawi",
        host="//malawi.ureport.in/",
        flag="flag_malawi.png",
        countries_codes=["MWI"],
        count_link="http://malawi.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Malaysia",
        host="//malaysia.ureport.in/",
        flag="flag_malaysia.png",
        countries_codes=["MYS"],
        count_link="http://malaysia.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="Mali",
        host="//mali.ureport.in/",
        flag="flag_mali.png",
        countries_codes=["MLI"],
        count_link="http://mali.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Mauritania",
        host="//mauritania.ureport.in/",
        flag="flag_mauritania.png",
        countries_codes=["MRT"],
        count_link="https://mauritania.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Mexico",
        host="//mexico.ureport.in/",
        flag="flag_mexico.png",
        countries_codes=["MEX"],
        count_link="http://mexico.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Micronesia",
        host="//micronesia.ureport.in",
        flag="flag_micronesia.png",
        countries_codes=["FSM"],
        count_link="http://micronesia.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="Moldova",
        host="//moldova.ureport.in",
        flag="flag_moldova.png",
        countries_codes=["MDA"],
        count_link="http://moldova.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Morocco",
        host="//morocco.ureport.in",
        flag="flag_morocco.png",
        countries_codes=["MAR"],
        count_link="http://morocco.ureport.in/count/",
        region="MENA",
    ),
    dict(
        name="Mozambique",
        host="//smsbiz.co.mz/",
        flag="flag_mozambique.png",
        countries_codes=["MOZ"],
        count_link="http://smsbiz.co.mz/count/",
        region="ESARO",
    ),
    dict(
        name="Myanmar",
        host="//myanmar.ureport.in",
        flag="flag_myanmar.png",
        countries_codes=["MMR"],
        count_link="http://myanmar.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="Namibia",
        host="//namibia.ureport.in",
        flag="flag_namibia.png",
        countries_codes=["NAM"],
        count_link="http://namibia.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Nicaragua",
        host="//nicaragua.ureport.in",
        flag="flag_nicaragua.png",
        countries_codes=["NIC"],
        count_link="http://nicaragua.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Niger",
        host="//niger.ureport.in",
        flag="flag_niger.png",
        countries_codes=["NER"],
        count_link="http://niger.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Nigeria",
        host="//nigeria.ureport.in",
        flag="flag_nigeria.png",
        countries_codes=["NGA"],
        count_link="http://nigeria.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Nigeria24x7",
        host="//nigeria24x7.ureport.in",
        flag="flag_nigeria24x7.png",
        countries_codes=["NGA"],
        count_link="http://nigeria24x7.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Nepal",
        host="//nepal.ureport.in",
        flag="flag_nepal.png",
        countries_codes=["NPL"],
        count_link="http://nepal.ureport.in/count/",
        region="ROSA",
    ),
    dict(
        name="Norge",
        host="//norge.ureport.in",
        flag="flag_norge.png",
        countries_codes=["NOR"],
        count_link="http://norge.ureport.in/count/",
        region="NATCOM",
    ),
    dict(
        name="OECS",
        host="//oecs.ureport.in",
        flag="flag_oecs.png",
        countries_codes=["ATG"],  # ["ATG", "VGB", "DMA", "GRD", "MSR", "KNA", "LCA", "VCT", "TCA"],
        count_link="http://oecs.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="On the move",
        host="//onthemove.ureport.in",
        flag="flag_onthemove.png",
        countries_codes=["ITA"],
        count_link="http://onthemove.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Pacific",
        host="//pacific.ureport.in",
        flag="flag_pacific.png",
        countries_codes=["FJI"],  # ["COK", "FJI", "MHL", "NRU", "NIU", "PLW", "WSM", "TKL", "TON", "TUV", "VUT"],
        count_link="http://pacific.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="Pakistan",
        host="//ureport.pk",
        flag="flag_pakistan.png",
        countries_codes=["PAK"],
        count_link="http://ureport.pk/count/",
        region="ROSA",
    ),
    dict(
        name="Panama",
        host="//panama.ureport.in",
        flag="flag_panama.png",
        countries_codes=["PAN"],
        count_link="http://panama.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Paraguay",
        host="//paraguay.ureport.in",
        flag="flag_paraguay.png",
        countries_codes=["PAR"],
        count_link="http://paraguay.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Philippines",
        host="//philippines.ureport.in",
        flag="flag_philippines.png",
        countries_codes=["PHL"],
        count_link="http://philippines.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="PNG",
        host="//png.ureport.in",
        flag="flag_png.png",
        countries_codes=["PNG"],
        count_link="http://png.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="România",
        host="//romania.ureport.in/",
        flag="flag_romania.png",
        countries_codes=["ROU"],
        count_link="http://romania.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="São Tomé and Príncipe",
        host="//stp.ureport.in",
        flag="flag_stp.png",
        countries_codes=["STP"],
        count_link="http://stp.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Senegal",
        host="//senegal.ureport.in/",
        flag="flag_senegal.png",
        countries_codes=["SEN"],
        count_link="http://senegal.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Serbia",
        host="//serbia.ureport.in/",
        flag="flag_serbia.png",
        countries_codes=["SRB"],
        count_link="http://serbia.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Sierra Leone",
        host="//sierraleone.ureport.in",
        flag="flag_sierraleone.png",
        countries_codes=["SLE"],
        count_link="http://sierraleone.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Slovenija",
        host="//slovenija.ureport.in",
        flag="flag_slovenija.png",
        countries_codes=["SVN"],
        count_link="http://slovenija.ureport.in/count/",
        region="NATCOM",
    ),
    dict(
        name="Solomon Islands",
        host="//solomonislands.ureport.in",
        flag="flag_solomonislands.png",
        countries_codes=["SLB"],
        count_link="http://solomonislands.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="Somalia",
        host="//somalia.ureport.in",
        flag="flag_somalia.png",
        countries_codes=["SOM"],
        count_link="http://somalia.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="South Africa",
        host="//sa.ureport.in",
        flag="flag_sa.png",
        countries_codes=["ZAF"],
        count_link="http://sa.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="South Asia",
        host="//southasia.ureport.in",
        flag="flag_southasia.png",
        countries_codes=[],  # ["AFG", "BGD", "BTN", "IND", "MDV", "NPL", "PAK", "LKA"],
        count_link="http://southasia.ureport.in/count/",
        region="ROSA",
    ),
    dict(
        name="Sudan",
        host="//sudan.ureport.in",
        flag="flag_sudan.png",
        countries_codes=["SDN"],
        count_link="http://sudan.ureport.in/count/",
        region="MENA",
    ),
    dict(
        name="Sverige",
        host="//sverige.ureport.in",
        flag="flag_sverige.png",
        countries_codes=["SWE"],
        count_link="http://sverige.ureport.in/count/",
        region="NATCOM",
    ),
    dict(
        name="Tanzania",
        host="//tanzania.ureport.in",
        flag="flag_tanzania.png",
        countries_codes=["TZA"],
        count_link="http://tanzania.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Tchad",
        host="//tchad.ureport.in",
        flag="flag_tchad.png",
        countries_codes=["TCD"],
        count_link="http://tchad.ureport.in/count/",
        region="WCARO",
    ),
    dict(
        name="Thailand",
        host="//thailand.ureport.in",
        flag="flag_thailand.png",
        countries_codes=["THA"],
        count_link="http://thailand.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="Trinidad and Tobago",
        host="//tt.ureport.in/",
        flag="flag_tt.png",
        countries_codes=["TTO"],
        count_link="http://tt.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Tunisia",
        host="//tunisie.ureport.in",
        flag="flag_tunisie.png",
        countries_codes=["TUN"],
        count_link="http://tunisie.ureport.in/count/",
        region="MENA",
    ),
    dict(
        name="Uganda",
        host="//ureport.ug",
        flag="flag_uganda.png",
        countries_codes=["UGA"],
        count_link="http://ureport.ug/count/",
        region="ESARO",
    ),
    dict(
        name="Uniendo Voces - Bolivia",
        host="//uniendovoces-bol.ureport.in",
        flag="flag_uniendovoces-bol.png",
        countries_codes=["BOL"],
        count_link="http://uniendovoces-bol.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Uniendo Voces - Brasil",
        host="//uniendovoces-br.ureport.in",
        flag="flag_uniendovoces-br.png",
        countries_codes=["BRA"],
        count_link="http://uniendovoces-br.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Uniendo Voces - Ecuador",
        host="//uniendovoces-ec.ureport.in",
        flag="flag_uniendovoces-ec.png",
        countries_codes=["ECU"],
        count_link="http://uniendovoces-ec.ureport.in/count/",
        region="LACRO",
    ),
    dict(
        name="Ukraine",
        host="//ukraine.ureport.in",
        flag="flag_ukraine.png",
        countries_codes=["UKR"],
        count_link="http://ukraine.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Uzbekistan",
        host="//uzbekistan.ureport.in",
        flag="flag_uzberkistan.png",
        countries_codes=["UZB"],
        count_link="http://uzbekistan.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Vietnam",
        host="//vietnam.ureport.in",
        flag="flag_vietnam.png",
        countries_codes=["VNM"],
        count_link="http://vietnam.ureport.in/count/",
        region="EAPRO",
    ),
    dict(
        name="Western Balkans",
        host="//westernbalkans.ureport.in",
        flag="flag_westernbalkans.png",
        countries_codes=["ALB", "XKX", "MNE"],
        count_link="http://westernbalkans.ureport.in/count/",
        region="ECARO",
    ),
    dict(
        name="Zambia",
        host="//zm.ureport.in",
        flag="flag_zm.png",
        countries_codes=["ZMB"],
        count_link="http://zm.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Zimbabwe",
        host="//zimbabwe.ureport.in",
        flag="flag_zimbabwe.png",
        countries_codes=["ZWE"],
        count_link="http://zimbabwe.ureport.in/count/",
        region="ESARO",
    ),
    dict(
        name="Global",
        host="//ureport.in",
        flag="",
        countries_codes=[],
        show_icon=False,
        count_link="https://www.ureport.in/count/",
        region="All",
    ),
]


# -----------------------------------------------------------------------------------
# Old country sites
# -----------------------------------------------------------------------------------
PREVIOUS_ORG_SITES = []  # Not uset anymore

# -----------------------------------------------------------------------------------
# Other sites to get counts for but not display the flag
# -----------------------------------------------------------------------------------
OTHER_ORG_COUNT_SITES = []  # Not used anymore


# -----------------------------------------------------------------------------------
# rest_framework config
# -----------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "PAGE_SIZE": 10,  # Default to 10
    "PAGINATE_BY_PARAM": "page_size",  # Allow client to override, using `?page_size=xxx`.
    "MAX_PAGINATE_BY": 100,
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.coreapi.AutoSchema",
}


SWAGGER_SETTINGS = {"SECURITY_DEFINITIONS": {"basic": {"type": "basic"}}}

STORY_WIDGET_URL = "https://ureportapp.ilhasoft.mobi/widget/"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "root": {"level": "WARNING", "handlers": ["console"]},
    "formatters": {"verbose": {"format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"}},
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "null": {"class": "logging.NullHandler"},
    },
    "loggers": {
        "pycountry": {"level": "ERROR", "handlers": ["console"], "propagate": False},
        "django.security.DisallowedHost": {"handlers": ["null"], "propagate": False},
        "django.db.backends": {
            "level": "ERROR",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}

SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {"basic": {"type": "basic"}},
}
