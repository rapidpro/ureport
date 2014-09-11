from .views import PollCRUDL, FeaturedResponseCRUDL

urlpatterns = PollCRUDL().as_urlpatterns()
urlpatterns += FeaturedResponseCRUDL().as_urlpatterns()
