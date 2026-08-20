# -*- coding: utf-8 -*-

from .views import SyncJobCRUDL

urlpatterns = SyncJobCRUDL().as_urlpatterns()
