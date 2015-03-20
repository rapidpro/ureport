from django.conf.urls import patterns
from ureport.jobs.views import JobSourceCRUDL


urlpatterns = JobSourceCRUDL().as_urlpatterns()
