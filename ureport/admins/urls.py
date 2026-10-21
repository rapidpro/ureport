# -*- coding: utf-8 -*-

from dash.dashblocks.views import DashBlockImageCRUDL, DashBlockTypeCRUDL

from .views import AdminCRUDL, DashBlockCRUDL

urlpatterns = AdminCRUDL().as_urlpatterns()

# replaces dash.dashblocks.urls so that custom page links are validated
urlpatterns += DashBlockTypeCRUDL().as_urlpatterns()
urlpatterns += DashBlockCRUDL().as_urlpatterns()
urlpatterns += DashBlockImageCRUDL().as_urlpatterns()
