from dash.orgs.views import OrgObjPermsMixin, OrgPermsMixin
from smartmin.views import SmartCRUDL, SmartUpdateView, SmartListView, SmartCreateView
from ureport.assets.models import Background


class BackgroundCRUDL(SmartCRUDL):
    model = Background
    actions = ('create', 'update', 'list')

    class Update(OrgObjPermsMixin, SmartUpdateView):
        fields = ('is_active', 'name', 'background_type', 'image')

    class List(OrgPermsMixin, SmartListView):
        fields = ("name", "background_type")

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ('org', 'name', 'background_type')
            return ('name', 'background_type')

        def get_background_type(self, obj):
            return obj.get_background_type_display()

        def get_queryset(self, **kwargs):
            queryset = super(BackgroundCRUDL.List, self).get_queryset(**kwargs)

            if not self.get_user().is_superuser:
                queryset = queryset.filter(org=self.derive_org())

            return queryset

    class Create(OrgPermsMixin, SmartCreateView):

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ('org', 'name', 'background_type', 'image')
            return ('name', 'background_type', 'image')

        def pre_save(self, obj):
            obj = super(BackgroundCRUDL.Create, self).pre_save(obj)

            if not self.get_user().is_superuser:
                org = self.derive_org()
                if org:
                    obj.org = org

            return obj

