from django.core.exceptions import DisallowedHost
from dash.orgs.models import Org
from django.template.response import TemplateResponse
from django.conf import settings
import traceback

class SetOrgMiddleware(object):

    def process_request(self, request):
        user = request.user

        host = 'localhost'
        try:
            host = request.get_host()
        except DisallowedHost:
            traceback.print_exc()

        subdomain = None

        # only consider first level subdomain
        if len(host.split('.')) > 1:
            subdomain = host.split('.')[0]

        org = None
        if subdomain:
            orgs = Org.objects.filter(subdomain=subdomain)
            if orgs:
                org = orgs[0]


        # no org and not org choosing page? display our chooser page
        if not org and request.path.find('/manage/org') != 0 and request.path.find('/users/') != 0:
            orgs = Org.objects.filter(is_active=True)

            # populate a 'host' attribute on each org so we can link off to them
            for org in orgs:
                org.host = settings.SITE_HOST_PATTERN % org.subdomain

            return TemplateResponse(request, 'public/org_chooser.haml', dict(orgs=orgs))

        else:
            if not user.is_anonymous():
                user.set_org(org)

            request.org = org

