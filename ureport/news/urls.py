from .views import *

urlpatterns = NewsItemCRUDL().as_urlpatterns()
urlpatterns += VideoCRUDL().as_urlpatterns()
