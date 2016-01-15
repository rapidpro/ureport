import json
from ureport.tests import DashTest, MockTembaClient
from mock import patch
from temba_client.types import Boundary as TembaBoundary, Geometry as TembaGeometry
from .models import Boundary


class LocationTest(DashTest):
    def setUp(self):
        super(LocationTest, self).setUp()
        self.nigeria = self.create_org('nigeria', self.admin)

    def test_kwargs_from_temba(self):
        geometry = TembaGeometry.create(type='MultiPolygon', coordinates=['COORDINATES'])
        country = TembaBoundary.create(boundary='R12345', name='Nigeria', parent=None, level=0, geometry=geometry)

        kwargs = Boundary.kwargs_from_temba(self.nigeria, country)
        self.assertEqual(kwargs, dict(org=self.nigeria, osm_id="R12345", name="Nigeria", level=0, parent=None,
                                      geometry=json.dumps(dict(type='MultiPolygon', coordinates=['COORDINATES']))))

        # try creating an object from the kwargs
        country_boundary = Boundary.objects.create(**kwargs)

        state = TembaBoundary.create(boundary='R23456', name='Lagos', parent="R12345", level=1, geometry=geometry)
        kwargs = Boundary.kwargs_from_temba(self.nigeria, state)
        self.assertEqual(kwargs, dict(org=self.nigeria, osm_id="R23456", name="Lagos", level=1, parent=country_boundary,
                                      geometry=json.dumps(dict(type='MultiPolygon', coordinates=['COORDINATES']))))

        # try creating an object from the kwargs
        Boundary.objects.create(**kwargs)

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
    def test_fetch_boundaries(self):

        # Old boundary should be deleted after we fetch boundaries
        old_boundary = Boundary.objects.create(org=self.nigeria, osm_id='OLD123', name='OLD', parent=None, level=0,
                                               geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}')

        Boundary.fetch_boundaries(self.nigeria)
        self.assertIsNone(Boundary.objects.filter(org=self.nigeria, osm_id__iexact='OLD123').first())

        self.assertEqual(Boundary.objects.all().count(), 2)

        country_boundary = Boundary.objects.get(level=0)
        self.assertEqual(country_boundary.name, "Nigeria")
        self.assertEqual(country_boundary.osm_id, 'R12345')
        self.assertIsNone(country_boundary.parent)
        self.assertEqual(country_boundary.geometry, json.dumps(dict(type='MultiPolygon', coordinates=['COORDINATES'])))

        state_boundary = Boundary.objects.get(level=1)
        self.assertEqual(state_boundary.name, "Lagos")
        self.assertEqual(state_boundary.osm_id, 'R23456')
        self.assertEqual(state_boundary.parent, country_boundary)
        self.assertEqual(state_boundary.geometry, json.dumps(dict(type='MultiPolygon', coordinates=['COORDINATES'])))

        self.assertEqual(country_boundary.as_geojson(),
                         dict(type='Feature', geometry=dict(type='MultiPolygon', coordinates=['COORDINATES']),
                              properties=dict(id='R12345', level=0, name='Nigeria')))

        self.assertEqual(state_boundary.as_geojson(),
                         dict(type='Feature', geometry=dict(type='MultiPolygon', coordinates=['COORDINATES']),
                              properties=dict(id='R23456', level=1, name='Lagos')))

        with patch('ureport.locations.models.Boundary.build_global_boundaries') as mock_global_boundaries:
            mock_global_boundaries.return_value = []

            Boundary.fetch_boundaries(self.nigeria)
            self.assertFalse(mock_global_boundaries.called)

            self.nigeria.set_config('is_global', True)

            Boundary.fetch_boundaries(self.nigeria)
            self.assertTrue(mock_global_boundaries.called)
            mock_global_boundaries.assert_called_once()

    @patch('dash.orgs.models.TembaClient', MockTembaClient)
    def test_get_boundaries(self):

        boundaries_ids = Boundary.get_boundaries(self.nigeria)
        self.assertEqual(boundaries_ids, ['R12345', 'R23456'])

        with patch('django.core.cache.cache.get') as cache_get_mock:
            cache_get_mock.return_value = None

            boundaries_ids = Boundary.get_boundaries(self.nigeria)
            self.assertEqual(boundaries_ids, ['R12345', 'R23456'])

            cache_get_mock.return_value = ['R12345', 'R23456']

            with patch('ureport.locations.models.Boundary.fetch_boundaries') as mock_fetch:

                Boundary.get_boundaries(self.nigeria)
                self.assertFalse(mock_fetch.called)

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