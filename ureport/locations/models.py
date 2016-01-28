import json
from django.core.cache import cache
from django.db import models
from dash.orgs.models import Org
from django.utils.translation import ugettext_lazy as _


class Boundary(models.Model):
    """
    Corresponds to a RapidPro AdminBoundary
    """

    BOUNDARIES_CACHE_TIMEOUT = 60 * 60 * 24 * 15
    BOUNDARIES_CACHE_KEY = 'org:%d:boundaries-osm-ids'

    org = models.ForeignKey(Org, verbose_name=_("Organization"), related_name="boundaries")

    osm_id = models.CharField(max_length=15,
                              help_text=_("This is the OSM id for this administrative boundary"))

    name = models.CharField(max_length=128,
                            help_text=_("The name of our administrative boundary"))

    level = models.IntegerField(help_text=_("The level of the boundary, 0 for country, 1 for state, 2 for district"))

    parent = models.ForeignKey('locations.Boundary', null=True, related_name='children',
                               help_text=_("The parent to this political boundary if any"))

    geometry = models.TextField(verbose_name=_("Geometry"),
                                help_text=_("The json representing the geometry type and coordinates of the boundaries"))

    class Meta:
        unique_together = ('org', 'osm_id')

    @classmethod
    def kwargs_from_temba(cls, org, temba_boundary):

        geometry = json.dumps(dict(type=temba_boundary.geometry.type, coordinates=temba_boundary.geometry.coordinates))

        parent = cls.objects.filter(osm_id__iexact=temba_boundary.parent, org=org).first()

        return dict(org=org, geometry=geometry, parent=parent, level=temba_boundary.level,
                    name=temba_boundary.name, osm_id=temba_boundary.boundary)

    @classmethod
    def update_or_create_from_temba(cls, org, temba_boundary):
        kwargs = cls.kwargs_from_temba(org, temba_boundary)

        existing = cls.objects.filter(org=org, osm_id=kwargs['osm_id'])
        if existing:
            existing.update(**kwargs)
            return existing.first()
        else:
            return cls.objects.create(**kwargs)

    @classmethod
    def build_global_boundaries(cls):

        from django.conf import settings
        from temba_client.v1.types import Geometry as TembaGeometry, Boundary as TembaBoundary
        handle = open('%s/geojson/countries.json' % settings.MEDIA_ROOT, 'r+')
        contents = handle.read()
        handle.close()

        boundaries_json = json.loads(contents)

        boundaries = []
        for elt in boundaries_json['features']:
            temba_geometry = TembaGeometry.create(type=elt['geometry']['type'],
                                                  coordinates=elt['geometry']['coordinates'])

            temba_boundary = TembaBoundary.create(level=0, name=elt['properties']['name'],
                                                  boundary=elt['properties']['hc-a2'], geometry=temba_geometry)

            boundaries.append(temba_boundary)

        return boundaries

    @classmethod
    def fetch_boundaries(cls, org):

        if org.get_config('is_global'):
            api_boundaries = cls.build_global_boundaries()
        else:
            temba_client = org.get_temba_client()
            api_boundaries = temba_client.get_boundaries()

        seen_ids = []

        for boundary in api_boundaries:
            cls.update_or_create_from_temba(org, boundary)
            seen_ids.append(boundary.boundary)

        # remove any boundary that's no longer on rapidpro
        cls.objects.filter(org=org).exclude(osm_id__in=seen_ids).delete()

        key = cls.BOUNDARIES_CACHE_KEY % org.id
        cache.set(key, seen_ids, cls.BOUNDARIES_CACHE_TIMEOUT)

        return seen_ids

    @classmethod
    def get_boundaries(cls, org):
        key = cls.BOUNDARIES_CACHE_KEY % org.id

        boundary_ids = cache.get(key, None)
        if boundary_ids:
            return boundary_ids

        boundary_ids = cls.fetch_boundaries(org)
        return boundary_ids

    def as_geojson(self):
        return dict(type='Feature', geometry=json.loads(self.geometry),
                    properties=dict(id=self.osm_id, level=self.level, name=self.name))

    @classmethod
    def get_org_top_level_boundaries_name(cls, org):
        if org.get_config('is_global'):
            top_boundaries = cls.objects.filter(org=org, level=0)
        else:
            top_boundaries = cls.objects.filter(org=org, level=1)

        top_boundaries_values = top_boundaries.values('name', 'osm_id')

        return {k['osm_id']: k['name'] for k in top_boundaries_values}
