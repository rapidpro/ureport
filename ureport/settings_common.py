from __future__ import absolute_import
import sys
from django.utils.translation import ugettext_lazy as _

#-----------------------------------------------------------------------------------
# Sets TESTING to True if this configuration is read during a unit test
#-----------------------------------------------------------------------------------
TESTING = sys.argv[1:2] == ['test']

DEBUG = True

ADMINS = (
    ('Nyaruka', 'code@nyaruka.com'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3', # Add 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'dash.sqlite',                      # Or path to database file if using sqlite3.
        'USER': '',                      # Not used with sqlite3.
        'PASSWORD': '',                  # Not used with sqlite3.
        'HOST': '',                      # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
    }
}

# set the mail settings, we send throught gmail
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_HOST_USER = 'server@nyaruka.com'
DEFAULT_FROM_EMAIL = 'server@nyaruka.com'
EMAIL_HOST_PASSWORD = 'NOTREAL'
EMAIL_USE_TLS = True

EMPTY_SUBDOMAIN_HOST = 'http://localhost:8000'
SITE_API_HOST = 'http://localhost:8001'
SITE_API_USER_AGENT = 'ureport/0.1'
HOSTNAME = 'localhost:8000'
SITE_CHOOSER_TEMPLATE = 'public/org_chooser.haml'
SITE_CHOOSER_URL_NAME = 'public.home'


SITE_BACKEND = 'ureport.backend.rapidpro.RapidProBackend'


# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone
TIME_ZONE = 'GMT'
USER_TIME_ZONE = 'GMT'
USE_TZ = True

MODELTRANSLATION_TRANSLATION_REGISTRY = "translation"

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en'

# Available languages for translation
LANGUAGES = (('en', "English"), ('fr', "French"), ('es', "Spanish"), ('ar', "Arabic"), ('pt', "Portuguese"),
             ('pt-br', "Brazilian Portuguese"), ('uk', "Ukrainian"), ('my', "Burmese"), ('id', "Indonesian"))
DEFAULT_LANGUAGE = "en"
RTL_LANGUAGES = ['ar']

ORG_LANG_MAP = {
    'ar': 'ar_AR',
    'en': 'en_US',
    'es': 'es_ES',
    'fr': 'fr_FR',
    'id': 'id_ID',
    'my': 'my_MM',
    'pt': 'pt_PT',
    'pt-br': 'pt_BR',
    'uk': 'uk_UA'
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
STATIC_URL = '/sitestatic/'
COMPRESS_URL = '/sitestatic/'

# URL prefix for admin static files -- CSS, JavaScript and images.
# Make sure to use a trailing slash.
# Examples: "http://foo.com/static/admin/", "/static/admin/".
ADMIN_MEDIA_PREFIX = '/sitestatic/admin/'

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
)

COMPRESS_PRECOMPILERS = (
    ('text/coffeescript', 'coffee --compile --stdio'),
    ('text/less', 'lessc {infile} {outfile}'),
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'bangbangrootplaydeadn7#^+-u-#1wm=y3a$-#^jps5tihx5v_@-_(kxumq_$+$5r)bxo'

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'dash.orgs.middleware.SetOrgMiddleware',
)

ROOT_URLCONF = 'ureport.urls'

from django.forms import Textarea

ORG_CONFIG_FIELDS =[ dict(name='is_on_landing_page', field=dict(help_text=_("Whether this org should be show on the landing page"), required=False), superuser_only=True),
                     dict(name='shortcode', field=dict(help_text=_("The shortcode that users will use to contact U-Report locally"), required=True)),
                     dict(name='join_text', field=dict(help_text=_("The short text used to direct visitors to join U-Report"), required=False)),
                     dict(name='join_fg_color', field=dict(help_text=_("The color used to draw the text on the join bar"), required=False), superuser_only=True),
                     dict(name='join_bg_color', field=dict(help_text=_("The color used to draw the background on the join bar"), required=False), superuser_only=True),
                     dict(name='primary_color', field=dict(help_text=_("The primary color for styling for this organization"), required=False), superuser_only=True),
                     dict(name='secondary_color', field=dict(help_text=_("The secondary color for styling for this organization"), required=False), superuser_only=True),
                     dict(name='bg_color', field=dict(help_text=_("The background color for the site"), required=False), superuser_only=True),
                     dict(name='colors', field=dict(help_text=_("Up to 6 colors for styling charts, use comma between colors"), required=False), superuser_only=True),
                     dict(name='google_tracking_id', field=dict(help_text=_("The Google Analytics Tracking ID for this organization"), required=False)),
                     dict(name='youtube_channel_url', field=dict(help_text=_("The URL to the Youtube channel for this organization"), required=False)),
                     dict(name='facebook_page_url', field=dict(help_text=_("The URL to the Facebook page for this organization"), required=False)),
                     dict(name='facebook_page_id', field=dict(help_text=_("The integer id to the Facebook page for this organization (optional)"), required=False)),
                     dict(name='facebook_app_id', field=dict(help_text=_("The integer id to the Facebook app for this organization's chat app (optional)"), required=False)),
                     dict(name='facebook_pixel_id', field=dict(help_text=_("The id of the Facebook Pixel for this organization (optional)"), required=False)),
                     dict(name='instagram_username', field=dict(help_text=_("The Instagram username for this organization"), required=False)),
                     dict(name='instagram_lightwidget_id', field=dict(help_text=_("The Instagram widget id from lightwidget.com"), required=False)),
                     dict(name='twitter_handle', field=dict(help_text=_("The Twitter handle for this organization"), required=False)),
                     dict(name='twitter_search_widget', field=dict(help_text=_("The Twitter widget used for searching"), required=False)),
                     dict(name='reporter_group', field=dict(help_text=_("The name of txbhe Contact Group that contains registered reporters")), superuser_only=True),
                     dict(name='born_label', field=dict(help_text=_("The label of the Contact Field that contains the birth date of reporters")), superuser_only=True),
                     dict(name='gender_label', field=dict(help_text=_("The label of the Contact Field that contains the gender of reporters")), superuser_only=True),
                     dict(name='occupation_label', field=dict(help_text=_("The label of the Contact Field that contains the occupation of reporters"), required=False), superuser_only=True),
                     dict(name='registration_label', field=dict(help_text=_("The label of the Contact Field that contains the registration date of reporters")), superuser_only=True),
                     dict(name='state_label', field=dict(help_text=_("The label of the Contact Field that contains the State of reporters"), required=False), superuser_only=True),
                     dict(name='district_label', field=dict(help_text=_("The label of the Contact Field that contains the District of reporters"), required=False), superuser_only=True),
                     dict(name='ward_label', field=dict(help_text=_("The label of the Contact Field that contains the Ward of reporters"), required=False), superuser_only=True),
                     dict(name='male_label', field=dict(help_text=_("The label assigned to U-Reporters that are Male.")), superuser_only=True),
                     dict(name='female_label', field=dict(help_text=_("The label assigned to U-Reporters that are Female.")), superuser_only=True),
                     dict(name='has_jobs', field=dict(help_text=_("If there are jobs to be shown on the public site"), required=False)),
                     dict(name='is_global', field=dict(help_text=_("If this org if for global data. e.g: It shows a world map instead of a country map."), required=False), superuser_only=True),
                     dict(name='iso_code', field=dict(help_text=_("The alpha-3 ISO code of the organization so that it appears the stories widget U-Report App. Example: BRA, NIG, CMR (Use GLOBAL if U-Report is Global)."), required=False)),
                     dict(name='custom_html', field=dict(help_text=_("If you need to include some custom HTML codes in you org pages, like custom analytics code snippets"), required=False, widget=Textarea))]
#                     dict(name='featured_state', field=dict(help_text=_("Choose the featured State of reporters shown on the home page")))]
INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',


    # mo-betta permission management
    'guardian',

    # the django admin
    'django.contrib.admin',


    # compress our CSS and js
    'compressor',

    # thumbnail
    'sorl.thumbnail',

    # smartmin
    'smartmin',

    # import tasks
    'smartmin.csv_imports',

    # smartmin users
    'smartmin.users',

    "hamlpy",

    # dash apps
    'dash.orgs',
    'dash.dashblocks',
    'dash.stories',
    'dash.utils',
    'dash.categories',

    # ureport apps
    'ureport.admins',
    'ureport.api',
    'ureport.assets',
    'ureport.contacts',
    'ureport.countries',
    'ureport.jobs',
    'ureport.locations',
    'ureport.news',
    'ureport.polls',

    'django_countries',
    'rest_framework',
    'rest_framework_swagger',
)

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class':'logging.StreamHandler',
            'formatter': 'verbose'
        }
    },
    'loggers': {
        'httprouterthread': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
        },
    }
}

#-----------------------------------------------------------------------------------
# Directory Configuration
#-----------------------------------------------------------------------------------
import os

PROJECT_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)))
RESOURCES_DIR = os.path.join(PROJECT_DIR, '../resources')

LOCALE_PATHS = (os.path.join(PROJECT_DIR, '../locale'),)
FIXTURE_DIRS = (os.path.join(PROJECT_DIR, '../fixtures'),)
TESTFILES_DIR = os.path.join(PROJECT_DIR, '../testfiles')
STATICFILES_DIRS = (os.path.join(PROJECT_DIR, '../static'), os.path.join(PROJECT_DIR, '../media'), )
STATIC_ROOT = os.path.join(PROJECT_DIR, '../sitestatic')
MEDIA_ROOT = os.path.join(PROJECT_DIR, '../media')
MEDIA_URL = "/media/"


# -----------------------------------------------------------------------------------
# Templates Configuration
# -----------------------------------------------------------------------------------

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(PROJECT_DIR, '../templates')],

        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.core.context_processors.debug',
                'django.core.context_processors.i18n',
                'django.core.context_processors.media',
                'django.core.context_processors.static',
                'django.contrib.messages.context_processors.messages',
                'django.core.context_processors.request',
                'dash.orgs.context_processors.user_group_perms_processor',
                'dash.orgs.context_processors.set_org_processor',
                'ureport.assets.context_processors.set_assets_processor',
                'ureport.public.context_processors.set_has_better_domain',
                'ureport.public.context_processors.set_is_iorg',
                'ureport.public.context_processors.set_org_lang_params',
                'ureport.public.context_processors.set_story_widget_url',
            ],
            'loaders': [
                'dash.utils.haml.HamlFilesystemLoader',
                'dash.utils.haml.HamlAppDirectoriesLoader',
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',

            ],
            'debug': False if TESTING else DEBUG
        }
    }
]


#-----------------------------------------------------------------------------------
# Permission Management
#-----------------------------------------------------------------------------------

# this lets us easily create new permissions across our objects
PERMISSIONS = {
    '*': ('create', # can create an object
          'read',   # can read an object, viewing it's details
          'update', # can update an object
          'delete', # can delete an object,
          'list'),  # can view a list of the objects

    'dashblocks.dashblock': ('html', ),
    'orgs.org': ('choose', 'edit', 'home', 'manage_accounts', 'create_login', 'join', 'refresh_cache'),
    'polls.poll': ('questions', 'responses', 'images', 'pull_refresh', 'poll_date'),
    'stories.story': ('html', 'images'),

}

# assigns the permissions that each group should have
GROUP_PERMISSIONS = {
    "Administrators": (
        'assets.image.*',
        'categories.category.*',
        'categories.categoryimage.*',
        'dashblocks.dashblock.*',
        'dashblocks.dashblocktype.*',
        'jobs.jobsource.*',
        'news.newsitem.*',
        'news.video.*',
        'orgs.org_edit',
        'orgs.org_home',
        'orgs.org_manage_accounts',
        'orgs.org_profile',
        'polls.poll.*',
        'polls.pollcategory.*',
        'polls.pollimage.*',
        'polls.featuredresponse.*',
        'stories.story.*',
        'stories.storyimage.*',
        'users.user_profile',
    ),
    "Editors": (
        'categories.category.*',
        'categories.categoryimage.*',
        'dashblocks.dashblock.*',
        'dashblocks.dashblocktype.*',
        'jobs.jobsource.*',
        'news.newsitem.*',
        'news.video.*',
        'orgs.org_home',
        'orgs.org_profile',
        'polls.poll.*',
        'polls.pollcategory.*',
        'polls.pollimage.*',
        'polls.featuredresponse.*',
        'stories.story.*',
        'stories.storyimage.*',
        'users.user_profile',
    ),
    "Global": (
        'countries.countryalias.*',
    )
}

#-----------------------------------------------------------------------------------
# Login / Logout
#-----------------------------------------------------------------------------------
LOGIN_URL = "/users/login/"
LOGOUT_URL = "/users/logout/"
LOGIN_REDIRECT_URL = "/manage/org/choose/"
LOGOUT_REDIRECT_URL = "/"

#-----------------------------------------------------------------------------------
# Guardian Configuration
#-----------------------------------------------------------------------------------

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',
)

ANONYMOUS_USER_NAME = 'AnonymousUser'

#-----------------------------------------------------------------------------------
# Redis Configuration
#-----------------------------------------------------------------------------------

# by default, celery doesn't have any timeout on our redis connections, this fixes that
BROKER_TRANSPORT_OPTIONS = {'socket_timeout': 5}

BROKER_BACKEND = 'redis'
BROKER_HOST = 'localhost'
BROKER_PORT = 6379
BROKER_VHOST = '1'

BROKER_URL = '%s://%s:%s/%s' % (BROKER_BACKEND, BROKER_HOST, BROKER_PORT, BROKER_VHOST)

CELERY_RESULT_BACKEND = BROKER_URL


CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': BROKER_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

if 'test' in sys.argv:
    CACHES['default']['LOCATION'] = 'redis://127.0.0.1:6379/15'

#-----------------------------------------------------------------------------------
# Django-Nose config
#-----------------------------------------------------------------------------------

TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'
SOUTH_TESTS_MIGRATE = False

#-----------------------------------------------------------------------------------
# SMS Configs
#-----------------------------------------------------------------------------------

RAPIDSMS_TABS = []
SMS_APPS = [ 'mileage' ]

# change this to your specific backend for your install
DEFAULT_BACKEND = "console"

# change this to the country code for your install
DEFAULT_COUNTRY_CODE = "250"

#-----------------------------------------------------------------------------------
# Debug Toolbar
#-----------------------------------------------------------------------------------

INTERNAL_IPS = ('127.0.0.1',)

#-----------------------------------------------------------------------------------
# Crontab Settings
#-----------------------------------------------------------------------------------

from datetime import timedelta
from celery.schedules import crontab

CELERY_TIMEZONE = 'UTC'

CELERYBEAT_SCHEDULE = {
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
    'contact-pull': {
        'task': 'dash.orgs.tasks.trigger_org_task',
        'schedule': crontab(minute=[0, 10, 20, 30, 40, 50]),
        'args': ('ureport.contacts.tasks.pull_contacts',)
    },
    'backfill-poll-results': {
        'task': 'dash.orgs.tasks.trigger_org_task',
        'schedule': timedelta(minutes=10),
        'relative': True,
        'args': ('ureport.polls.tasks.backfill_poll_results', 'sync')
    },
    'results-pull-main-poll':  {
        'task': 'dash.orgs.tasks.trigger_org_task',
        'schedule': crontab(minute=[5, 25, 45]),
        'args': ('ureport.polls.tasks.pull_results_main_poll', 'sync')
    },
    'results-pull-recent-other-polls': {
        'task': 'dash.orgs.tasks.trigger_org_task',
        "schedule": timedelta(hours=1),
        "relative": True,
        'args': ('ureport.polls.tasks.pull_results_recent_other_polls', 'sync')
    },
    'results-pull-brick-polls':  {
        'task': 'dash.orgs.tasks.trigger_org_task',
        "schedule": timedelta(hours=48),
        "relative": True,
        'args': ('ureport.polls.tasks.pull_results_brick_polls', 'sync')
    },
    'results-pull-other-polls':  {
        'task': 'dash.orgs.tasks.trigger_org_task',
        "schedule": timedelta(hours=48),
        "relative": True,
        'args': ('ureport.polls.tasks.pull_results_other_polls', 'sync')
    },
}

#-----------------------------------------------------------------------------------
# U-Report Defaults
#-----------------------------------------------------------------------------------
UREPORT_DEFAULT_PRIMARY_COLOR = '#FFD100'
UREPORT_DEFAULT_SECONDARY_COLOR = '#1F49BF'


#-----------------------------------------------------------------------------------
# non org urls
#-----------------------------------------------------------------------------------
SITE_ALLOW_NO_ORG = ('public.countries',)


#-----------------------------------------------------------------------------------
# Old country sites
#-----------------------------------------------------------------------------------
PREVIOUS_ORG_SITES = [
    dict(
        name="Brazil",
        host="http://ureportbrasil.org.br/",
        flag="flag_br.png",
        is_static=True,
        count_link="http://ureportbrasil.org.br/count/",
    ),
    dict(
        name="Guatemala",
        host="http://guatemala.ureport.in/",
        flag="flag_gt.png",
        is_static=True,
        count_link="http://guatemala.ureport.in/count/",
    ),
    dict(
        name="France",
        host="http://france.ureport.in",
        flag="flag_fr.png",
        is_static=True,
        count_link="http://france.ureport.in/count/",
    ),
    dict(
        name="Ireland",
        host="http://ireland.ureport.in",
        flag="flag_ir.png",
        is_static=True,
        count_link="http://ireland.ureport.in/count/",
    ),
    dict(
        name="Syria",
        host="http://syria.ureport.in",
        flag="flag_sy.png",
        is_static=True,
        count_link="http://syria.ureport.in/count/",
    ),
    dict(
        name="Thailand",
        host="http://thailand.ureport.in",
        flag="flag_th.png",
        is_static=True,
        count_link="http://thailand.ureport.in/count/",
    ),
    dict(
        name='United Kingdom',
        host="http://uk.ureport.in",
        flag="flag_uk.png",
        is_static=True,
        count_link="http://uk.ureport.in/count/",
    ),
    dict(
        name="Zambia",
        host="http://www.zambiaureport.org/home/",
        flag="flag_zm.png",
        is_static=True,
        count_link='http://www.zambiaureport.org/count.txt/',
    ),
]


#-----------------------------------------------------------------------------------
# rest_framework config
#-----------------------------------------------------------------------------------
REST_FRAMEWORK = {
    'PAGINATE_BY': 10,                 # Default to 10
    'PAGINATE_BY_PARAM': 'page_size',  # Allow client to override, using `?page_size=xxx`.
    'MAX_PAGINATE_BY': 100,
}

SWAGGER_SETTINGS = {
    'api_version': '0.1',
    'api_path': '/',
    'enabled_methods': [
        'get'
    ],
}

STORY_WIDGET_URL = 'https://ureportapp.ilhasoft.mobi/widget/'
