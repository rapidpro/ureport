# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json

from mock import Mock, patch

from django.urls import reverse

from ureport.tests import UreportTest

from .models import Boundary


class LocationTest(UreportTest):
    def setUp(self):
        super(LocationTest, self).setUp()

    def test_get_org_top_level_boundaries_name(self):
        self.assertEqual(Boundary.get_org_top_level_boundaries_name(self.nigeria), dict())

        Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-NIGERIA",
            name="Nigeria",
            parent=None,
            level=0,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-LAGOS",
            name="Lagos",
            parent=None,
            level=1,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-OYO",
            name="OYO",
            parent=None,
            level=1,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        Boundary.objects.create(
            org=self.nigeria,
            osm_id="R-ABUJA",
            name="Abuja",
            parent=None,
            level=1,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        expected = dict()
        expected["R-LAGOS"] = "Lagos"
        expected["R-ABUJA"] = "Abuja"
        expected["R-OYO"] = "OYO"

        self.assertEqual(Boundary.get_org_top_level_boundaries_name(self.nigeria), expected)

        self.nigeria.set_config("common.is_global", True)

        expected = dict()
        expected["R-NIGERIA"] = "Nigeria"

        self.assertEqual(Boundary.get_org_top_level_boundaries_name(self.nigeria), expected)

        self.assertEqual(reverse("public.boundaries", args=["R-Nigeria"]), "/boundaries/R-Nigeria/")
        self.assertEqual(reverse("public.boundaries", args=["232_23"]), "/boundaries/232_23/")
        self.assertEqual(reverse("public.boundaries", args=["COD.16_1"]), "/boundaries/COD.16_1/")
        self.assertEqual(reverse("public.boundaries", args=["COD.16_1_2"]), "/boundaries/COD.16_1_2/")

    def test_build_global_boundaries(self):
        with patch("ureport.locations.models.open") as my_mock:
            my_mock.return_value.__enter__ = lambda s: s
            my_mock.return_value.__exit__ = Mock()
            my_mock.return_value.read.return_value = json.dumps(
                dict(
                    features=[
                        {
                            "type": "Feature",
                            "id": "DK",
                            "properties": {"NAME": "Denmark", "ISO_A2": "DK"},
                            "geometry": {"type": "MultiPolygon", "coordinates": [[[[1, 2], [3, 4]]]]},
                        },
                        {
                            "type": "Feature",
                            "id": "FO",
                            "properties": {"NAME": "Faroe Islands", "ISO_A2": "FO"},
                            "geometry": {"type": "Polygon", "coordinates": [[[5, 6], [7, 8]]]},
                        },
                    ]
                )
            )

            boundaries = Boundary.build_global_boundaries()
            danemark = boundaries[0]
            faroe = boundaries[1]

            self.assertEqual(danemark.osm_id, "DK")
            self.assertEqual(danemark.name, "Denmark")
            self.assertEqual(danemark.level, 0)
            self.assertEqual(danemark.geometry.type, "MultiPolygon")
            self.assertEqual(danemark.geometry.coordinates, [[[[1, 2], [3, 4]]]])

            self.assertEqual(faroe.osm_id, "FO")
            self.assertEqual(faroe.name, "Faroe Islands")
            self.assertEqual(faroe.level, 0)
            self.assertEqual(faroe.geometry.type, "Polygon")
            self.assertEqual(faroe.geometry.coordinates, [[[5, 6], [7, 8]]])
