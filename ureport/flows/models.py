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
        obj = cls.objects.filter(org=org, flow_uuid=flow_uuid, result_uuid=result_uuid).first()

        if obj:
            obj.result_name = result_name
            obj.save(update_fields=("result_name",))
        else:
            obj = FlowResult.objects.create(
                org=org, flow_uuid=flow_uuid, result_uuid=result_uuid, result_name=result_name
            )

        return obj

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "flow_uuid", "result_uuid"],
                name="flows_flowresult_org_id_flow_uuid_result_uuid_5efa8f2d_uniq",
            )
        ]


class FlowResultCategory(models.Model):
    is_active = models.BooleanField(default=True)

    flow_result = models.ForeignKey(FlowResult, on_delete=models.PROTECT, related_name="result_categories")

    category = models.TextField(null=True)

    @classmethod
    def update_or_create(cls, flow_result, category):
        obj = cls.objects.filter(flow_result=flow_result, category=category).first()

        if obj:
            obj.is_active = True
            obj.save(update_fields=("is_active",))
        else:
            obj = cls.objects.create(flow_result=flow_result, category=category, is_active=True)
        return obj
