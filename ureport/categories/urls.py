from .views import *

urlpatterns = CategoryCRUDL().as_urlpatterns()
urlpatterns += CategoryImageCRUDL().as_urlpatterns()
