from django.urls import re_path
from django.views.generic import RedirectView

from .views import UserCRUDL

urlpatterns = [
    # the pre-allauth login and logout URLs, still reversed by dash and possibly bookmarked
    re_path(
        r"^login/$",
        RedirectView.as_view(pattern_name="account_login", query_string=True),
        name="users.user_login",
    ),
    re_path(
        r"^logout/$",
        RedirectView.as_view(pattern_name="account_logout", query_string=True),
        name="users.user_logout",
    ),
]

urlpatterns += UserCRUDL().as_urlpatterns()
