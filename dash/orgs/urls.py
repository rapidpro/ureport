from .views import *

urlpatterns = OrgCRUDL().as_urlpatterns()
urlpatterns += OrgBackgroundCRUDL().as_urlpatterns()
