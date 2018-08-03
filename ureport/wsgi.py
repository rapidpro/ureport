# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import os

from django.core.wsgi import get_wsgi_application

"""
WSGI config for foo project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/dev/howto/deployment/wsgi/
"""


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ureport.settings")
application = get_wsgi_application()
