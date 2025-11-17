# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import zoneinfo
from datetime import datetime, timezone as tzone

import mock
import valkey
from mock import patch
from temba_client.v2 import Flow

from django.conf import settings
from django.utils import timezone

from dash.categories.models import Category
from dash.test import MockClientQuery, MockResponse
from ureport.contacts.models import ReportersCounter
from ureport.locations.models import Boundary
from ureport.polls.models import CACHE_ORG_FLOWS_KEY, UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME, Poll
from ureport.tests import UreportTest
from ureport.utils import (
    GLOBAL_COUNT_CACHE_KEY,
    ORG_CONTACT_COUNT_KEY,
    datetime_to_json_date,
    fetch_flows,
    fetch_old_sites_count,
    get_age_stats,
    get_flows,
    get_gender_stats,
    get_global_count,
    get_linked_orgs,
    get_org_contacts_counts,
    get_regions_stats,
    get_registration_stats,
    get_reporters_count,
    get_ureporters_locations_stats,
    json_date_to_datetime,
    update_poll_flow_data,
)


class UtilsTest(UreportTest):
    def setUp(self):
        super(UtilsTest, self).setUp()
        self.org = self.create_org("burundi", zoneinfo.ZoneInfo("Africa/Bujumbura"), self.admin)

        self.education = Category.objects.create(
            org=self.org, name="Education", created_by=self.admin, modified_by=self.admin
        )

        self.poll = self.create_poll(self.org, "Poll 1", "uuid-1", self.education, self.admin)

    def clear_cache(self):
        # hardcoded to localhost
        r = valkey.StrictValkey(host="localhost", db=1)
        r.flushdb()

    def test_datetime_to_json_date(self):
        d1 = datetime(2014, 1, 2, 3, 4, 5, tzinfo=tzone.utc)
        self.assertEqual(datetime_to_json_date(d1), "2014-01-02T03:04:05.000Z")
        self.assertEqual(json_date_to_datetime("2014-01-02T03:04:05.000+00:00"), d1)
        self.assertEqual(json_date_to_datetime("2014-01-02T03:04:05.000Z"), d1)
        self.assertEqual(json_date_to_datetime("2014-01-02T03:04:05.000"), d1)

        tz = zoneinfo.ZoneInfo("Africa/Kigali")
        d2 = datetime(2014, 1, 2, 3, 4, 5, tzinfo=tz)
        self.assertEqual(datetime_to_json_date(d2), "2014-01-02T01:04:05.000Z")
        self.assertEqual(json_date_to_datetime("2014-01-02T03:04:05+02:00"), d2)
        self.assertEqual(json_date_to_datetime("2014-01-02T01:04:05.000Z"), d2)
        self.assertEqual(json_date_to_datetime("2014-01-02T01:04:05.000"), d2)

    @mock.patch("ureport.utils.get_shared_sites_count")
    def test_get_linked_orgs(self, mock_get_shared_sites_count):
        settings_sites = list(getattr(settings, "COUNTRY_FLAGS_SITES", []))
        mock_get_shared_sites_count.return_value = {
            "global_count": 120,
            "countries_count": 12,
            "linked_sites": settings_sites,
        }

        settings_sites_count = len(settings_sites)

        # we have 1 org in settings we do not show its link (global)
        self.assertEqual(len(get_linked_orgs()), settings_sites_count - 1)
        self.assertEqual(get_linked_orgs()[0]["name"].lower(), "afghanistan")

    @patch("dash.orgs.models.TembaClient.get_flows")
    def test_fetch_flows(self, mock_get_flows):
        mock_get_flows.side_effect = [
            MockClientQuery(
                [
                    Flow.create(
                        name="Flow 1",
                        uuid="uuid-25",
                        labels=[],
                        archived=False,
                        expires=720,
                        created_on=json_date_to_datetime("2015-04-08T12:48:44.320Z"),
                        results=[
                            Flow.FlowResult.create(
                                key="color",
                                name="Color",
                                categories=["Orange", "Blue", "Other", "Nothing"],
                                node_uuids=["42a8e177-9e88-429b-b70a-7d4854423092"],
                            )
                        ],
                        runs=Flow.Runs.create(completed=120, active=50, expired=100, interrupted=30),
                    )
                ]
            )
        ]

        with patch("ureport.utils.datetime_to_ms") as mock_datetime_ms:
            mock_datetime_ms.return_value = 500

            with patch("django.core.cache.cache.set") as cache_set_mock:
                flows = fetch_flows(self.org, self.rapidpro_backend)
                expected = dict()
                expected["uuid-25"] = dict(
                    uuid="uuid-25",
                    date_hint="2015-04-08",
                    created_on="2015-04-08T12:48:44.320Z",
                    name="Flow 1",
                    runs=300,
                    completed_runs=120,
                    archived=False,
                    results=[
                        dict(
                            key="color",
                            name="Color",
                            categories=["Orange", "Blue", "Other", "Nothing"],
                            node_uuids=["42a8e177-9e88-429b-b70a-7d4854423092"],
                        )
                    ],
                )

            self.assertEqual(flows, expected)

            cache_set_mock.assert_called_once_with(
                "org:%d:backend:%s:flows" % (self.org.pk, self.rapidpro_backend.slug),
                dict(time=500, results=expected),
                UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME,
            )

    def test_update_poll_flow_data(self):
        poll = Poll.objects.filter(pk=self.poll.pk).first()
        self.assertFalse(poll.flow_archived)
        self.assertEqual(poll.runs_count, 0)

        with patch("ureport.utils.get_flows") as mock_get_flows:
            mock_get_flows.return_value = dict()

            update_poll_flow_data(self.org)
            poll = Poll.objects.filter(pk=self.poll.pk).first()
            self.assertFalse(poll.flow_archived)
            self.assertEqual(poll.runs_count, 0)

            mock_get_flows.return_value = {"uuid-1": {"uuid": "uuid-1", "archived": True}}

            update_poll_flow_data(self.org)
            poll = Poll.objects.filter(pk=self.poll.pk).first()
            self.assertTrue(poll.flow_archived)
            self.assertEqual(poll.runs_count, 0)

            mock_get_flows.return_value = {"uuid-1": {"uuid": "uuid-1", "archived": True, "runs": 0}}

            update_poll_flow_data(self.org)
            poll = Poll.objects.filter(pk=self.poll.pk).first()
            self.assertTrue(poll.flow_archived)
            self.assertEqual(poll.runs_count, 0)

            mock_get_flows.return_value = {"uuid-1": {"uuid": "uuid-1", "archived": True, "runs": 5}}

            update_poll_flow_data(self.org)
            poll = Poll.objects.filter(pk=self.poll.pk).first()
            self.assertTrue(poll.flow_archived)
            self.assertEqual(poll.flow_uuid, "uuid-1")
            self.assertEqual(poll.runs_count, 5)

            mock_get_flows.return_value = {"uuid-1": {"uuid": "uuid-1", "archived": True, "runs": 0}}

            update_poll_flow_data(self.org)
            poll = Poll.objects.filter(pk=self.poll.pk).first()
            self.assertTrue(poll.flow_archived)
            self.assertEqual(poll.runs_count, 5)

            mock_get_flows.return_value = {"uuid-1": {"uuid": "uuid-1", "archived": False, "runs": 0}}

            update_poll_flow_data(self.org)
            poll = Poll.objects.filter(pk=self.poll.pk).first()
            self.assertFalse(poll.flow_archived)
            self.assertEqual(poll.runs_count, 5)

            mock_get_flows.return_value = {"uuid-1": {"uuid": "uuid-1", "archived": False, "runs": 3}}

            update_poll_flow_data(self.org)
            poll = Poll.objects.filter(pk=self.poll.pk).first()
            self.assertFalse(poll.flow_archived)
            self.assertEqual(poll.runs_count, 3)

            mock_get_flows.return_value = {"uuid-1": {"uuid": "uuid-1", "archived": True, "runs": 2}}

            update_poll_flow_data(self.org)
            poll = Poll.objects.filter(pk=self.poll.pk).first()
            self.assertTrue(poll.flow_archived)
            self.assertEqual(poll.runs_count, 2)

            mock_get_flows.return_value = {"uuid-1": {"uuid": "uuid-1"}}

            update_poll_flow_data(self.org)
            poll = Poll.objects.filter(pk=self.poll.pk).first()
            self.assertFalse(poll.flow_archived)
            self.assertEqual(poll.runs_count, 2)

    def test_fetch_old_sites_count(self):
        self.clear_cache()

        settings_sites = list(getattr(settings, "COUNTRY_FLAGS_SITES", []))

        with patch("ureport.utils.datetime_to_ms") as mock_datetime_ms:
            mock_datetime_ms.return_value = 500

            with patch("requests.get") as mock_get:
                mock_get.return_value = MockResponse(200, b"300")

                with patch("django.core.cache.cache.set") as cache_set_mock:
                    cache_set_mock.return_value = "Set"

                    with patch("django.core.cache.cache.delete") as cache_delete_mock:
                        cache_delete_mock.return_value = "Deleted"

                        old_site_values = fetch_old_sites_count()
                        self.assertEqual(
                            old_site_values,
                            [{"time": 500, "results": dict(size=300)}]
                            * len([elt for elt in settings_sites if elt["count_link"]]),
                        )

                        mock_get.assert_called_with("https://www.ureport.in/count/")

                        cache_set_mock.assert_called_with(
                            "org:global:reporters:old-site",
                            {"time": 500, "results": dict(size=300)},
                            None,
                        )

                        cache_delete_mock.assert_called_once_with(GLOBAL_COUNT_CACHE_KEY)

    def test_get_gender_labels(self):
        self.assertEqual(self.org.get_gender_labels(), {"M": "Male", "F": "Female", "O": "Other"})

        self.org.language = "fr"
        self.org.save()

        self.assertEqual(self.org.get_gender_labels(), {"M": "Homme", "F": "Femme", "O": "Autre"})

        self.org.language = "es"
        self.org.save()

        self.assertEqual(self.org.get_gender_labels(), {"M": "Hombre", "F": "Mujer", "O": "Otro"})

    @patch("django.core.cache.cache.get")
    def test_get_gender_stats(self, mock_cache_get):
        mock_cache_get.return_value = None

        self.assertEqual(
            get_gender_stats(self.org),
            dict(female_count=0, female_percentage="---", male_count=0, male_percentage="---"),
        )

        ReportersCounter.objects.create(org=self.org, type="gender:f", count=2)
        ReportersCounter.objects.create(org=self.org, type="gender:m", count=2)
        ReportersCounter.objects.create(org=self.org, type="gender:m", count=1)

        self.assertEqual(
            get_gender_stats(self.org),
            dict(female_count=2, female_percentage="40%", male_count=3, male_percentage="60%"),
        )

        self.org.set_config("common.has_extra_gender", True)

        ReportersCounter.objects.create(org=self.org, type="gender:o", count=5)
        self.assertEqual(
            get_gender_stats(self.org),
            dict(
                female_count=2,
                female_percentage="20%",
                male_count=3,
                male_percentage="30%",
                other_count=5,
                other_percentage="50%",
            ),
        )

    @patch("django.core.cache.cache.get")
    def test_get_age_stats(self, mock_cache_get):
        mock_cache_get.return_value = None

        expected = [
            dict(name="0-14", y=0, absolute_count=0),
            dict(name="15-19", y=0, absolute_count=0),
            dict(name="20-24", y=0, absolute_count=0),
            dict(name="25-30", y=0, absolute_count=0),
            dict(name="31-34", y=0, absolute_count=0),
            dict(name="35+", y=0, absolute_count=0),
        ]

        self.assertEqual(get_age_stats(self.org), json.dumps(expected))

        now = timezone.now()
        now_year = now.year

        two_years_ago = now_year - 2
        five_years_ago = now_year - 5
        twelve_years_ago = now_year - 12
        fifteen_years_ago = now_year - 15
        seventeen_years_ago = now_year - 17
        nineteen_years_ago = now_year - 19
        twenty_years_ago = now_year - 20
        thirty_years_ago = now_year - 30
        thirty_one_years_ago = now_year - 31
        forthy_five_years_ago = now_year - 45

        ReportersCounter.objects.create(org=self.org, type="born:%s" % two_years_ago, count=2)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % five_years_ago, count=1)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % twelve_years_ago, count=3)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % twelve_years_ago, count=2)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % fifteen_years_ago, count=25)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % seventeen_years_ago, count=40)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % nineteen_years_ago, count=110)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % twenty_years_ago, count=2)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % thirty_years_ago, count=12)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % thirty_one_years_ago, count=2)
        ReportersCounter.objects.create(org=self.org, type="born:%s" % forthy_five_years_ago, count=2)

        ReportersCounter.objects.create(org=self.org, type="born:10", count=10)
        ReportersCounter.objects.create(org=self.org, type="born:732837", count=20)

        # y is the percentage of count over the total count
        expected = [
            dict(name="0-14", y=4, absolute_count=8),
            dict(name="15-19", y=87, absolute_count=175),
            dict(name="20-24", y=1, absolute_count=2),
            dict(name="25-30", y=6, absolute_count=12),
            dict(name="31-34", y=1, absolute_count=2),
            dict(name="35+", y=1, absolute_count=2),
        ]

        self.assertEqual(get_age_stats(self.org), json.dumps(expected))

    @patch("django.core.cache.cache.get")
    def test_get_registration_stats(self, mock_cache_get):
        mock_cache_get.return_value = None

        tz = zoneinfo.ZoneInfo("UTC")
        with patch.object(timezone, "now", return_value=datetime(2015, 9, 4, 3, 4, 5, 6, tzinfo=tz)):
            stats = json.loads(get_registration_stats(self.org))

            for entry in stats:
                self.assertEqual(entry["count"], 0)

            ReportersCounter.objects.create(org=self.org, type="registered_on:2015-08-27", count=3)
            ReportersCounter.objects.create(org=self.org, type="registered_on:2015-08-25", count=2)
            ReportersCounter.objects.create(org=self.org, type="registered_on:2015-08-25", count=3)
            ReportersCounter.objects.create(org=self.org, type="registered_on:2015-08-25", count=1)
            ReportersCounter.objects.create(org=self.org, type="registered_on:2015-06-30", count=2)
            ReportersCounter.objects.create(org=self.org, type="registered_on:2015-06-30", count=2)
            ReportersCounter.objects.create(org=self.org, type="registered_on:2014-11-25", count=6)

            stats = json.loads(get_registration_stats(self.org))

            non_zero_keys = {"08/24/15": 9, "06/29/15": 4}

            for entry in stats:
                self.assertFalse(entry["label"].endswith("14"))
                if entry["count"] != 0:
                    self.assertTrue(entry["label"] in non_zero_keys.keys())
                    self.assertEqual(entry["count"], non_zero_keys[entry["label"]])

    def test_get_ureporters_locations_stats(self):
        self.assertEqual(get_ureporters_locations_stats(self.org, dict()), [])
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location="map")), [])
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location="state")), [])
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location="district")), [])

        self.country = Boundary.objects.create(
            org=self.org, osm_id="R-COUNTRY", name="Country", level=0, parent=None, geometry='{"foo":"bar-country"}'
        )
        self.state = Boundary.objects.create(
            org=self.org, osm_id="R-STATE", name="State", level=1, parent=self.country, geometry='{"foo":"bar-state"}'
        )
        self.city = Boundary.objects.create(
            org=self.org, osm_id="R-CITY", name="City", level=1, parent=self.country, geometry='{"foo":"bar-city"}'
        )
        self.district = Boundary.objects.create(
            org=self.org,
            osm_id="R-DISTRICT",
            name="District",
            level=2,
            parent=self.state,
            geometry='{"foo":"bar-district"}',
        )

        inactive_district = Boundary.objects.create(
            org=self.org,
            osm_id="R-DISTRICT2",
            name="District",
            level=2,
            parent=self.state,
            geometry='{"foo":"bar-district"}',
        )
        inactive_district.is_active = False
        inactive_district.save()

        ReportersCounter.objects.create(org=self.org, type="state:R-STATE", count=5)
        ReportersCounter.objects.create(org=self.org, type="district:R-DISTRICT", count=3)

        self.assertEqual(get_ureporters_locations_stats(self.org, dict()), [])
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location="map")), [])
        self.assertEqual(
            get_ureporters_locations_stats(self.org, dict(location="state")),
            [dict(boundary="R-CITY", label="City", set=0), dict(boundary="R-STATE", label="State", set=5)],
        )

        # district without parent
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location="district")), [])

        # district with wrong parent
        self.assertEqual(get_ureporters_locations_stats(self.org, dict(location="district", parent="BLABLA")), [])

        self.assertEqual(
            get_ureporters_locations_stats(self.org, dict(location="district", parent="R-STATE")),
            [dict(boundary="R-DISTRICT", label="District", set=3)],
        )

    @patch("django.core.cache.cache.get")
    def test_get_regions_stats(self, mock_cache_get):
        mock_cache_get.return_value = None
        self.assertEqual(get_regions_stats(self.org), [])

        Boundary.objects.create(
            org=self.org,
            osm_id="R-NIGERIA",
            name="Nigeria",
            parent=None,
            level=0,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        Boundary.objects.create(
            org=self.org,
            osm_id="R-LAGOS",
            name="Lagos",
            parent=None,
            level=1,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        Boundary.objects.create(
            org=self.org,
            osm_id="R-OYO",
            name="OYO",
            parent=None,
            level=1,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        Boundary.objects.create(
            org=self.org,
            osm_id="R-ABUJA",
            name="Abuja",
            parent=None,
            level=1,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        self.assertEqual(get_regions_stats(self.org), [])

        ReportersCounter.objects.create(org=self.org, type="state:R-LAGOS", count=5)

        self.assertEqual(get_regions_stats(self.org), [dict(name="Lagos", count=5)])

        ReportersCounter.objects.create(org=self.org, type="state:R-OYO", count=15)

        self.assertEqual(get_regions_stats(self.org), [dict(name="OYO", count=15), dict(name="Lagos", count=5)])

        self.org.set_config("common.is_global", True)

        self.assertEqual(get_regions_stats(self.org), [])

        ReportersCounter.objects.create(org=self.org, type="state:R-NIGERIA", count=30)
        self.assertEqual(get_regions_stats(self.org), [dict(name="Nigeria", count=30)])

    def test_get_org_contacts_counts(self):
        with patch("ureport.contacts.models.ReportersCounter.get_counts") as mock_get_counts:
            mock_get_counts.return_value = {"total-reporters": 50}
            with patch("django.core.cache.cache.get") as mock_cache_get:
                with patch("django.core.cache.cache.set") as mock_cache_set:
                    mock_cache_get.return_value = {"total-reporters": 13}

                    self.assertEqual(get_org_contacts_counts(self.org), {"total-reporters": 13})
                    mock_cache_get.assert_called_once_with(ORG_CONTACT_COUNT_KEY % self.org.pk, None)
                    mock_cache_set.assert_called_once_with(
                        f"{ORG_CONTACT_COUNT_KEY % self.org.pk}-total-reporters", 13, None
                    )

                    self.assertFalse(mock_get_counts.called)

                    mock_cache_get.return_value = None
                    mock_cache_set.reset_mock()

                    self.assertEqual(get_org_contacts_counts(self.org), {"total-reporters": 50})
                    mock_get_counts.assert_called_once_with(self.org)
                    mock_cache_set.assert_called_once_with(
                        ORG_CONTACT_COUNT_KEY % self.org.pk, {"total-reporters": 50}, None
                    )

    def test_get_flows(self):
        with patch("ureport.utils.fetch_flows") as mock_fetch_flows:
            mock_fetch_flows.return_value = "Fetched"
            with patch("django.core.cache.cache.get") as mock_cache_get:
                mock_cache_get.return_value = dict(results="Cached")

                self.assertEqual(get_flows(self.org, self.rapidpro_backend), "Cached")
                mock_cache_get.assert_called_once_with(
                    CACHE_ORG_FLOWS_KEY % (self.org.pk, self.rapidpro_backend.slug), None
                )
                self.assertFalse(mock_fetch_flows.called)

                mock_cache_get.return_value = None
                self.assertEqual(get_flows(self.org, self.rapidpro_backend), "Fetched")
                mock_fetch_flows.assert_called_once_with(self.org, self.rapidpro_backend)

    @patch("django.core.cache.cache.get")
    def test_get_reporters_count(self, mock_cache_get):
        mock_cache_get.return_value = None

        self.assertEqual(get_reporters_count(self.org), 0)

        ReportersCounter.objects.create(org=self.org, type="total-reporters", count=5)

        self.assertEqual(get_reporters_count(self.org), 5)

    def test_get_global_count(self):
        with self.settings(
            CACHES={
                "default": {
                    "BACKEND": "django_valkey.cache.ValkeyCache",
                    "LOCATION": "redis://127.0.0.1:6379/1",
                }
            }
        ):
            with patch("ureport.utils.fetch_old_sites_count") as mock_old_sites_count:
                mock_old_sites_count.return_value = []

                self.assertEqual(get_global_count(), 0)

                mock_old_sites_count.return_value = [
                    {"time": 500, "results": dict(size=300)},
                    {"time": 500, "results": dict(size=50)},
                ]
                from django.core.cache import cache

                cache.delete(GLOBAL_COUNT_CACHE_KEY)
                cache.set("org:ignored:reporters:old-site", {"time": 500, "results": dict(size=100)}, None)
                self.assertEqual(get_global_count(), 350)

            with patch("django.core.cache.cache.get") as cache_get_mock:
                cache_get_mock.return_value = 20

                self.assertEqual(get_global_count(), 20)
                cache_get_mock.assert_called_once_with("global_count", None)
