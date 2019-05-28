# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json

import pytz
from dash.orgs.middleware import SetOrgMiddleware
from dash.orgs.models import Org
from dash.test import DashTest
from dash.utils import random_string
from mock import Mock, patch
from smartmin.tests import SmartminTest
from temba_client.v2 import TembaClient
from temba_client.v2.types import (
    Contact as TembaContact,
    Export as TembaExport,
    Field as TembaContactField,
    Flow,
    Group,
)

from django.conf import settings
from django.contrib.auth.models import User
from django.http.request import HttpRequest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_text

from ureport.backend.rapidpro import RapidProBackend
from ureport.jobs.models import JobSource
from ureport.polls.models import Poll
from ureport.public.views import IndexView


class MockTembaClient(TembaClient):
    def get_fields(self, pager=None):
        return [TembaContactField.create(key="occupation", label="Activité", value_type="T")]

    def get_contacts(self, uuids=None, urns=None, groups=None, after=None, before=None, pager=None):
        return [
            TembaContact.create(
                uuid="000-001",
                name="Ann",
                urns=["tel:1234"],
                groups=["000-002"],
                fields=dict(state="Lagos", lga="Oyo", gender="Female", born="1990"),
                language="eng",
                modified_on=timezone.now(),
            )
        ]

    def get_groups(self, uuids=None, name=None, pager=None):
        return Group.deserialize_list([dict(uuid="uuid-8", name=name, size=120)])

    def get_flows(self, uuids=None, archived=None, labels=None, before=None, after=None, pager=None):
        return Flow.deserialize_list(
            [
                dict(
                    runs=300,
                    completed_runs=120,
                    name="Flow 1",
                    uuid="uuid-25",
                    participants=None,
                    labels="",
                    archived=False,
                    expires=720,
                    created_on="2015-04-08T12:48:44.320Z",
                    results=[
                        dict(
                            key="color",
                            name="Color",
                            categories=["Orange", "Blue", "Other", "Nothing"],
                            node_uuids=["b16fe2a9-8960-47e7-982a-8d6935888b39"],
                        )
                    ],
                    rulesets=[
                        dict(node="uuid-8435", id="8435", response_type="C", label="Does your community have power")
                    ],
                )
            ]
        )

    def get_definitions(self, flows=(), campaigns=(), dependencies=None):
        return TembaExport.deserialize(
            dict(
                campaigns=[],
                triggers=[],
                version=10,
                flows=[
                    dict(metadata=dict(uuid="abcdefg")),
                    dict(
                        metadata=dict(uuid="uuid-1"),
                        version=8,
                        base_language="eng",
                        flow_type="F",
                        action_sets=[],
                        rule_sets=[
                            dict(
                                uuid="ruleset-1-uuid",
                                label="ruleset1",
                                ruleset_type="wait_message",
                                rules=[dict(uuid="rule-1-uuid", category=dict(eng="Blue"))],
                            )
                        ],
                        entry="",
                    ),
                ],
            )
        )


class TestBackend(RapidProBackend):
    """
    TODO once all backend functionality actually goes through get_backend() this can become a stub
    """

    pass


class MockResponse(object):
    def __init__(self, status_code, content=""):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception("Server returned %s" % force_text(self.status_code))

    def json(self, **kwargs):
        return json.loads(self.content)

    def __next__(self):
        return self


@override_settings(SITE_BACKEND="ureport.tests.TestBackend")
class UreportTest(SmartminTest, DashTest):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username="super", email="super@user.com", password="super")

        self.admin = self.create_user("Administrator")
        self.anon = self.create_user("Anon")
        self.uganda = self.create_org("uganda", pytz.timezone("Africa/Kampala"), self.admin)
        self.nigeria = self.create_org("nigeria", pytz.timezone("Africa/Lagos"), self.admin)

        rapidpro_backend = self.nigeria.backends.filter(slug="rapidpro").first()
        if not rapidpro_backend:
            rapidpro_backend, created = self.nigeria.backends.get_or_create(
                api_token=random_string(32), slug="rapidpro", created_by=self.admin, modified_by=self.admin
            )
        self.rapidpro_backend = rapidpro_backend

        floip_backend = self.nigeria.backends.filter(slug="floip").first()
        if not floip_backend:
            floip_backend, created = self.nigeria.backends.get_or_create(
                api_token=random_string(32), slug="floip", created_by=self.admin, modified_by=self.admin
            )

        self.floip_backend = floip_backend

    def create_org(self, subdomain, timezone, user):

        name = subdomain

        orgs = Org.objects.filter(subdomain=subdomain)
        if orgs:
            org = orgs[0]
            org.name = name
            org.save()
        else:
            org = super(UreportTest, self).create_org(name, timezone, subdomain)

        org.administrators.add(user)

        self.assertEqual(Org.objects.filter(subdomain=subdomain).count(), 1)

        backend = org.backends.filter(slug="rapidpro", is_active=True).first()
        if not backend:
            backend = org.backends.create(
                slug="rapidpro",
                backend_type="ureport.backend.rapidpro.RapidProBackend",
                api_token="token",
                host="http://localhost:8001",
            )

        backend.backend_type = "ureport.backend.rapidpro.RapidProBackend"
        backend.api_token = "token"
        backend.host = "http://localhost:8001"
        backend.save()

        return Org.objects.get(subdomain=subdomain)

    def create_poll(self, org, title, flow_uuid, category, user, featured=False, has_synced=False):
        now = timezone.now()
        backend = org.backends.filter(slug="rapidpro", is_active=True).first()
        poll = Poll.objects.create(
            flow_uuid=flow_uuid,
            title=title,
            category=category,
            is_featured=featured,
            has_synced=has_synced,
            backend=backend,
            org=org,
            poll_date=now,
            created_by=user,
            modified_by=user,
        )

        return poll


class UreportJobsTest(UreportTest):
    FB_SOURCE = "http://www.facebook.com/%s"
    TW_SOURCE = "http://twitter.com/%s"
    RSS_SOURCE = "http://dummy.rss.com/%s.xml"

    def create_fb_job_source(self, org, fb_identifier):
        return JobSource.objects.create(
            source_url=UreportJobsTest.FB_SOURCE % fb_identifier,
            source_type=JobSource.FACEBOOK,
            org=org,
            created_by=self.admin,
            modified_by=self.admin,
        )

    def create_tw_job_source(self, org, tw_identifier):
        return JobSource.objects.create(
            source_url=UreportJobsTest.TW_SOURCE % tw_identifier,
            widget_id="WIDGETID_%s" % tw_identifier,
            source_type=JobSource.TWITTER,
            org=org,
            created_by=self.admin,
            modified_by=self.admin,
        )

    def create_rss_job_source(self, org, rss_identifier):
        return JobSource.objects.create(
            source_url=UreportJobsTest.RSS_SOURCE % rss_identifier,
            source_type=JobSource.RSS,
            org=org,
            created_by=self.admin,
            modified_by=self.admin,
        )


class SetOrgMiddlewareTest(UreportTest):
    def setUp(self):
        super(SetOrgMiddlewareTest, self).setUp()

        self.middleware = SetOrgMiddleware()
        self.request = Mock(spec=HttpRequest)
        self.request.user = self.anon
        self.request.path = "/"
        self.request.get_host.return_value = "ureport.io"
        self.request.META = dict(HTTP_HOST=None)

    def test_process_request_without_org(self):
        response = self.middleware.process_request(self.request)
        self.assertEqual(response, None)
        self.assertEqual(self.request.org, None)

    def test_process_request_with_org(self):

        ug_org = self.create_org("uganda", pytz.timezone("Africa/Kampala"), self.admin)
        ug_dash_url = ug_org.subdomain + ".ureport.io"
        self.request.get_host.return_value = ug_dash_url

        response = self.middleware.process_request(self.request)
        self.assertEqual(response, None)
        self.assertEqual(self.request.org, ug_org)

        self.request.user = self.admin
        response = self.middleware.process_request(self.request)
        self.assertEqual(response, None)
        self.assertEqual(self.request.org, ug_org)
        self.assertEqual(self.request.user.get_org(), ug_org)

        # test invalid subdomain
        wrong_subdomain_url = "blabla.ureport.io"
        self.request.get_host.return_value = wrong_subdomain_url
        response = self.middleware.process_request(self.request)
        self.assertEqual(response, None)
        self.assertEqual(self.request.org, None)

    def test_process_view(self):
        with patch("django.urls.ResolverMatch") as resolver_mock:
            resolver_mock.url_name.return_value = "public.index"

            self.request.resolver_match = resolver_mock

            ug_org = self.uganda
            ug_dash_url = ug_org.subdomain + ".ureport.io"
            self.request.get_host.return_value = ug_dash_url

            # test invalid subdomain
            wrong_subdomain_url = "blabla.ureport.io"
            self.request.get_host.return_value = wrong_subdomain_url
            self.request.org = None
            response = self.middleware.process_view(self.request, IndexView.as_view(), [], dict())
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse(settings.SITE_CHOOSER_URL_NAME))
            self.assertEqual(self.request.org, None)
            self.assertEqual(self.request.user.get_org(), None)

            self.create_org("rwanda", pytz.timezone("Africa/Kigali"), self.admin)
            wrong_subdomain_url = "blabla.ureport.io"
            self.request.get_host.return_value = wrong_subdomain_url
            response = self.middleware.process_view(self.request, IndexView.as_view(), [], dict())
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse(settings.SITE_CHOOSER_URL_NAME))
