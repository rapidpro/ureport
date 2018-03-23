# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import *

from .views import AdminCRUDL

urlpatterns = AdminCRUDL().as_urlpatterns()