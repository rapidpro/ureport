from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed


class AssumeHTTPSMiddleware:
    """
    Tells Django every request arrived over https, for when TLS is always terminated in front of the app. Everything
    that keys off the scheme - CSRF origin checks, HSTS, absolute URLs - then works without the app having to trust a
    forwarded header from whatever is in front of it. This has to run before anything that reads the scheme, which is
    why it's first.
    """

    def __init__(self, get_response=None):
        if not settings.SECURE_ASSUME_HTTPS:
            raise MiddlewareNotUsed()

        self.get_response = get_response

    def __call__(self, request):
        request.META["wsgi.url_scheme"] = "https"
        return self.get_response(request)


class CacheControlMiddleware:
    """
    Marks dynamic responses as not to be stored by browsers or shared caches, unless the view set a Cache-Control
    header of its own (e.g. cache_page). Static files are served by whitenoise above this middleware and carry
    their own cache headers.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not response.has_header("Cache-Control"):
            response["Cache-Control"] = "no-store"
        return response
