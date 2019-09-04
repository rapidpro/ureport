class CheckVersionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_template_response(self, request, response):
        if request.path.startswith("/v2/"):
            current_t_names = response.template_name
            response.template_name = [f"v2/{elt}" if not elt.startswith("v2/") else elt for elt in current_t_names]
        return response
