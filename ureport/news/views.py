from dash.orgs.views import OrgPermsMixin, OrgObjPermsMixin
from smartmin.views import SmartCRUDL, SmartCreateView, SmartListView, SmartUpdateView
from .models import NewsItem, Video

class NewsItemCRUDL(SmartCRUDL):
    model = NewsItem
    actions = ('create', 'update', 'list')

    class Update(OrgObjPermsMixin, SmartUpdateView):
        fields = ('is_active', 'title', 'description', 'link', 'category')

    class List(OrgPermsMixin, SmartListView):
        fields = ('title', 'link', 'category')

        def get_queryset(self, **kwargs):
            queryset = super(NewsItemCRUDL.List, self).get_queryset(**kwargs)

            if not self.get_user().is_superuser:
                queryset = queryset.filter(org=self.derive_org())

            return queryset


    class Create(OrgPermsMixin, SmartCreateView):

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ('title', 'description', 'link', 'category', 'org')
            return ('title', 'description', 'link', 'category')

        def pre_save(self, obj):
            obj = super(NewsItemCRUDL.Create, self).pre_save(obj)

            org = self.derive_org()
            if org:
                obj.org = org

            return obj


class VideoCRUDL(SmartCRUDL):
    model = Video
    actions = ('create', 'update', 'list')

    class Update(OrgObjPermsMixin, SmartUpdateView):
        fields = ('is_active', 'title', 'description', 'video_id', 'category')

    class List(OrgPermsMixin, SmartListView):
        fields = ('title', 'video_id', 'category')

        def get_queryset(self, **kwargs):
            queryset = super(VideoCRUDL.List, self).get_queryset(**kwargs)

            if not self.get_user().is_superuser:
                queryset = queryset.filter(org=self.derive_org())

            return queryset


    class Create(OrgPermsMixin, SmartCreateView):

        def derive_fields(self):
            if self.request.user.is_superuser:
                return ('title', 'description', 'video_id', 'category', 'org')
            return ('title', 'description', 'video_id', 'category')

        def pre_save(self, obj):
            obj = super(VideoCRUDL.Create, self).pre_save(obj)

            org = self.derive_org()
            if org:
                obj.org = org

            return obj