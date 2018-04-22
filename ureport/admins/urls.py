from __future__ import absolute_import, unicode_literals

from .views import AdminCRUDL

urlpatterns = AdminCRUDL().as_urlpatterns()
