from __future__ import absolute_import, unicode_literals

from .views import OrgExtCRUDL

urlpatterns = OrgExtCRUDL().as_urlpatterns()