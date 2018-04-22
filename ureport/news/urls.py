from .views import NewsItemCRUDL, VideoCRUDL

urlpatterns = NewsItemCRUDL().as_urlpatterns()
urlpatterns += VideoCRUDL().as_urlpatterns()
