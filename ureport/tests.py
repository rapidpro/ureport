from smartmin.tests import SmartminTest
from django.contrib.auth.models import User, Group
from dash.orgs.middleware import SetOrgMiddleware
from mock import Mock
from django.core.urlresolvers import reverse
from dash.orgs.models import Org
from django.http.request import HttpRequest

class DashTest(SmartminTest):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username="super", email="super@user.com", password="super")

        self.admin = self.create_user("Administrator")

    def create_org(self, subdomain, user):

        email = subdomain + "@user.com"
        first_name = subdomain + "_First"
        last_name = subdomain + "_Last"
        name = subdomain.upper()

        orgs = Org.objects.filter(subdomain=subdomain)
        if orgs:
            org =orgs[0]
            org.name = name
            org.save()
        else:
            org = Org.objects.create(subdomain=subdomain, name=name, created_by=user, modified_by=user)

        org.administrators.add(user)

        self.assertEquals(Org.objects.filter(subdomain=subdomain).count(), 1)
        return Org.objects.get(subdomain=subdomain)


class SetOrgMiddlewareTest(DashTest):

    def setUp(self):
        super(SetOrgMiddlewareTest, self).setUp()

        self.middleware = SetOrgMiddleware()
        self.request = Mock(spec=HttpRequest)
        self.request.user = User.objects.get(pk=-1)
        self.request.get_host.return_value="ureport.io"
        self.request.META = dict(HTTP_HOST=None)

    def test_process_request_without_org(self):
        self.assertEqual(self.middleware.process_request(self.request), None)
        self.assertEqual(self.request.org, None)

    def test_process_request_with_org(self):

        ug_org = self.create_org('uganda', self.admin)
        ug_dash_url = ug_org.subdomain + ".ureport.io"
        self.request.get_host.return_value=ug_dash_url

        self.assertEqual(self.middleware.process_request(self.request), None)
        self.assertEqual(self.request.org, ug_org)

        self.request.user = self.admin
        self.assertEqual(self.middleware.process_request(self.request), None)
        self.assertEqual(self.request.org, ug_org)
        self.assertEquals(self.request.user.get_org(), ug_org)

        # test invalid subdomain
        wrong_subdomain_url = "blabla.ureport.io"
        self.request.get_host.return_value=wrong_subdomain_url
        self.assertEqual(self.middleware.process_request(self.request), None)
        self.assertEqual(self.request.org, None)
        self.assertEquals(self.request.user.get_org(), None)
