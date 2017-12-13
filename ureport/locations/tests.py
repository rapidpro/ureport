import json

from ureport.tests import UreportTest
from mock import patch, Mock
from .models import Boundary


class LocationTest(UreportTest):
    def setUp(self):
        super(LocationTest, self).setUp()

    def test_get_org_top_level_boundaries_name(self):

        self.assertEqual(Boundary.get_org_top_level_boundaries_name(self.nigeria), dict())

        Boundary.objects.create(org=self.nigeria, osm_id='R-NIGERIA', name='Nigeria', parent=None, level=0,
                                geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        Boundary.objects.create(org=self.nigeria, osm_id='R-LAGOS', name='Lagos', parent=None, level=1,
                                geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        Boundary.objects.create(org=self.nigeria, osm_id='R-OYO', name='OYO', parent=None, level=1,
                                geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        Boundary.objects.create(org=self.nigeria, osm_id='R-ABUJA', name='Abuja', parent=None, level=1,
                                geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        expected = dict()
        expected['R-LAGOS'] = "Lagos"
        expected['R-ABUJA'] = "Abuja"
        expected['R-OYO'] = "OYO"

        self.assertEqual(Boundary.get_org_top_level_boundaries_name(self.nigeria), expected)

        self.nigeria.set_config('is_global', True)

        expected = dict()
        expected['R-NIGERIA'] = "Nigeria"

        self.assertEqual(Boundary.get_org_top_level_boundaries_name(self.nigeria), expected)

    def test_build_global_boundaries(self):
        with patch('__builtin__.open') as my_mock:
            my_mock.return_value.__enter__ = lambda s: s
            my_mock.return_value.__exit__ = Mock()
            my_mock.return_value.read.return_value = json.dumps(dict(features=[{"type": "Feature",
                                              "id": "DK",
                                              "properties": {"hc-group": "admin0",
                                                             "hc-middle-x": 0.28,
                                                             "hc-middle-y": 0.52,
                                                             "hc-key": "dk",
                                                             "hc-a2": "DK",
                                                             "name": "Denmark",
                                                             "labelrank": "4",
                                                             "country-abbrev": "Den.",
                                                             "subregion": "Northern Europe",
                                                             "woe-id": "23424796",
                                                             "region-wb": "Europe & Central Asia",
                                                             "iso-a3": "DNK",
                                                             "iso-a2": "DK",
                                                             "region-un": "Europe",
                                                             "continent": "Europe"},
                                              "geometry": {"type": "MultiPolygon",
                                                           "coordinates": [[[[1, 2], [3, 4]]]]}},
                                             {"type":"Feature",
                                              "id": "FO",
                                              "properties": {"hc-group": "admin0",
                                                             "hc-middle-x": 0.5,
                                                             "hc-middle-y": 0.41,
                                                             "hc-key": "fo",
                                                             "hc-a2": "FO",
                                                             "name": "Faroe Islands",
                                                             "labelrank": "6",
                                                             "country-abbrev": "Faeroe Is.",
                                                             "subregion": "Northern Europe",
                                                             "woe-id": "23424816",
                                                             "region-wb": "Europe & Central Asia",
                                                             "iso-a3": "FRO",
                                                             "iso-a2": "FO",
                                                             "region-un": "Europe",
                                                             "continent": "Europe"},
                                              "geometry": {"type": "Polygon",
                                                           "coordinates": [[[5, 6], [7, 8]]]}}]))

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
