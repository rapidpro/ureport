# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys
from datetime import timedelta

from django.forms import Textarea
from django.utils.translation import ugettext_lazy as _

from celery.schedules import crontab

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
SITE_CHOOSER_TEMPLATE = "public/org_chooser.haml"
SITE_CHOOSER_URL_NAME = "public.home"


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
    ("id", "Indonesian"),
    ("it", "Italian"),
    ("ro", "Romanian"),
    ("vi", "Vietnamese"),
    ("sr-rs@latin", "Serbian (Latin, Serbia)"),
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

COMPRESS_PRECOMPILERS = (("text/coffeescript", "coffee --compile --stdio"), ("text/less", "lessc {infile} {outfile}"))

# Make this unique, and don't share it with anybody.
SECRET_KEY = "bangbangrootplaydeadn7#^+-u-#1wm=y3a$-#^jps5tihx5v_@-_(kxumq_$+$5r)bxo"

MIDDLEWARE = (
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "dash.orgs.middleware.SetOrgMiddleware",
    "ureport.utils.middleware.CheckVersionMiddleware",
)

ROOT_URLCONF = "ureport.urls"


DATA_API_BACKENDS_CONFIG = {
    "rapidpro": {"name": "RapidPro", "slug": "rapidpro", "class_type": "ureport.backend.rapidpro.RapidProBackend"}
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
            help_text=_("The label of the Contact Field that contains the occupation of reporters"), required=False
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
        field=dict(help_text=_("The label of the Contact Field that contains the State of reporters"), required=False),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="district_label",
        field=dict(
            help_text=_("The label of the Contact Field that contains the District of reporters"), required=False
        ),
        superuser_only=True,
        read_only=True,
    ),
    dict(
        name="ward_label",
        field=dict(help_text=_("The label of the Contact Field that contains the Ward of reporters"), required=False),
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
        field=dict(help_text=_("Whether this org should be show on the landing page"), required=False),
        superuser_only=True,
    ),
    dict(
        name="has_count_on_link_only",
        field=dict(help_text=_("Whether this org count should consider the count from link only"), required=False),
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
            help_text=_("The whatapp number that users will use to contact U-Report if you have one"),
            label="Whatapp Number",
            required=False,
        ),
    ),
    dict(
        name="join_text",
        field=dict(
            help_text=_("The short text used to direct visitors to join U-Report"), label="Join Text", required=False
        ),
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
        field=dict(help_text=_("The description of the opinions page"), label="Opinions Description", required=False),
    ),
    dict(
        name="stories_description",
        field=dict(help_text=_("The description of the stories page"), label="Stories Description", required=False),
    ),
    dict(
        name="engagement_description",
        field=dict(
            help_text=_("The description of the engagement page"), label="Engagement Description", required=False
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
        field=dict(help_text=_("The primary color for styling for this organization, should be dark"), required=False),
        superuser_only=True,
    ),
    dict(
        name="dark2_color",
        field=dict(
            help_text=_("The secondary color for styling for this organization, should be dark"), required=False
        ),
        superuser_only=True,
    ),
    dict(
        name="dark3_color",
        field=dict(
            help_text=_("The tertiary color for styling for this organization, should be dark"), required=False
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
        field=dict(help_text=_("Up to 6 colors for styling charts, use comma between colors"), required=False),
        superuser_only=True,
    ),
    # deprecated, can be removed after v2 launch
    dict(
        name="join_fg_color",
        field=dict(help_text=_("The color used to draw the text on the join bar"), required=False),
        superuser_only=True,
    ),
    # deprecated, can be removed after v2 launch
    dict(
        name="join_bg_color",
        field=dict(help_text=_("The color used to draw the background on the join bar"), required=False),
        superuser_only=True,
    ),
    # deprecated, should be replaced by dark1
    dict(
        name="primary_color",
        field=dict(help_text=_("The primary color for styling for this organization"), required=False),
        superuser_only=True,
    ),
    # deprecated, should be replaced by dark2
    dict(
        name="secondary_color",
        field=dict(help_text=_("The secondary color for styling for this organization"), required=False),
        superuser_only=True,
    ),
    # deprecated, can be removed after v2 launch
    dict(
        name="bg_color",
        field=dict(help_text=_("The background color for the site"), required=False),
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
        field=dict(help_text=_("The states to show on maps only, used to filter poll results"), required=False),
        superuser_only=True,
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
            help_text=_("The Instagram username for this organization"), label="Instagram Username", required=False
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
        field=dict(help_text=_("The Twitter handle for this organization"), label="Twitter Handle", required=False),
    ),
    dict(
        name="twitter_search_widget",
        field=dict(
            help_text=_("The Twitter widget used for searching"), label="Twitter Search Widget ID", required=False
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
            help_text=_("If there are jobs to be shown on the public site."), label="Display Jobs Tab", required=False
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
        name="has_new_design",
        field=dict(help_text=_("Whether to activate the new design."), required=False),
        superuser_only=True,
        read_only=True,
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
        name="text_font", field=dict(help_text=_("The font used for normal text"), required=False), superuser_only=True
    ),
    dict(
        name="is_participation_hidden",
        field=dict(help_text=_("Hide participation stats"), required=False),
        superuser_only=True,
    ),
    dict(
        name="ureport_announcement",
        field=dict(
            help_text=_("The text to describe the sponsors of free messages"), label="Announcement", required=False
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
    # compress our CSS and js
    "compressor",
    # thumbnail
    "sorl.thumbnail",
    # smartmin
    "smartmin",
    # import tasks
    "smartmin.csv_imports",
    # smartmin users
    "smartmin.users",
    # dash apps
    "dash.orgs",
    "dash.dashblocks",
    "dash.stories",
    "dash.utils",
    "dash.categories",
    # ureport apps
    "ureport.admins",
    "ureport.api",
    "ureport.assets",
    "ureport.contacts",
    "ureport.countries",
    "ureport.jobs",
    "ureport.locations",
    "ureport.news",
    "ureport.polls",
    "ureport.stats",
    "django_countries",
    "rest_framework",
    "rest_framework_swagger",
    "hamlpy",
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
    "handlers": {"console": {"level": "INFO", "class": "logging.StreamHandler", "formatter": "verbose"}},
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
STATICFILES_DIRS = (os.path.join(PROJECT_DIR, "../static"), os.path.join(PROJECT_DIR, "../media"))
STATIC_ROOT = os.path.join(PROJECT_DIR, "../sitestatic")
MEDIA_ROOT = os.path.join(PROJECT_DIR, "../media")
MEDIA_URL = "/media/"


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
                "ureport.assets.context_processors.set_assets_processor",
                "ureport.public.context_processors.set_has_better_domain",
                "ureport.public.context_processors.set_is_iorg",
                "ureport.public.context_processors.set_linked_sites",
                "ureport.public.context_processors.set_config_display_flags",
                "ureport.public.context_processors.set_org_lang_params",
                "ureport.public.context_processors.set_story_widget_url",
            ],
            "loaders": [
                "dash.utils.haml.HamlFilesystemLoader",
                "dash.utils.haml.HamlAppDirectoriesLoader",
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
    "orgs.org": ("choose", "edit", "home", "manage_accounts", "create_login", "join", "refresh_cache"),
    "polls.poll": ("questions", "responses", "images", "pull_refresh", "poll_date", "poll_flow"),
    "stories.story": ("html", "images"),
}

# assigns the permissions that each group should have
GROUP_PERMISSIONS = {
    "Administrators": (
        "assets.image.*",
        "categories.category.*",
        "categories.categoryimage.*",
        "dashblocks.dashblock.*",
        "dashblocks.dashblocktype.*",
        "jobs.jobsource.*",
        "news.newsitem.*",
        "news.video.*",
        "orgs.org_edit",
        "orgs.org_home",
        "orgs.org_manage_accounts",
        "orgs.org_profile",
        "polls.poll.*",
        "polls.pollcategory.*",
        "polls.pollimage.*",
        "polls.featuredresponse.*",
        "stories.story.*",
        "stories.storyimage.*",
        "users.user_profile",
    ),
    "Editors": (
        "categories.category.*",
        "categories.categoryimage.*",
        "dashblocks.dashblock.*",
        "dashblocks.dashblocktype.*",
        "jobs.jobsource.*",
        "news.newsitem.*",
        "news.video.*",
        "orgs.org_home",
        "orgs.org_profile",
        "polls.poll.*",
        "polls.pollcategory.*",
        "polls.pollimage.*",
        "polls.featuredresponse.*",
        "stories.story.*",
        "stories.storyimage.*",
        "users.user_profile",
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

ANONYMOUS_USER_NAME = "AnonymousUser"

# -----------------------------------------------------------------------------------
# Redis Configuration
# -----------------------------------------------------------------------------------

# by default, celery doesn't have any timeout on our redis connections, this fixes that
BROKER_TRANSPORT_OPTIONS = {"socket_timeout": 5}

BROKER_BACKEND = "redis"
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = "1"

BROKER_URL = "redis://%s:%s/%s" % (REDIS_HOST, REDIS_PORT, REDIS_DB)

CELERY_RESULT_BACKEND = BROKER_URL


CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": BROKER_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
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

CELERYBEAT_SCHEDULE = {
    "refresh_flows": {"task": "polls.refresh_org_flows", "schedule": timedelta(minutes=20), "relative": True},
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
    "polls_stats_squash": {"task": "polls.polls_stats_squash", "schedule": timedelta(minutes=10), "relative": True},
    "contact-pull": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": crontab(minute=[0, 10, 20, 30, 40, 50]),
        "args": ("ureport.contacts.tasks.pull_contacts",),
    },
    "backfill-poll-results": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": timedelta(minutes=10),
        "relative": True,
        "args": ("ureport.polls.tasks.backfill_poll_results", "sync"),
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
    "results-pull-brick-polls": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": timedelta(hours=1),
        "relative": True,
        "args": ("ureport.polls.tasks.pull_results_brick_polls", "sync"),
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
        "args": ("ureport.stats.tasks.refresh_engagement_data", "sync"),
    },
    "clear-old-results": {
        "task": "dash.orgs.tasks.trigger_org_task",
        "schedule": crontab(hour=4, minute=0),
        "args": ("ureport.polls.tasks.clear_old_poll_results", "sync"),
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
        name="Argentina",
        host="//argentina.ureport.in/",
        flag="flag_argentina.png",
        is_static=True,
        count_link="http://argentina.ureport.in/count/",
    ),
    dict(
        name="Bangladesh",
        host="//bangladesh.ureport.in/",
        flag="flag_bangladesh.png",
        is_static=True,
        count_link="http://bangladesh.ureport.in/count/",
    ),
    dict(
        name="Belize",
        host="//belize.ureport.in/",
        flag="flag_belize.png",
        is_static=True,
        count_link="http://belize.ureport.in/count/",
    ),
    dict(
        name="Bolivia",
        host="//bolivia.ureport.in/",
        flag="flag_bolivia.png",
        is_static=True,
        count_link="http://bolivia.ureport.in/count/",
    ),
    dict(
        name="Bosnia and Herzegovina",
        host="//bih.ureport.in/",
        flag="flag_bosnia_and_herzegovina.png",
        is_static=True,
        count_link="http://bih.ureport.in/count/",
    ),
    dict(
        name="Brazil",
        host="//ureportbrasil.org.br/",
        flag="flag_brazil.png",
        is_static=True,
        count_link="http://brasil.ureport.in/count/",
    ),
    dict(
        name="Botswana",
        host="//botswana.ureport.in/",
        flag="flag_botswana.png",
        is_static=True,
        count_link="http://botswana.ureport.in/count/",
    ),
    dict(
        name="Burkina Faso",
        host="//burkinafaso.ureport.in/",
        flag="flag_burkina_faso.png",
        is_static=True,
        count_link="http://burkinafaso.ureport.in/count/",
    ),
    dict(
        name="Burundi",
        host="//burundi.ureport.in/",
        flag="flag_burundi.png",
        is_static=True,
        count_link="http://burundi.ureport.in/count/",
    ),
    dict(
        name="Cameroun",
        host="//cameroon.ureport.in/",
        flag="flag_cameroun.png",
        is_static=True,
        count_link="http://cameroon.ureport.in/count/",
    ),
    dict(
        name="CAR",
        host="//centrafrique.ureport.in/",
        flag="flag_car.png",
        is_static=True,
        count_link="http://centrafrique.ureport.in/count/",
    ),
    dict(
        name="Chile",
        host="//chile.ureport.in/",
        flag="flag_chile.png",
        is_static=True,
        count_link="http://chile.ureport.in/count/",
    ),
    dict(
        name="CAR",
        host="//congobrazzaville.ureport.in/",
        flag="flag_congo_brazzaville.png",
        is_static=True,
        count_link="http://congobrazzaville.ureport.in/count/",
    ),
    dict(
        name="Costa Rica",
        host="//costarica.ureport.in/",
        flag="flag_costa_rica.png",
        is_static=True,
        count_link="https://costarica.ureport.in/count/",
    ),
    dict(
        name="Cote d'ivoire",
        host="//cotedivoire.ureport.in/",
        flag="flag_cote_d_ivoire.png",
        is_static=True,
        count_link="http://cotedivoire.ureport.in/count/",
    ),
    dict(
        name="DRC",
        host="//drc.ureport.in/",
        flag="flag_drc.png",
        is_static=True,
        count_link="http://drc.ureport.in/count/",
    ),
    dict(
        name="Ecuador",
        host="//ecuador.ureport.in/",
        flag="flag_ecuador.png",
        is_static=True,
        count_link="http://ecuador.ureport.in/count/",
    ),
    dict(
        name="El Salvador",
        host="//elsalvador.ureport.in/",
        flag="flag_el_salvador.png",
        is_static=True,
        count_link="http://elsalvador.ureport.in/count/",
    ),
    dict(
        name="Eswatini",
        host="//eswatini.ureport.in/",
        flag="flag_eswatini.png",
        is_static=True,
        count_link="http://eswatini.ureport.in/count/",
    ),
    dict(
        name="France",
        host="//france.ureport.in",
        flag="flag_france.png",
        is_static=True,
        count_link="http://france.ureport.in/count/",
    ),
    dict(
        name="FSM",
        host="//fsm.ureport.in",
        flag="flag_fsm.png",
        is_static=True,
        count_link="http://fsm.ureport.in/count/",
    ),
    dict(
        name="Gambia",
        host="//gambia.ureport.in/",
        flag="flag_gambia.png",
        is_static=True,
        count_link="http://gambia.ureport.in/count/",
    ),
    dict(
        name="Ghana",
        host="//ghana.ureport.in/",
        flag="flag_ghana.png",
        is_static=True,
        count_link="http://ghana.ureport.in/count/",
    ),
    dict(
        name="Guatemala",
        host="//guatemala.ureport.in/",
        flag="flag_guatemala.png",
        is_static=True,
        count_link="http://guatemala.ureport.in/count/",
    ),
    dict(
        name="Guinea",
        host="//guinea.ureport.in/",
        flag="flag_guinea.png",
        is_static=True,
        count_link="http://guinea.ureport.in/count/",
    ),
    dict(
        name="Haiti",
        host="//haiti.ureport.in/",
        flag="flag_haiti.png",
        is_static=True,
        count_link="http://haiti.ureport.in/count/",
    ),
    dict(
        name="Honduras",
        host="//honduras.ureport.in",
        flag="flag_honduras.png",
        is_static=True,
        count_link="http://honduras.ureport.in/count/",
    ),
    dict(
        name="India",
        host="//india.ureport.in",
        flag="flag_india.png",
        is_static=True,
        count_link="http://india.ureport.in/count/",
    ),
    dict(
        name="Indonesia",
        host="//indonesia.ureport.in",
        flag="flag_indonesia.png",
        is_static=True,
        count_link="http://indonesia.ureport.in/count/",
    ),
    dict(
        name="Iraq",
        host="//iraq.ureport.in",
        flag="flag_iraq.png",
        is_static=True,
        count_link="http://iraq.ureport.in/count/",
    ),
    dict(
        name="Ireland",
        host="//ireland.ureport.in",
        flag="flag_ireland.png",
        is_static=True,
        count_link="http://ireland.ureport.in/count/",
    ),
    dict(
        name="Jamaica",
        host="//jamaica.ureport.in/",
        flag="flag_jamaica.png",
        is_static=True,
        count_link="http://jamaica.ureport.in/count/",
    ),
    dict(
        name="Jordan",
        host="//jordan.ureport.in/",
        flag="flag_jordan.png",
        is_static=True,
        count_link="http://jordan.ureport.in/count/",
    ),
    dict(
        name="Kiribati",
        host="//kiribati.ureport.in/",
        flag="flag_kiribati.png",
        is_static=True,
        count_link="http://kiribati.ureport.in/count/",
    ),
    dict(
        name="Liberia",
        host="//liberia.ureport.in/",
        flag="flag_liberia.png",
        is_static=True,
        count_link="http://liberia.ureport.in/count/",
    ),
    dict(
        name="Malawi",
        host="//ureport.mw/",
        flag="flag_malawi.png",
        is_static=True,
        count_link="http://ureport.mw/count/",
    ),
    dict(
        name="Malaysia",
        host="//malaysia.ureport.in/",
        flag="flag_malaysia.png",
        is_static=True,
        count_link="http://malaysia.ureport.in/count/",
    ),
    dict(
        name="Mali",
        host="//mali.ureport.in/",
        flag="flag_mali.png",
        is_static=True,
        count_link="http://mali.ureport.in/count/",
    ),
    dict(
        name="Mexico",
        host="//mexico.ureport.in/",
        flag="flag_mexico.png",
        is_static=True,
        count_link="http://mexico.ureport.in/count/",
    ),
    dict(
        name="Moldova",
        host="//moldova.ureport.in",
        flag="flag_moldova.png",
        is_static=True,
        count_link="http://moldova.ureport.in/count/",
    ),
    dict(
        name="Mozambiqui",
        host="//smsbiz.co.mz/",
        flag="flag_mozambique.png",
        is_static=True,
        count_link="http://smsbiz.co.mz/count/",
    ),
    dict(
        name="Myanmar",
        host="//myanmar.ureport.in",
        flag="flag_myanmar.png",
        is_static=True,
        count_link="http://myanmar.ureport.in/count/",
    ),
    dict(
        name="Nigeria",
        host="//nigeria.ureport.in",
        flag="flag_nigeria.png",
        is_static=True,
        count_link="http://nigeria.ureport.in/count/",
    ),
    dict(
        name="Nigeria24x7",
        host="//nigeria24x7.ureport.in",
        flag="flag_nigeria24x7.png",
        is_static=True,
        count_link="http://nigeria24x7.ureport.in/count/",
    ),
    dict(
        name="On the move",
        host="//onthemove.ureport.in",
        flag="flag_on_the_move.png",
        is_static=True,
        count_link="http://onthemove.ureport.in/count/",
    ),
    dict(
        name="Pacific",
        host="//pacific.ureport.in",
        flag="flag_pacific.png",
        is_static=True,
        count_link="http://pacific.ureport.in/count/",
    ),
    dict(
        name="Pakistan",
        host="//ureport.pk",
        flag="flag_pakistan.png",
        is_static=True,
        count_link="http://ureport.pk/count/",
    ),
    dict(
        name="Philippines",
        host="//philippines.ureport.in",
        flag="flag_philippines.png",
        is_static=True,
        count_link="http://philippines.ureport.in/count/",
    ),
    dict(
        name="PNG",
        host="//png.ureport.in",
        flag="flag_png.png",
        is_static=True,
        count_link="http://png.ureport.in/count/",
    ),
    dict(
        name="România",
        host="//romania.ureport.in/",
        flag="flag_romania.png",
        is_static=True,
        count_link="http://romania.ureport.in/count/",
    ),
    dict(
        name="Senegal",
        host="//senegal.ureport.in/",
        flag="flag_senegal.png",
        is_static=True,
        count_link="http://senegal.ureport.in/count/",
    ),
    dict(
        name="Serbia",
        host="//serbia.ureport.in/",
        flag="flag_serbia.png",
        is_static=True,
        count_link="http://serbia.ureport.in/count/",
    ),
    dict(
        name="Sierra Leone",
        host="//sierraleone.ureport.in",
        flag="flag_sierra_leone.png",
        is_static=True,
        count_link="http://sierraleone.ureport.in/count/",
    ),
    dict(
        name="South Africa",
        host="//sa.ureport.in",
        flag="flag_south_africa.png",
        is_static=True,
        count_link="http://sa.ureport.in/count/",
    ),
    dict(
        name="Tanzania",
        host="//tanzania.ureport.in",
        flag="flag_tanzania.png",
        is_static=True,
        count_link="http://tanzania.ureport.in/count/",
    ),
    dict(
        name="Tchad",
        host="//tchad.ureport.in",
        flag="flag_tchad.png",
        is_static=True,
        count_link="http://tchad.ureport.in/count/",
    ),
    dict(
        name="Thailand",
        host="//thailand.ureport.in",
        flag="flag_thailand.png",
        is_static=True,
        count_link="http://thailand.ureport.in/count/",
    ),
    dict(
        name="Trinidad and Tobago",
        host="//tt.ureport.in/",
        flag="flag_trinidad_and_tobago.png",
        is_static=True,
        count_link="http://tt.ureport.in/count/",
    ),
    dict(
        name="Tunisia",
        host="//tunisie.ureport.in",
        flag="flag_tunisia.png",
        is_static=True,
        count_link="http://tunisie.ureport.in/count/",
    ),
    dict(
        name="Uganda",
        host="//ureport.ug",
        flag="flag_uganda.png",
        is_static=True,
        count_link="http://ureport.ug/count/",
    ),
    dict(
        name="Ukraine",
        host="//ukraine.ureport.in",
        flag="flag_ukraine.png",
        is_static=True,
        count_link="http://ukraine.ureport.in/count/",
    ),
    dict(
        name="Uzbekistan",
        host="//uzbekistan.ureport.in",
        flag="flag_uzberkistan.png",
        is_static=True,
        count_link="http://uzbekistan.ureport.in/count/",
    ),
    dict(
        name="Vietnam",
        host="//vietnam.ureport.in",
        flag="flag_vietnam.png",
        is_static=True,
        count_link="http://vietnam.ureport.in/count/",
    ),
    dict(
        name="Western Balkans",
        host="//westernbalkans.ureport.in",
        flag="flag_western_balkans.png",
        is_static=True,
        count_link="http://westernbalkans.ureport.in/count/",
    ),
    dict(
        name="Zambia",
        host="//www.zambiaureport.com/home/",
        flag="flag_zambia.png",
        is_static=True,
        count_link="http://www.zambiaureport.com/count.txt/",
    ),
    dict(
        name="Zimbabwe",
        host="//zimbabwe.ureport.in",
        flag="flag_zimbabwe.png",
        is_static=True,
        count_link="http://zimbabwe.ureport.in/count/",
    ),
]


# -----------------------------------------------------------------------------------
# Old country sites
# -----------------------------------------------------------------------------------
PREVIOUS_ORG_SITES = []  # Not uset anymore

# -----------------------------------------------------------------------------------
# Other sites to get counts for but not display the flag
# -----------------------------------------------------------------------------------
OTHER_ORG_COUNT_SITES = [dict(name="Global", count_link="https://www.ureport.in/count/")]


# -----------------------------------------------------------------------------------
# rest_framework config
# -----------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "PAGE_SIZE": 10,  # Default to 10
    "PAGINATE_BY_PARAM": "page_size",  # Allow client to override, using `?page_size=xxx`.
    "MAX_PAGINATE_BY": 100,
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
}


SWAGGER_SETTINGS = {"SECURITY_DEFINITIONS": {"basic": {"type": "basic"}}}

STORY_WIDGET_URL = "https://ureportapp.ilhasoft.mobi/widget/"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "root": {"level": "WARNING", "handlers": ["console"]},
    "formatters": {"verbose": {"format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s"}},
    "handlers": {
        "console": {"level": "DEBUG", "class": "logging.StreamHandler", "formatter": "verbose"},
        "null": {"class": "logging.NullHandler"},
    },
    "loggers": {
        "pycountry": {"level": "ERROR", "handlers": ["console"], "propagate": False},
        "django.security.DisallowedHost": {"handlers": ["null"], "propagate": False},
        "django.db.backends": {"level": "ERROR", "handlers": ["console"], "propagate": False},
    },
}
