from .models import *
from smartmin.views import *
from django import forms
from dash.orgs.views import OrgPermsMixin, OrgObjPermsMixin

class StoryCRUDL(SmartCRUDL):
    model = Story
    actions = ('create', 'update', 'list')

    class Update(OrgObjPermsMixin, SmartUpdateView):
        fields = ('is_active', 'title', 'featured', 'summary', 'content', 'image', 'video_id', 'tags', 'category')

    class List(OrgPermsMixin, SmartListView):
        fields = ('title', 'featured', 'modified_on')


        def get_featured(self, obj):
            if obj.featured:
                return "Yes"
            return "No"

        def get_queryset(self, **kwargs):
            queryset = super(StoryCRUDL.List, self).get_queryset(**kwargs)

            if not self.get_user().is_superuser:
                queryset = queryset.filter(org=self.derive_org())

            return queryset


    class Create(OrgPermsMixin, SmartCreateView):

        def pre_save(self, obj):
            obj = super(StoryCRUDL.Create, self).pre_save(obj)

            org = self.derive_org()
            if org:
                obj.org = org

            obj.space_tags()
            return obj

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ('title', 'featured', 'summary', 'content', 'image', 'video_id', 'tags', 'category', 'org')
            return ('title', 'featured', 'summary', 'content', 'image', 'video_id', 'tags', 'category')
