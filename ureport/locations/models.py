# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json

from django_redis import get_redis_connection

from django.db import models
from django.utils.translation import gettext_lazy as _

from dash.orgs.models import Org, OrgBackend

BOUNDARY_LOCK_KEY = "lock:boundary:%d:%s"


class Boundary(models.Model):
    """
    Corresponds to a RapidPro AdminBoundary
    """

    COUNTRY_LEVEL = 0
    STATE_LEVEL = 1
    DISTRICT_LEVEL = 2
    WARD_LEVEL = 3

    BOUNDARIES_CACHE_TIMEOUT = 60 * 60 * 24 * 15
    BOUNDARIES_CACHE_KEY = "org:%d:boundaries-osm-ids"

    org = models.ForeignKey(Org, on_delete=models.PROTECT, verbose_name=_("Organization"), related_name="boundaries")

    is_active = models.BooleanField(default=True)

    backend = models.ForeignKey(OrgBackend, on_delete=models.PROTECT, null=True)

    osm_id = models.CharField(max_length=15, help_text=_("This is the OSM id for this administrative boundary"))

    name = models.CharField(max_length=128, help_text=_("The name of our administrative boundary"))

    level = models.IntegerField(help_text=_("The level of the boundary, 0 for country, 1 for state, 2 for district"))

    parent = models.ForeignKey(
        "locations.Boundary",
        null=True,
        on_delete=models.PROTECT,
        related_name="children",
        help_text=_("The parent to this political boundary if any"),
    )

    geometry = models.TextField(
        verbose_name=_("Geometry"),
        help_text=_("The json representing the geometry type and coordinates of the boundaries"),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org", "osm_id"], name="locations_boundary_org_id_5c2d99160b82334a_uniq")
        ]
        indexes = [
            models.Index(name=None, fields=["org", "level", "name", "osm_id"]),
        ]

    @classmethod
    def lock(cls, org, osm_id):
        return get_redis_connection().lock(BOUNDARY_LOCK_KEY % (org.pk, osm_id), timeout=60)

    @classmethod
    def build_global_boundaries(cls):
        from temba_client.v2.types import Boundary as TembaBoundary

        from django.conf import settings

        handle = open("%s/geojson/countries.json" % settings.MEDIA_ROOT, "r+")
        contents = handle.read()
        handle.close()

        boundaries_json = json.loads(contents)
        boundaries = []
        for elt in boundaries_json["features"]:
            temba_geometry = TembaBoundary.Geometry.create(
                type=elt["geometry"]["type"], coordinates=elt["geometry"]["coordinates"]
            )

            temba_boundary = TembaBoundary.create(
                level=0,
                name=elt["properties"]["NAME"],
                aliases=None,
                osm_id=elt["properties"]["ISO_A2"],
                geometry=temba_geometry,
            )

            boundaries.append(temba_boundary)

        return boundaries

    def as_geojson(self):
        return dict(
            type="Feature",
            geometry=json.loads(self.geometry),
            properties=dict(id=self.osm_id, level=self.level, name=self.name),
        )

    @classmethod
    def get_org_top_level_boundaries_name(cls, org):
        if org.get_config("common.is_global"):
            top_boundaries = cls.objects.filter(org=org, level=cls.COUNTRY_LEVEL)
            limit_states = org.get_config("common.limit_poll_states")
            if limit_states:
                limit_states = [elt.strip() for elt in limit_states.split(",")]
                top_boundaries = top_boundaries.filter(osm_id__in=limit_states)
        else:
            # just listing states that are limited
            limit_states = org.get_config("common.limit_poll_states")
            if limit_states:
                limit_states = [elt.strip() for elt in limit_states.split(",")]
                top_boundaries = cls.objects.filter(org=org, level=cls.STATE_LEVEL, name__in=limit_states)
            else:
                top_boundaries = cls.objects.filter(org=org, level=cls.STATE_LEVEL)

        top_boundaries_values = top_boundaries.values("name", "osm_id")

        return {k["osm_id"]: k["name"] for k in top_boundaries_values}

    def release(self):
        self.delete()
