import json
from django.core.cache import cache
from django.db import models
from dash.orgs.models import Org
from django.utils.translation import ugettext_lazy as _

from django_redis import get_redis_connection

BOUNDARY_LOCK_KEY = 'lock:boundary:%d:%s'


class Boundary(models.Model):
    """
    Corresponds to a RapidPro AdminBoundary
    """
    COUNTRY_LEVEL = 0
    STATE_LEVEL = 1
    DISTRICT_LEVEL = 2
    WARD_LEVEL = 3

    BOUNDARIES_CACHE_TIMEOUT = 60 * 60 * 24 * 15
    BOUNDARIES_CACHE_KEY = 'org:%d:boundaries-osm-ids'

    org = models.ForeignKey(Org, verbose_name=_("Organization"), related_name="boundaries")

    is_active = models.BooleanField(default=True)

    backend = models.CharField(max_length=16, default='rapidpro')

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
    def lock(cls, org, osm_id):
        return get_redis_connection().lock(BOUNDARY_LOCK_KEY % (org.pk, osm_id), timeout=60)

    @classmethod
    def build_global_boundaries(cls):

        from django.conf import settings
        from temba_client.v2.types import Boundary as TembaBoundary
        handle = open('%s/geojson/countries.json' % settings.MEDIA_ROOT, 'r+')
        contents = handle.read()
        handle.close()

        boundaries_json = json.loads(contents)

        boundaries = []
        for elt in boundaries_json['features']:
            temba_geometry = TembaBoundary.Geometry.create(type=elt['geometry']['type'],
                                                           coordinates=elt['geometry']['coordinates'])

            temba_boundary = TembaBoundary.create(level=0, name=elt['properties']['name'], aliases=None,
                                                  osm_id=elt['properties']['hc-a2'], geometry=temba_geometry)

            boundaries.append(temba_boundary)

        return boundaries

    def as_geojson(self):
        return dict(type='Feature', geometry=json.loads(self.geometry),
                    properties=dict(id=self.osm_id, level=self.level, name=self.name))

    @classmethod
    def get_org_top_level_boundaries_name(cls, org):
        if org.get_config('is_global'):
            top_boundaries = cls.objects.filter(org=org, level=cls.COUNTRY_LEVEL)
        else:
            top_boundaries = cls.objects.filter(org=org, level=cls.STATE_LEVEL)

        top_boundaries_values = top_boundaries.values('name', 'osm_id')

        return {k['osm_id']: k['name'] for k in top_boundaries_values}

    def release(self):
        self.delete()
