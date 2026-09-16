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
