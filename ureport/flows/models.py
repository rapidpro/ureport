from django.db import models

from dash.orgs.models import Org

# Create your models here.

class FlowResult(models.Model):
    is_active = models.BooleanField(default=True)

    org = models.ForeignKey(Org, on_delete=models.PROTECT)

    flow_uuid = models.CharField(max_length=36)

    result_uuid = models.CharField(max_length=36)

    result_name = models.CharField(max_length=255, null=True, blank=True)

    @classmethod
    def update_or_create(cls, org, flow_uuid, result_uuid, result_name):
        existing = cls.objects.filter(org=org, flow_uuid=flow_uuid, result_uuid=result_uuid)

        if existing:
            existing.update(result_name=result_name)
            obj = existing.first()
        else:
            obj = FlowResult.objects.create(org=org, low_uuid=flow_uuid, result_uuid=result_uuid, result_name=result_name)

        return obj

    class Meta:
        unique_together = ("org", "flow_uuid",  "result_uuid")

class FlowResultCategory(models.Model):
    is_active = models.BooleanField(default=True)
    
    flow_result = models.ForeignKey(FlowResult, on_delete=models.PROTECT, related_name="result_categories")

    category = models.TextField(null=True)

    @classmethod
    def update_or_create(cls, flow_result, category):
        existing = cls.objects.filter(flow_result=flow_result, category=category)

        if existing:
            existing.update(is_active=True)
        else:
            existing = cls.objects.create(flow_result=flow_result, category=category, is_active=True)
        return existing