# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
from builtins import *

from .views import ImageCRUDL

urlpatterns = ImageCRUDL().as_urlpatterns()