# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from .views import PollCRUDL

urlpatterns = PollCRUDL().as_urlpatterns()
