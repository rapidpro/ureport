from .views import *

urlpatterns = DashBlockCRUDL().as_urlpatterns()
urlpatterns += DashBlockTypeCRUDL().as_urlpatterns()
urlpatterns += DashBlockImageCRUDL().as_urlpatterns()
