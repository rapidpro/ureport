"""
Server hooks for gunicorn, loaded with -c python:ureport.gunicorn_conf
"""

import os

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from ureport import __version__


def on_starting(server):
    # the master never loads Django, so its own errors (workers OOM-killed, timed out, failing to boot) only reach
    # Sentry if it initializes the SDK itself - workers fork after this and re-initialize from Django settings
    if dsn := os.environ.get("SENTRY_DSN"):
        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT"),
            release=__version__,
            integrations=[LoggingIntegration()],
            # auto-enabled integrations such as Django's would be set up here and not again in the workers
            auto_enabling_integrations=False,
            traces_sample_rate=0,
        )
