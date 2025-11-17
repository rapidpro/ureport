# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from mock import patch
from temba_client.v2.types import Contact as TembaContact, ObjectRef

from dash.categories.models import Category
from dash.test import MockClientQuery
from dash.utils.sync import SyncOutcome
from ureport.backend.floip import ContactSyncer, FLOIPBackend
from ureport.contacts.models import Contact
from ureport.flows.models import FlowResult, FlowResultCategory
from ureport.locations.models import Boundary
from ureport.polls.models import Poll, PollQuestion, PollResponseCategory, PollResult
from ureport.tests import MockResponse, UreportTest
from ureport.utils import json_date_to_datetime


class ContactSyncerTest(UreportTest):
    def setUp(self):
        super(ContactSyncerTest, self).setUp()
        self.syncer = ContactSyncer(self.floip_backend)
        self.nigeria.set_config("floip.reporter_group", "Ureporters")
        self.nigeria.set_config("floip.registration_label", "registration_date")
        self.nigeria.set_config("floip.state_label", "state")
        self.nigeria.set_config("floip.district_label", "lga")
        self.nigeria.set_config("floip.ward_label", "ward")
        self.nigeria.set_config("floip.born_label", "born")
        self.nigeria.set_config("floip.gender_label", "gender")
        self.nigeria.set_config("floip.female_label", "female")
        self.nigeria.set_config("floip.male_label", "male")

        # boundaries fetched
        self.country = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-NIGERIA",
            name="Nigeria",
            level=Boundary.COUNTRY_LEVEL,
            parent=None,
            backend=self.rapidpro_backend,
            geometry='{"foo":"bar-country"}',
        )
        self.state = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-LAGOS",
            name="Lagos",
            level=Boundary.STATE_LEVEL,
            backend=self.rapidpro_backend,
            parent=self.country,
            geometry='{"foo":"bar-state"}',
        )
        self.district = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-OYO",
            name="Oyo",
            level=Boundary.DISTRICT_LEVEL,
            backend=self.rapidpro_backend,
            parent=self.state,
            geometry='{"foo":"bar-state"}',
        )
        self.ward = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-IKEJA",
            name="Ikeja",
            level=Boundary.WARD_LEVEL,
            parent=self.district,
            geometry='{"foo":"bar-ward"}',
            backend=self.rapidpro_backend,
        )

    def test_local_kwargs(self):
        temba_contact = TembaContact.create(
            uuid="C-006",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": None,
                "state": None,
                "lga": None,
                "born": None,
                "gender": None,
            },
            language="eng",
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.floip_backend,
                "org": self.nigeria,
                "uuid": "C-006",
                "gender": "",
                "born": 0,
                "registered_on": None,
                "state": "",
                "district": "",
                "ward": "",
            },
        )

        temba_contact = TembaContact.create(
            uuid="C-007",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Kigali",
                "lga": "Oyo",
                "born": "1990",
                "gender": "Male",
            },
            language="eng",
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.floip_backend,
                "org": self.nigeria,
                "uuid": "C-007",
                "gender": "M",
                "born": 1990,
                "registered_on": json_date_to_datetime("2014-01-02T03:04:05.000"),
                "state": "",
                "district": "",
                "ward": "",
            },
        )

        temba_contact = TembaContact.create(
            uuid="C-008",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Lagos",
                "lga": "Oyo",
                "ward": "Ikeja",
                "born": "1990",
                "gender": "Male",
            },
            language="eng",
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.floip_backend,
                "org": self.nigeria,
                "uuid": "C-008",
                "gender": "M",
                "born": 1990,
                "registered_on": json_date_to_datetime("2014-01-02T03:04:05.000"),
                "state": "R-LAGOS",
                "district": "R-OYO",
                "ward": "R-IKEJA",
            },
        )

        temba_contact = TembaContact.create(
            uuid="C-008",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Lagos",
                "lga": "Oyo",
                "born": "-1",
                "gender": "Male",
            },
            language="eng",
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.floip_backend,
                "org": self.nigeria,
                "uuid": "C-008",
                "gender": "M",
                "born": 0,
                "registered_on": json_date_to_datetime("2014-01-02T03:04:05.000"),
                "state": "R-LAGOS",
                "district": "R-OYO",
                "ward": "",
            },
        )

        temba_contact = TembaContact.create(
            uuid="C-008",
            name="Jan",
            urns=["tel:123"],
            groups=[ObjectRef.create(uuid="G-001", name="ureporters"), ObjectRef.create(uuid="G-007", name="Actors")],
            fields={
                "registration_date": "2014-01-02T03:04:05.000000Z",
                "state": "Lagos",
                "lga": "Oyo",
                "born": "2147483648",
                "gender": "Male",
            },
            language="eng",
        )

        self.assertEqual(
            self.syncer.local_kwargs(self.nigeria, temba_contact),
            {
                "backend": self.floip_backend,
                "org": self.nigeria,
                "uuid": "C-008",
                "gender": "M",
                "born": 0,
                "registered_on": json_date_to_datetime("2014-01-02T03:04:05.000"),
                "state": "R-LAGOS",
                "district": "R-OYO",
                "ward": "",
            },
        )


class FLOIPBackendTest(UreportTest):
    def setUp(self):
        super(FLOIPBackendTest, self).setUp()
        self.backend = FLOIPBackend(self.floip_backend)
        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

        self.nigeria.set_config("floip.registration_label", "registration_date")
        self.nigeria.set_config("floip.state_label", "state")
        self.nigeria.set_config("floip.district_label", "lga")
        self.nigeria.set_config("floip.ward_label", "ward")
        self.nigeria.set_config("floip.born_label", "born")
        self.nigeria.set_config("floip.gender_label", "gender")
        self.nigeria.set_config("floip.female_label", "Female")
        self.nigeria.set_config("floip.male_label", "Male")

        # boundaries fetched
        self.country = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-NIGERIA",
            name="Nigeria",
            backend=self.rapidpro_backend,
            level=Boundary.COUNTRY_LEVEL,
            parent=None,
            geometry='{"foo":"bar-country"}',
        )
        self.state = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-LAGOS",
            name="Lagos",
            backend=self.rapidpro_backend,
            level=Boundary.STATE_LEVEL,
            parent=self.country,
            geometry='{"foo":"bar-state"}',
        )
        self.district = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-OYO",
            name="Oyo",
            backend=self.rapidpro_backend,
            level=Boundary.DISTRICT_LEVEL,
            parent=self.state,
            geometry='{"foo":"bar-state"}',
        )
        self.ward = Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-IKEJA",
            name="Ikeja",
            backend=self.rapidpro_backend,
            level=Boundary.WARD_LEVEL,
            parent=self.district,
            geometry='{"foo":"bar-state"}',
        )

    @patch("requests.request")
    def test_fetch_flows(self, mock_get):
        response_contents = """{
            "links": {
                "self": "https://go.votomobile.org/flow-results/packages?page%5Bsize%5D=100",
                "next": null,
                "previous": null
            },
            "data": [
                {
                    "type": "packages",
                    "id": "2a754346-a0dc-4176-a8b9-0f978f6b04c7",
                    "attributes": {
                        "id": "2a754346-a0dc-4176-a8b9-0f978f6b04c7",
                        "title": "Standard Test Survey",
                        "name": "standard_test_survey",
                        "created": "2018-04-05 19:32:19+00:00",
                        "modified": "2018-04-05 19:56:17+00:00"
                    }
                }
            ]
        }
        """

        mock_get.return_value = MockResponse(200, response_contents)

        fetched_flows = {
            "2a754346-a0dc-4176-a8b9-0f978f6b04c7": dict(
                uuid="2a754346-a0dc-4176-a8b9-0f978f6b04c7",
                date_hint="2018-04-05 19:32:19+00:00",
                created_on="2018-04-05 19:32:19+00:00",
                name="Standard Test Survey",
                archived=False,
                runs=0,
                completed_runs=0,
            )
        }

        self.assertEqual(self.backend.fetch_flows(self.nigeria), fetched_flows)

    @patch("requests.request")
    def test_get_definition(self, mock_get):
        response_contents = """
        {
            "links": {
                "self": "https://go.votomobile.org/flow-results/packages/2a754346-a0dc-4176-a8b9-0f978f6b04c7"
            },
            "data": {
                "type": "packages",
                "id": "2a754346-a0dc-4176-a8b9-0f978f6b04c7",
                "attributes": {
                    "profile": "flow-results-package",
                    "name": "standard_test_survey",
                    "flow-results-specification": "1.0.0-rc1",
                    "created": "2018-04-05 19:32:19+00:00",
                    "modified": "2018-04-05 19:56:17+00:00",
                    "id": "2a754346-a0dc-4176-a8b9-0f978f6b04c7",
                    "title": "Standard Test Survey",
                    "resources": [
                        {
                            "profile": "data-resource",
                            "name": "standard_test_survey-data",
                            "path": null,
                            "api-data-url": "https://go.votomobile.org/flow-results/packages/2a754346-a0dc-4176-a8b9-0f978f6b04c7/resources",
                            "mediatype": "application/vnd.api+json",
                            "encoding": "utf-8",
                            "schema": {
                                "language": "eng",
                                "fields": [
                                    {
                                        "name": "timestamp",
                                        "title": "Timestamp",
                                        "type": "datetime"
                                    },
                                    {
                                        "name": "row_id",
                                        "title": "Row ID",
                                        "type": "string"
                                    },
                                    {
                                        "name": "contact_id",
                                        "title": "Contact ID",
                                        "type": "string"
                                    },
                                    {
                                        "name": "session_id",
                                        "title": "Session ID",
                                        "type": "string"
                                    },
                                    {
                                        "name": "question_id",
                                        "title": "Question ID",
                                        "type": "string"
                                    },
                                    {
                                        "name": "response_id",
                                        "title": "Response ID",
                                        "type": "any"
                                    },
                                    {
                                        "name": "response_metadata",
                                        "title": "Response Metadata",
                                        "type": "object"
                                    }
                                ],
                                "questions": {
                                    "q_1522956745304_75": {
                                        "type": "select_one",
                                        "label": "What is your gender?",
                                        "type_options": {
                                            "choices": [
                                                "Woman",
                                                "Man"
                                            ]
                                        }
                                    },
                                    "q_1522956746998_26": {
                                        "type": "numeric",
                                        "label": "How old are you?",
                                        "type_options": {
                                            "range": [
                                                -99,
                                                99
                                            ]
                                        }
                                    },
                                    "q_1522957067432_34": {
                                        "type": "open",
                                        "label": "What is the best thing that happened to you today?",
                                        "type_options": {}
                                    }
                                }
                            }
                        }
                    ]
                }
            },
            "relationships": {
                "responses": {
                    "links": {
                        "related": "https://go.votomobile.org/flow-results/packages/2a754346-a0dc-4176-a8b9-0f978f6b04c7/responses"
                    }
                }
            }
        }
        """

        mock_get.return_value = MockResponse(200, response_contents)

        flow_definition = {
            "profile": "flow-results-package",
            "name": "standard_test_survey",
            "flow-results-specification": "1.0.0-rc1",
            "created": "2018-04-05 19:32:19+00:00",
            "modified": "2018-04-05 19:56:17+00:00",
            "id": "2a754346-a0dc-4176-a8b9-0f978f6b04c7",
            "title": "Standard Test Survey",
            "resources": [
                {
                    "profile": "data-resource",
                    "name": "standard_test_survey-data",
                    "path": None,
                    "api-data-url": "https://go.votomobile.org/flow-results/packages/2a754346-a0dc-4176-a8b9-0f978f6b04c7/resources",
                    "mediatype": "application/vnd.api+json",
                    "encoding": "utf-8",
                    "schema": {
                        "language": "eng",
                        "fields": [
                            {"name": "timestamp", "title": "Timestamp", "type": "datetime"},
                            {"name": "row_id", "title": "Row ID", "type": "string"},
                            {"name": "contact_id", "title": "Contact ID", "type": "string"},
                            {"name": "session_id", "title": "Session ID", "type": "string"},
                            {"name": "question_id", "title": "Question ID", "type": "string"},
                            {"name": "response_id", "title": "Response ID", "type": "any"},
                            {"name": "response_metadata", "title": "Response Metadata", "type": "object"},
                        ],
                        "questions": {
                            "q_1522956745304_75": {
                                "type": "select_one",
                                "label": "What is your gender?",
                                "type_options": {"choices": ["Woman", "Man"]},
                            },
                            "q_1522956746998_26": {
                                "type": "numeric",
                                "label": "How old are you?",
                                "type_options": {"range": [-99, 99]},
                            },
                            "q_1522957067432_34": {
                                "type": "open",
                                "label": "What is the best thing that happened to you today?",
                                "type_options": {},
                            },
                        },
                    },
                }
            ],
        }

        self.assertEqual(
            self.backend.get_definition(self.nigeria, "2a754346-a0dc-4176-a8b9-0f978f6b04c7"), flow_definition
        )

        poll = self.create_poll(
            self.nigeria, "Flow 1", "2a754346-a0dc-4176-a8b9-0f978f6b04c7", self.education_nigeria, self.admin
        )
        self.assertEqual(PollQuestion.objects.all().count(), 0)
        self.assertEqual(FlowResult.objects.all().count(), 0)
        self.assertEqual(PollResponseCategory.objects.all().count(), 0)
        self.assertEqual(FlowResultCategory.objects.all().count(), 0)

        self.backend.update_poll_questions(self.nigeria, poll, self.admin)

        self.assertEqual(PollQuestion.objects.all().count(), 3)
        self.assertEqual(FlowResult.objects.all().count(), 3)

        self.assertEqual(PollResponseCategory.objects.all().count(), 4)
        self.assertEqual(FlowResultCategory.objects.all().count(), 4)
        self.assertEqual(PollResponseCategory.objects.filter(category="other").count(), 2)
        self.assertEqual(FlowResultCategory.objects.filter(category="other").count(), 2)

    def test_pull_fields(self):
        self.assertEqual(
            self.backend.pull_fields(self.nigeria),
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

    def test_pull_boundaries(self):
        self.assertEqual(
            self.backend.pull_boundaries(self.nigeria),
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

    @patch("ureport.backend.floip.TembaClient.get_contacts")
    def test_pull_contacts(self, mock_get_contacts):
        Contact.objects.all().delete()

        # empty fetches
        mock_get_contacts.side_effect = [
            # first call to get active contacts
            MockClientQuery([]),
            # second call to get deleted contacts
            MockClientQuery([]),
        ]

        with self.assertNumQueries(0):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        # fecthed contact not in configured group get ignored
        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Bob McFlow",
                        language="eng",
                        urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="Customers")],
                        fields={"age": "34"},
                        status="active",
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-002", name="Spammers")],
                        fields={"age": "67"},
                        status="active",
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003",
                        name="Ann McPoll",
                        language="eng",
                        urns=["tel:+250783835664"],
                        groups=[],
                        fields={"age": "35"},
                        status="blocked",
                    )
                ],
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status="stopped",
                    )
                ]
            ),
        ]

        with self.assertNumQueries(10):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 3, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Bob McFlow",
                        language="eng",
                        urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "34"},
                        status="active",
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-002", name="Spammers")],
                        fields={"age": "67"},
                        status="active",
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003",
                        name="Ann McPoll",
                        language="eng",
                        urns=["tel:+250783835664"],
                        groups=[],
                        fields={"age": "35"},
                        status="stopped",
                    )
                ],
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status="stopped",
                    )
                ]
            ),
        ]

        with self.assertNumQueries(10):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 3},
        )

        Contact.objects.all().delete()

        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Bob McFlow",
                        language="eng",
                        urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "34"},
                        status="active",
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "67"},
                        status="active",
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003",
                        name="Ann McPoll",
                        language="eng",
                        urns=["tel:+250783835664"],
                        groups=[],
                        fields={"age": "35"},
                        status="stopped",
                    )
                ],
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status="stopped",
                    )
                ]
            ),
        ]

        with self.assertNumQueries(10):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 3, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        Contact.objects.all().delete()

        mock_get_contacts.side_effect = [
            # first call to get active contacts will return two fetches of 2 and 1 contacts
            # all included in the reporters
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Bob McFlow",
                        language="eng",
                        urns=["twitter:bobflow"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "34"},
                        status="active",
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "67"},
                        status="active",
                    ),
                ],
                [
                    TembaContact.create(
                        uuid="C-003",
                        name="Ann McPoll",
                        language="eng",
                        urns=["tel:+250783835664"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "35"},
                        status="stopped",
                    )
                ],
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status="stopped",
                    )
                ]
            ),
        ]

        with self.assertNumQueries(10):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 3, SyncOutcome.updated: 0, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        contact_jan = Contact.objects.filter(uuid="C-001").first()
        self.assertFalse(contact_jan.born)
        self.assertFalse(contact_jan.state)

        mock_get_contacts.side_effect = [
            # first call to get active contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-001",
                        name="Jan",
                        urns=["tel:123"],
                        groups=[
                            ObjectRef.create(uuid="G-001", name="ureporters"),
                            ObjectRef.create(uuid="G-007", name="Actors"),
                        ],
                        fields={
                            "registration_date": "2014-01-02T03:04:05.000000Z",
                            "state": "Nigeria > Lagos",
                            "lga": "Nigeria > Lagos > Oyo",
                            "born": "1990",
                            "gender": "Male",
                        },
                        language="eng",
                        status="active",
                    ),
                    TembaContact.create(
                        uuid="C-002",
                        name="Jim McMsg",
                        language="fre",
                        urns=["tel:+250783835665"],
                        groups=[ObjectRef.create(uuid="G-001", name="ureporters")],
                        fields={"age": "67", "born": "1992"},
                        status="active",
                    ),
                ]
            ),
            # second call to get deleted contacts returns a contact we don't have
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-004",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status=None,
                    )
                ]
            ),
        ]

        with self.assertNumQueries(10):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 2, SyncOutcome.deleted: 0, SyncOutcome.ignored: 0},
        )

        contact_jan = Contact.objects.filter(uuid="C-001").first()

        self.assertTrue(contact_jan.born)
        self.assertEqual(contact_jan.born, 1990)
        self.assertTrue(contact_jan.state)
        self.assertEqual(contact_jan.state, "R-LAGOS")

        self.assertTrue(Contact.objects.filter(uuid="C-002", is_active=True))

        mock_get_contacts.side_effect = [
            # first call to get active contacts
            MockClientQuery([]),
            # second call to get deleted contacts
            MockClientQuery(
                [
                    TembaContact.create(
                        uuid="C-002",
                        name=None,
                        language=None,
                        urns=[],
                        groups=[],
                        fields=None,
                        status=None,
                    )
                ]
            ),
        ]

        with self.assertNumQueries(3):
            contact_results, resume_cursor = self.backend.pull_contacts(self.nigeria, None, None)

        self.assertEqual(
            contact_results,
            {SyncOutcome.created: 0, SyncOutcome.updated: 0, SyncOutcome.deleted: 1, SyncOutcome.ignored: 0},
        )

        self.assertFalse(Contact.objects.filter(uuid="C-002", is_active=True))

    @patch("requests.request")
    @patch("valkey.client.StrictValkey.lock")
    @patch("django.core.cache.cache.get")
    def test_pull_results(self, mock_cache_get, mock_valkey_lock, mock_request):
        response_contents = """
        {
            "data": {
                "type": "flow-results-data",
                "id": "2a754346-a0dc-4176-a8b9-0f978f6b04c7",
                "attributes": {
                    "responses": [
                        [
                            "2018-04-05 19:37:09",
                            "479575787",
                            "160786609",
                            "236977343",
                            "q_1522956745304_75",
                            "Man",
                            {}
                        ],
                        [
                            "2018-04-05 19:37:14",
                            "479576022",
                            "160786609",
                            "236977343",
                            "q_1522956746998_26",
                            "33.0000",
                            {}
                        ],
                        [
                            "2018-04-05 19:39:18",
                            "479578705",
                            "160786609",
                            "236977600",
                            "q_1522956745304_75",
                            "Woman",
                            {}
                        ],
                        [
                            "2018-04-05 19:39:21",
                            "479578808",
                            "160786609",
                            "236977600",
                            "q_1522956746998_26",
                            "25.0000",
                            {}
                        ],
                        [
                            "2018-04-05 19:39:37",
                            "479578895",
                            "160786609",
                            "236977600",
                            "q_1522957067432_34",
                            "https://s3-us-west-2.amazonaws.com/audioresponses.votomobile.org/wav/5ac67b69ee6ba5.01962634.wav",
                            {
                                "type": "audio",
                                "format": "audio/wav"
                            }
                        ],
                        [
                            "2018-04-05 19:43:27",
                            "479582854",
                            "160786609",
                            "236977957",
                            "q_1522956745304_75",
                            "Man",
                            {}
                        ],
                        [
                            "2018-04-05 19:42:49",
                            "479583384",
                            "160786609",
                            "236977956",
                            "q_1522956745304_75",
                            "Man",
                            {}
                        ],
                        [
                            "2018-04-05 19:42:52",
                            "479583524",
                            "160786609",
                            "236977956",
                            "q_1522956746998_26",
                            "30.0000",
                            {}
                        ],
                        [
                            "2018-04-05 19:43:09",
                            "479583565",
                            "160786609",
                            "236977956",
                            "q_1522957067432_34",
                            "https://s3-us-west-2.amazonaws.com/audioresponses.votomobile.org/wav/5ac67c3cdfb064.03976750.wav",
                            {
                                "type": "audio",
                                "format": "audio/wav"
                            }
                        ],
                        [
                            "2018-04-05 19:43:38",
                            "479584294",
                            "160786609",
                            "236977957",
                            "q_1522956746998_26",
                            "35.0000",
                            {}
                        ],
                        [
                            "2018-04-05 19:44:05",
                            "479584550",
                            "160786609",
                            "236977957",
                            "q_1522957067432_34",
                            "Making progress with partners on the Flow Results project.",
                            {
                                "type": "text"
                            }
                        ],
                        [
                            "2018-04-05 19:48:01",
                            "479589160",
                            "160786632",
                            "236980450",
                            "q_1522956745304_75",
                            "Woman",
                            {}
                        ],
                        [
                            "2018-04-05 19:48:12",
                            "479589345",
                            "160786632",
                            "236980450",
                            "q_1522956746998_26",
                            "23.0000",
                            {}
                        ],
                        [
                            "2018-04-05 19:49:18",
                            "479589540",
                            "160786632",
                            "236980450",
                            "q_1522957067432_34",
                            "https://s3-us-west-2.amazonaws.com/audioresponses.votomobile.org/wav/5ac67d7c5cce83.30730585.wav",
                            {
                                "type": "audio",
                                "format": "audio/wav"
                            }
                        ],
                        [
                            "2018-04-05 19:57:06",
                            "479597206",
                            "160786653",
                            "236983202",
                            "q_1522956745304_75",
                            "Man",
                            {}
                        ],
                        [
                            "2018-04-05 19:57:21",
                            "479597439",
                            "160790933",
                            "236983203",
                            "q_1522956745304_75",
                            "Man",
                            {}
                        ],
                        [
                            "2018-04-05 19:57:07",
                            "479597458",
                            "160786649",
                            "236983201",
                            "q_1522956745304_75",
                            "Man",
                            {}
                        ],
                        [
                            "2018-04-05 19:57:14",
                            "479597554",
                            "160786653",
                            "236983202",
                            "q_1522956746998_26",
                            "37.0000",
                            {}
                        ],
                        [
                            "2018-04-05 19:57:20",
                            "479597575",
                            "160786649",
                            "236983201",
                            "q_1522956746998_26",
                            "38.0000",
                            {}
                        ],
                        [
                            "2018-04-05 19:57:38",
                            "479597680",
                            "160786653",
                            "236983202",
                            "q_1522957067432_34",
                            "Mini egg brownie!!",
                            {
                                "type": "text"
                            }
                        ],
                        [
                            "2018-04-05 19:57:33",
                            "479597786",
                            "160786649",
                            "236983201",
                            "q_1522957067432_34",
                            "https://s3-us-west-2.amazonaws.com/audioresponses.votomobile.org/wav/5ac67fa09a72a5.38746156.wav",
                            {
                                "type": "audio",
                                "format": "audio/wav"
                            }
                        ],
                        [
                            "2018-04-05 19:57:34",
                            "479597796",
                            "160790933",
                            "236983203",
                            "q_1522956746998_26",
                            "26.0000",
                            {}
                        ],
                        [
                            "2018-04-05 19:57:43",
                            "479597971",
                            "160790933",
                            "236983203",
                            "q_1522957067432_34",
                            "https://s3-us-west-2.amazonaws.com/audioresponses.votomobile.org/wav/5ac67faee188b9.52434885.wav",
                            {
                                "type": "audio",
                                "format": "audio/wav"
                            }
                        ]
                    ]
                },
                "relationships": {
                    "descriptor": {
                        "links": {
                            "self": "https://go.votomobile.org/flow-results/packages/2a754346-a0dc-4176-a8b9-0f978f6b04c7"
                        }
                    },
                    "links": {
                        "self": "https://go.votomobile.org/flow-results/packages/2a754346-a0dc-4176-a8b9-0f978f6b04c7/responses?page%5Bsize%5D=100",
                        "next": null,
                        "previous": null
                    }
                }
            }
        }
        """

        mock_request.return_value = MockResponse(200, response_contents)
        mock_cache_get.return_value = None

        PollResult.objects.all().delete()
        Contact.objects.create(
            org=self.nigeria, uuid="160786609", gender="M", born=1990, state="R-LAGOS", district="R-OYO"
        )
        poll = self.create_poll(
            self.nigeria, "Flow 1", "2a754346-a0dc-4176-a8b9-0f978f6b04c7", self.education_nigeria, self.admin
        )

        self.create_poll_question(self.admin, poll, "question 1", "q_1522956745304_75")
        self.create_poll_question(self.admin, poll, "question 2", "q_1522956746998_26")
        self.create_poll_question(self.admin, poll, "question 3", "q_1522957067432_34")

        with self.assertNumQueries(4):
            (
                num_val_created,
                num_val_updated,
                num_val_ignored,
                num_path_created,
                num_path_updated,
                num_path_ignored,
            ) = self.backend.pull_results(poll, None, None)

        self.assertEqual(
            (num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored),
            (15, 0, 8, 0, 0, 0),
        )
        mock_valkey_lock.assert_called_once_with(
            Poll.POLL_PULL_RESULTS_TASK_LOCK % (poll.org.pk, poll.flow_uuid), timeout=7200
        )

        poll_result = PollResult.objects.filter(
            flow="2a754346-a0dc-4176-a8b9-0f978f6b04c7", ruleset="q_1522956745304_75", contact="160786609"
        ).first()
        self.assertEqual(poll_result.state, "R-LAGOS")
        self.assertEqual(poll_result.district, "R-OYO")
        self.assertEqual(poll_result.contact, "160786609")
        self.assertEqual(poll_result.ruleset, "q_1522956745304_75")
        self.assertEqual(poll_result.flow, "2a754346-a0dc-4176-a8b9-0f978f6b04c7")
        self.assertEqual(poll_result.category, "Man")
        self.assertEqual(poll_result.text, "Man")
