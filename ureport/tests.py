# -*- coding: utf-8 -*-

import json
import os
import uuid
import zoneinfo
from datetime import timedelta
from types import SimpleNamespace

from gunicorn.config import Config
from mock import Mock, patch
from temba_client.v2 import TembaClient
from temba_client.v2.types import (
    Contact as TembaContact,
    Export as TembaExport,
    Field as TembaContactField,
    Flow,
    Group,
)

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.http.request import HttpRequest
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_str

from dash.orgs.middleware import SetOrgMiddleware
from dash.orgs.models import Org
from dash.test import DashTest
from dash.utils import random_string
from smartmin.tests import SmartminTest
from ureport.backend.rapidpro import RapidProBackend
from ureport.flows.models import FlowResult, FlowResultCategory
from ureport.gunicorn import JSONAccessLogger
from ureport.jobs.models import JobSource
from ureport.polls.models import Poll, PollQuestion, PollResponseCategory
from ureport.public.views import IndexView


class MockTembaClient(TembaClient):
    def get_fields(self, pager=None):
        return [TembaContactField.create(key="gender", label="Genre", value_type="T")]

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
            raise Exception("Server returned %s" % force_str(self.status_code))

    def json(self, **kwargs):
        return json.loads(self.content)

    def __next__(self):
        return self


@override_settings(SITE_BACKEND="ureport.tests.TestBackend")
class UreportTest(SmartminTest, DashTest):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="super", email="super@user.com", password="super"
        )

        self.admin = self.create_user("Administrator")
        self.anon = self.create_user("Anon")
        self.uganda = self.create_org("uganda", zoneinfo.ZoneInfo("Africa/Kampala"), self.admin)
        self.nigeria = self.create_org("nigeria", zoneinfo.ZoneInfo("Africa/Lagos"), self.admin)

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

    def create_poll(self, org, title, flow_uuid, category, user, featured=False, has_synced=False, published=True):
        now = timezone.now()
        backend = org.backends.filter(slug="rapidpro", is_active=True).first()
        poll = Poll.objects.create(
            flow_uuid=flow_uuid,
            title=title,
            category=category,
            published=published,
            is_featured=featured,
            has_synced=has_synced,
            backend=backend,
            org=org,
            poll_date=now,
            created_by=user,
            modified_by=user,
        )

        return poll

    def create_poll_question(self, user, poll, result_name, result_uuid):
        flow_result = FlowResult.objects.filter(org=poll.org, flow_uuid=poll.flow_uuid, result_uuid=result_uuid).first()
        if flow_result:
            flow_result.result_name = result_name
            flow_result.save(update_fields=("result_name",))
        else:
            flow_result = FlowResult.objects.create(
                org=poll.org, flow_uuid=poll.flow_uuid, result_uuid=result_uuid, result_name=result_name
            )

        question = PollQuestion.objects.filter(ruleset_uuid=result_uuid, poll=poll).first()
        if question:
            question.ruleset_label = result_name
            question.flow_result = flow_result
            question.save(update_fields=("ruleset_label", "flow_result"))
        else:
            question = PollQuestion.objects.create(
                poll=poll,
                title=result_name,
                ruleset_label=result_name,
                ruleset_uuid=result_uuid,
                flow_result=flow_result,
                created_by=user,
                modified_by=user,
            )
        return question

    def create_poll_response_category(self, question, rule_uuid, category):
        flow_result_category = FlowResultCategory.objects.filter(
            flow_result=question.flow_result, category=category
        ).first()
        if flow_result_category:
            flow_result_category.is_active = True
            flow_result_category.save(update_fields=("is_active",))
        else:
            flow_result_category = FlowResultCategory.objects.create(
                flow_result=question.flow_result, category=category, is_active=True
            )

        obj = PollResponseCategory.objects.filter(question=question, category=category).first()

        if obj:
            obj.is_active = True
            obj.category = category
            obj.flow_result_category = flow_result_category
            obj.save(update_fields=("is_active", "category", "flow_result_category"))

        else:
            if not rule_uuid:
                rule_uuid = uuid.uuid4()

            obj = PollResponseCategory.objects.create(
                question=question,
                rule_uuid=rule_uuid,
                category=category,
                category_displayed=category,
                flow_result_category=flow_result_category,
                is_active=True,
            )
        return obj


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

        self.middleware = SetOrgMiddleware(self.get_response)
        self.request = Mock(spec=HttpRequest)
        self.request.user = self.anon
        self.request.path = "/"
        self.request.get_host.return_value = "ureport.io"
        self.request.META = dict(HTTP_HOST=None)

    def get_response(request):
        return HttpResponse()

    def test_process_request_without_org(self):
        response = self.middleware.process_request(self.request)
        self.assertEqual(response, None)
        self.assertEqual(self.request.org, None)

    def test_process_request_with_org(self):
        ug_org = self.create_org("uganda", zoneinfo.ZoneInfo("Africa/Kampala"), self.admin)
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

            self.create_org("rwanda", zoneinfo.ZoneInfo("Africa/Kigali"), self.admin)
            wrong_subdomain_url = "blabla.ureport.io"
            self.request.get_host.return_value = wrong_subdomain_url
            response = self.middleware.process_view(self.request, IndexView.as_view(), [], dict())
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse(settings.SITE_CHOOSER_URL_NAME))


class JSONAccessLoggerTest(SimpleTestCase):
    def logger(self, **settings) -> JSONAccessLogger:
        cfg = Config()
        for name, value in settings.items():
            cfg.set(name, value)
        return JSONAccessLogger(cfg)

    def log(self, logger, environ: dict, *, status="200 OK", sent=0, ms=0.0) -> dict:
        resp = SimpleNamespace(status=status, sent=sent, headers=[])

        with self.assertLogs("gunicorn.access", level="INFO") as captured:
            logger.access(resp, None, environ, timedelta(milliseconds=ms))

        self.assertEqual(1, len(captured.records))
        return json.loads(captured.records[0].getMessage())

    def test_record(self):
        record = self.log(
            self.logger(accesslog="-"),
            {
                "REQUEST_METHOD": "POST",
                "PATH_INFO": "/manage/poll/",
                "QUERY_STRING": "page=2",
                "SERVER_PROTOCOL": "HTTP/1.1",
                "wsgi.url_scheme": "https",
                "REMOTE_ADDR": "10.0.1.5",
                "HTTP_HOST": "uganda.ureport.io",
                "HTTP_X_FORWARDED_FOR": "203.0.113.9, 10.0.1.5",
                "HTTP_USER_AGENT": "Mozilla/5.0",
                "HTTP_REFERER": "https://uganda.ureport.io/manage/",
            },
            status="200 OK",
            sent=1512,
            ms=34.7,
        )

        self.assertRegex(record.pop("timestamp"), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
        self.assertEqual(
            {
                "http": {
                    "request": {"method": "POST", "header": {"referer": "https://uganda.ureport.io/manage/"}},
                    "response": {"status_code": 200, "body": {"size": 1512}},
                },
                "url": {"scheme": "https", "path": "/manage/poll/", "query": "page=2"},
                "network": {"protocol": {"version": "1.1"}},
                "server": {"address": "uganda.ureport.io"},
                "client": {"address": "203.0.113.9"},  # the first forwarded address, not the load balancer's
                "user_agent": {"original": "Mozilla/5.0"},
                "duration_ms": 34.7,
                "process": {"pid": os.getpid()},
            },
            record,
        )

    def test_absent_fields_are_omitted(self):
        record = self.log(
            self.logger(accesslog="-"),
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/status/",
                "QUERY_STRING": "",
                "SERVER_PROTOCOL": "HTTP/1.1",
                "wsgi.url_scheme": "http",
                "REMOTE_ADDR": "10.0.1.5",
                "HTTP_HOST": "10.0.1.23:8000",
            },
            status="200 OK",
            sent=2,
        )
        record.pop("timestamp")

        self.assertEqual(
            {
                "http": {"request": {"method": "GET"}, "response": {"status_code": 200, "body": {"size": 2}}},
                "url": {"scheme": "http", "path": "/status/"},
                "network": {"protocol": {"version": "1.1"}},
                "server": {"address": "10.0.1.23:8000"},
                "client": {"address": "10.0.1.5"},  # nothing forwarded, so the peer is the client
                "duration_ms": 0.0,
                "process": {"pid": os.getpid()},
            },
            record,
        )

    def test_no_status_when_the_app_never_set_one(self):
        record = self.log(self.logger(accesslog="-"), {"REQUEST_METHOD": "GET"}, status=None)

        self.assertEqual({"body": {"size": 0}}, record["http"]["response"])

    def test_client_controlled_values_cant_break_the_line(self):
        hostile = 'Mozilla/5.0" }\n{"http":{"response":{"status_code":200}}, "injected":"yes'

        logger = self.logger(accesslog="-")
        resp = SimpleNamespace(status="404 Not Found", sent=0, headers=[])

        with self.assertLogs("gunicorn.access", level="INFO") as captured:
            logger.access(resp, None, {"REQUEST_METHOD": "GET", "HTTP_USER_AGENT": hostile}, timedelta())

        line = captured.records[0].getMessage()
        self.assertNotIn("\n", line)

        record = json.loads(line)
        self.assertEqual(hostile, record["user_agent"]["original"])
        self.assertEqual(404, record["http"]["response"]["status_code"])
        self.assertNotIn("injected", record)

    def test_nothing_logged_when_access_logging_is_off(self):
        logger = self.logger()
        resp = SimpleNamespace(status="200 OK", sent=0, headers=[])

        with self.assertNoLogs("gunicorn.access"):
            logger.access(resp, None, {"REQUEST_METHOD": "GET"}, timedelta())

    def test_a_bad_record_is_reported_rather_than_raised(self):
        logger = self.logger(accesslog="-")
        resp = SimpleNamespace(status="200 OK", sent=0, headers=[])

        # a duration that isn't one can't be turned into a record
        with self.assertLogs("gunicorn.error", level="ERROR") as captured, self.assertNoLogs("gunicorn.access"):
            logger.access(resp, None, {"REQUEST_METHOD": "GET"}, None)

        self.assertIn("AttributeError", captured.records[0].getMessage())
