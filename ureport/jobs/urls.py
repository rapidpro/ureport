# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from ureport.jobs.views import JobSourceCRUDL

urlpatterns = JobSourceCRUDL().as_urlpatterns()
