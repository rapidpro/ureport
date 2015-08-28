import json
from django.db import models
from dash.orgs.models import Org
from django.utils.translation import ugettext_lazy as _

# Create your models here.


class Boundary(models.Model):
    """
    Corresponds to a RapidPro AdminBoundary
    """
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
    def fetch_boundaries(cls, org):
        temba_client = org.get_temba_client()
        api_boundaries = temba_client.get_boundaries()

        seen_ids = []

        for boundary in api_boundaries:
            cls.update_or_create_from_temba(org, boundary)
            seen_ids.append(boundary.boundary)

        # remove any boundary that's no longer on rapidpro
        cls.objects.filter(org=org).exclude(osm_id__in=seen_ids).delete()
