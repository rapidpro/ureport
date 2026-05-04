# -*- coding: utf-8 -*-

from .views import PollCRUDL

urlpatterns = PollCRUDL().as_urlpatterns()
