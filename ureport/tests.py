# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import override_settings
from django.utils import timezone
from smartmin.tests import SmartminTest
from django.contrib.auth.models import User
from dash.orgs.middleware import SetOrgMiddleware
from mock import Mock, patch
from dash.orgs.models import Org
from django.http.request import HttpRequest

from ureport.backend.rapidpro import RapidProBackend
from ureport.jobs.models import JobSource
from ureport.polls.models import Poll
from ureport.public.views import IndexView
from temba_client.v1 import TembaClient
from temba_client.v1.types import Result, Flow, Group, Boundary as TembaBoundary, Field as TembaContactField
from temba_client.v1.types import Contact as TembaContact, Group as TembaGroup
from temba_client.v1.types import Geometry as TembaGeometry, FlowDefinition


class MockTembaClient(TembaClient):

    def get_boundaries(self, pager=None):
        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=['COORDINATES'])
        return [TembaBoundary.create(boundary='R12345', name='Nigeria', parent=None, level=0, geometry=geometry),
                TembaBoundary.create(boundary='R23456', name='Lagos', parent="R12345", level=1, geometry=geometry)]

    def get_fields(self, pager=None):
        return [TembaContactField.create(key='occupation', label='Activité', value_type='T')]

    def get_contacts(self, uuids=None, urns=None, groups=None, after=None, before=None, pager=None):
        return [TembaContact.create(
                uuid='000-001', name="Ann", urns=['tel:1234'], groups=['000-002'],
                fields=dict(state="Lagos", lga="Oyo", gender='Female', born="1990"),
                language='eng', modified_on=timezone.now())]

    def get_groups(self, uuids=None, name=None, pager=None):
        return Group.deserialize_list([dict(uuid="uuid-8", name=name, size=120)])

    def get_results(self, ruleset_id=None, contact_field=None, segment=None):
        return Result.deserialize_list([dict(open_ended=False,
                                                 set=3462,
                                                 unset=3694,
                                                 categories=[dict(count=2210, label='Yes'),
                                                             dict(count=1252, label='No')],
                                                 label='All')])

    def get_flows(self, uuids=None, archived=None, labels=None, before=None, after=None, pager=None):
        return Flow.deserialize_list([dict(runs=300,
                                           completed_runs=120,
                                           name='Flow 1',
                                           uuid='uuid-25',
                                           participants=None,
                                           labels="",
                                           archived=False,
                                           created_on="2015-04-08T12:48:44.320Z",
                                           rulesets=[dict(node='uuid-8435', id="8435", response_type="C",
                                                          label='Does your community have power')]
                                           )])

    def get_flow(self, uuid):
        return Flow.deserialize(dict(runs=300,
                                     completed_runs=120,
                                     name='Flow 1',
                                     uuid='uuid-25',
                                     participants=None,
                                     labels="",
                                     archived=False,
                                     created_on="2015-04-08T12:48:44.320Z",
                                     rulesets=[dict(node='uuid-8435', id="8435", response_type="C",
                                                    label='Does your community have power')]
                                     ))

    def get_flow_definition(self, uuid):
        return FlowDefinition.deserialize(dict(metadata=dict(), version=8, base_language='eng', flow_type='',
                                               action_sets=[], rule_sets=[dict(uuid='ruleset-1-uuid', label='ruleset1',
                                                                               ruleset_type='wait_message',
                                                                               rules=[dict(uuid='rule-1-uuid',
                                                                                           category=dict(eng='Blue')
                                                                                           )])], entry=''))


class TestBackend(RapidProBackend):
    """
    TODO once all backend functionality actually goes through get_backend() this can become a stub
    """
    pass


@override_settings(SITE_BACKEND='ureport.tests.TestBackend')
class DashTest(SmartminTest):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username="super", email="super@user.com", password="super")

        self.admin = self.create_user("Administrator")

    def create_org(self, subdomain, user):

        email = subdomain + "@user.com"
        first_name = subdomain + "_First"
        last_name = subdomain + "_Last"
        name = subdomain

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

    def create_poll(self, org, title, flow_uuid, category, user, featured=False):
        now = timezone.now()
        poll = Poll.objects.create(flow_uuid=flow_uuid,
                                   title=title,
                                   category=category,
                                   is_featured=featured,
                                   org=org,
                                   poll_date=now,
                                   created_by=user,
                                   modified_by=user)

        return poll


class UreportJobsTest(DashTest):
    FB_SOURCE = 'http://www.facebook.com/%s'
    TW_SOURCE = 'http://twitter.com/%s'
    RSS_SOURCE = 'http://dummy.rss.com/%s.xml'

    def create_fb_job_source(self, org, fb_identifier):
        return JobSource.objects.create(source_url=UreportJobsTest.FB_SOURCE % fb_identifier,
                                        source_type=JobSource.FACEBOOK,
                                        org=org,
                                        created_by=self.admin,
                                        modified_by=self.admin)

    def create_tw_job_source(self, org, tw_identifier):
        return JobSource.objects.create(source_url=UreportJobsTest.TW_SOURCE % tw_identifier,
                                        widget_id='WIDGETID_%s' % tw_identifier,
                                        source_type=JobSource.TWITTER,
                                        org=org,
                                        created_by=self.admin,
                                        modified_by=self.admin)

    def create_rss_job_source(self, org, rss_identifier):
        return JobSource.objects.create(source_url=UreportJobsTest.RSS_SOURCE % rss_identifier,
                                        source_type=JobSource.RSS,
                                        org=org,
                                        created_by=self.admin,
                                        modified_by=self.admin)


class SetOrgMiddlewareTest(DashTest):

    def setUp(self):
        super(SetOrgMiddlewareTest, self).setUp()

        self.middleware = SetOrgMiddleware()
        self.request = Mock(spec=HttpRequest)
        self.request.user = User.objects.get(pk=-1)
        self.request.path = '/'
        self.request.get_host.return_value="ureport.io"
        self.request.META = dict(HTTP_HOST=None)

    def test_process_request_without_org(self):
        response = self.middleware.process_request(self.request)
        self.assertEqual(response, None)
        self.assertEqual(self.request.org, None)

    def test_process_request_with_org(self):

        ug_org = self.create_org('uganda', self.admin)
        ug_dash_url = ug_org.subdomain + ".ureport.io"
        self.request.get_host.return_value = ug_dash_url

        response = self.middleware.process_request(self.request)
        self.assertEqual(response, None)
        self.assertEqual(self.request.org, ug_org)

        self.request.user = self.admin
        response = self.middleware.process_request(self.request)
        self.assertEqual(response, None)
        self.assertEqual(self.request.org, ug_org)
        self.assertEquals(self.request.user.get_org(), ug_org)

        # test invalid subdomain
        wrong_subdomain_url = "blabla.ureport.io"
        self.request.get_host.return_value=wrong_subdomain_url
        response = self.middleware.process_request(self.request)
        self.assertEqual(response, None)
        self.assertEqual(self.request.org, None)

    def test_process_view(self):
        with patch('django.core.urlresolvers.ResolverMatch') as resolver_mock:
            resolver_mock.url_name.return_value = "public.index"

            self.request.resolver_match = resolver_mock

            ug_org = self.create_org('uganda', self.admin)
            ug_dash_url = ug_org.subdomain + ".ureport.io"
            self.request.get_host.return_value=ug_dash_url

            # test invalid subdomain
            wrong_subdomain_url = "blabla.ureport.io"
            self.request.get_host.return_value=wrong_subdomain_url
            self.request.org = None
            response = self.middleware.process_view(self.request, IndexView.as_view(), [], dict())
            self.assertEquals(response.status_code, 302)
            self.assertEquals(response.url, reverse(settings.SITE_CHOOSER_URL_NAME))
            self.assertEqual(self.request.org, None)
            self.assertEquals(self.request.user.get_org(), None)

            rw_org = self.create_org('rwanda', self.admin)
            wrong_subdomain_url = "blabla.ureport.io"
            self.request.get_host.return_value=wrong_subdomain_url
            response = self.middleware.process_view(self.request, IndexView.as_view(), [], dict())
            self.assertEquals(response.status_code, 302)
            self.assertEquals(response.url, reverse(settings.SITE_CHOOSER_URL_NAME))
