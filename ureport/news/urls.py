# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals


from .views import NewsItemCRUDL, VideoCRUDL


urlpatterns = NewsItemCRUDL().as_urlpatterns()
urlpatterns += VideoCRUDL().as_urlpatterns()
