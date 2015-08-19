from dash.orgs.models import Org
from dash.stories.models import Story
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView, RetrieveAPIView
from smartmin.views import SmartCRUDL, SmartListView
from ureport.api.serializers import PollReadSerializer, NewsItemReadSerializer, VideoReadSerializer, ImageReadSerializer, \
    OrgReadSerializer, StoryReadSerializer
from ureport.assets.models import Image
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll

__author__ = 'kenneth'


class TokenCRUDL(SmartCRUDL):
    model = Token
    actions = ('list', )

    class List(SmartListView):
        search_fields = ('user__username__icontains','user__first_name__icontains', 'user__last_name__icontains')
        fields = ('user', 'key')


class OrgList(ListAPIView):
    serializer_class = OrgReadSerializer
    queryset = Org.objects.all()


class OrgDetails(RetrieveAPIView):
    serializer_class = OrgReadSerializer
    queryset = Org.objects.all()


class BaseListAPIView(ListAPIView):
    def get_queryset(self):
        q = self.model.objects.all()
        if self.kwargs.get('org', None):
            q = q.filter(org__id=self.kwargs.get('org'))
        return q


class PollList(BaseListAPIView):
    serializer_class = PollReadSerializer
    model = Poll

    def get_queryset(self):
        q = super(PollList, self).get_queryset()
        if self.request.query_params.get('flow_uuid', None):
            q = q.filter(flow_uuid=self.request.query_params.get('flow_uuid'))
        return q


class PollDetails(RetrieveAPIView):
    serializer_class = PollReadSerializer
    queryset = Poll.objects.all()


class NewsItemList(BaseListAPIView):
    serializer_class = NewsItemReadSerializer
    model = NewsItem


class NewsItemDetails(RetrieveAPIView):
    serializer_class = NewsItemReadSerializer
    queryset = NewsItem.objects.all()


class VideoList(BaseListAPIView):
    serializer_class = VideoReadSerializer
    model = Video


class VideoDetails(RetrieveAPIView):
    serializer_class = VideoReadSerializer
    queryset = Video.objects.all()


class ImageList(BaseListAPIView):
    serializer_class = ImageReadSerializer
    model = Image


class ImageDetails(RetrieveAPIView):
    serializer_class = ImageReadSerializer
    queryset = Image.objects.all()


class StoryList(BaseListAPIView):
    serializer_class = StoryReadSerializer
    model = Story


class StoryDetails(RetrieveAPIView):
    serializer_class = StoryReadSerializer
    queryset = Story.objects.all()


