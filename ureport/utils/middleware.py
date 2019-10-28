from django.http import HttpResponseRedirect


class CheckVersionMiddleware:
    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):

        new_design = False
        org = request.org
        if org:
            new_design = org.get_config("common.has_new_design", False)

        path = request.get_full_path_info()
        if (
            new_design
            and not path.startswith("/v2/")
            and not path.startswith("/v1/")
            and not path.startswith("/home/")
            and not path.startswith("/media/")
            and not path.startswith("/api/")
            and not path.startswith("/count")
            and not path.startswith("/status")
            and not path.startswith("/sitestatic")
        ):
            return HttpResponseRedirect(f"/v2{path}")

        response = self.get_response(request)
        return response

    def process_template_response(self, request, response):
        if request.path.startswith("/v2/"):
            current_t_names = response.template_name
            response.template_name = [f"v2/{elt}" if not elt.startswith("v2/") else elt for elt in current_t_names]
        return response
