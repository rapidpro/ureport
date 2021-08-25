from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCreateView, SmartCRUDL, SmartListView, SmartUpdateView

from ureport.topics.models import Topic


class TopicCRUDL(SmartCRUDL):
    model = Topic
    actions = ("create", "list", "update")

    class Create(OrgPermsMixin, SmartCreateView):
        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("name", "org")
            return ("name",)

        def pre_save(self, obj):
            obj = super(TopicCRUDL.Create, self).pre_save(obj)

            if not self.get_user().is_superuser:
                org = self.derive_org()
                if org:
                    obj.org = org

            return obj

    class Update(OrgObjPermsMixin, SmartUpdateView):
        fields = ("is_active", "name")

    class List(OrgPermsMixin, SmartListView):
        ordering = ("name",)

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ("name", "modified_on", "created_on", "org")
            return ("name", "modified_on", "created_on")

        def get_queryset(self, **kwargs):
            queryset = super(TopicCRUDL.List, self).get_queryset(**kwargs)
            queryset = queryset.filter(org=self.derive_org())

            return queryset
