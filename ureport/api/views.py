from dash.orgs.models import Org
from dash.stories.models import Story
from rest_framework.generics import ListAPIView, RetrieveAPIView
from ureport.api.serializers import PollReadSerializer, NewsItemReadSerializer, VideoReadSerializer, ImageReadSerializer, \
    OrgReadSerializer, StoryReadSerializer
from ureport.assets.models import Image
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll

__author__ = 'kenneth'


class OrgList(ListAPIView):
    """
    This endpoint allows you to list orgs.

    ## Listing Polls

    By making a ```GET``` request you can list all the organisations.  Each org has the following attributes:

    * **id** - the ID of the org (int)
    * **logo_url** - the LOGO_URL of the org (string)
    * **name** - the NAME of the org (string)
    * **language** - the LANGUAGE of the org (string)
    * **subdomain** - the SUBDOMAIN of of this org (string)
    * **domain** - the DOMAIN of of this org (string)
    * **timezone** - the TIMEZONE of of this org (string)

    Example:

        GET /api/v1/orgs/

    Response is the list of orgs:

        {
            "count": 389,
            "next": "/api/v1/polls/orgs/?page=2",
            "previous": null,
            "results": [
            {
                "id": 1,
                "logo_url": "http://test.ureport.in/media/logos/StraightOuttaSomewhere_2.jpg",
                "name": "test",
                "language": "en",
                "subdomain": "test",
                "domain": "ureport.in",
                "timezone": "Africa/Kampala"
                "gender_stats": {
                    "female_count": 0,
                    "male_percentage": "---",
                    "female_percentage": "---",
                    "male_count": 0
                },
                "age_stats": [],
                "registration_stats": [{"count": 0, "label": "07/06/15"}],
                "occupation_stats": []
            },
            ...
        }
    """
    serializer_class = OrgReadSerializer
    queryset = Org.objects.filter(is_active=True)


class OrgDetails(RetrieveAPIView):
    """
    This endpoint allows you to get a single org.

    ## Get a single org

    Example:

        GET /api/v1/orgs/1/

    Response is a single org with that ID:

        {
            "id": 1,
            "logo_url": "http://test.ureport.in/media/logos/StraightOuttaSomewhere_2.jpg",
            "name": "test",
            "language": "en",
            "subdomain": "test",
            "domain": "ureport.in",
            "timezone": "Africa/Kampala"
            "gender_stats": {
                    "female_count": 0,
                    "male_percentage": "---",
                    "female_percentage": "---",
                    "male_count": 0
                },
            "age_stats": [],
            "registration_stats": [{"count": 0, "label": "07/06/15"}],
            "occupation_stats": []
        }
    """
    serializer_class = OrgReadSerializer
    queryset = Org.objects.filter(is_active=True)


class BaseListAPIView(ListAPIView):
    def get_queryset(self):
        q = self.model.objects.filter(is_active=True)
        if self.kwargs.get('org', None):
            q = q.filter(org_id=self.kwargs.get('org'))
        return q


class PollList(BaseListAPIView):
    """
    This endpoint allows you to list polls.

    ## Listing Polls

    By making a ```GET``` request you can list all the polls for an organization, filtering them as needed.  Each
    poll has the following attributes:

    * **id** - the ID of the poll (int)
    * **flow_uuid** - the FLOW_UUID of the run (string) (filterable: ```flow_uuid```)
    * **title** - the TITLE of the poll (string)
    * **org** - the ID of the org that owns this poll (int)
    * **category** - the CATEGORIES of of this poll (dictionary)

    Example:

        GET /api/v1/polls/org/1/

    Response is the list of polls on the flow, most recent first:

        {
            "count": 389,
            "next": "/api/v1/polls/org/1/?page=2",
            "previous": null,
            "results": [
            {
                "id": 1,
                "flow_uuid": "a22991df-6d84-4b94-b6da-7b00086a2023",
                "title": "test",
                "org": 1,
                "category": {
                    "image_url": "http://fake.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                    "name": "tests"
                }
            },
            ...
        }
    """
    serializer_class = PollReadSerializer
    model = Poll

    def get_queryset(self):
        q = super(PollList, self).get_queryset()
        if self.request.query_params.get('flow_uuid', None):
            q = q.filter(flow_uuid=self.request.query_params.get('flow_uuid'))
        return q


class PollDetails(RetrieveAPIView):
    """
    This endpoint allows you to get a single poll.

    ## Get a single poll

    Example:

        GET /api/v1/polls/1/

    Response is a single poll with that ID:

        {
            "id": 1,
            "flow_uuid": "a22991df-6d84-4b94-b6da-7b00086a2023",
            "title": "test",
            "org": 1,
            "category": {
                "image_url": "http://fake.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                "name": "tests"
            }
        }
    """
    serializer_class = PollReadSerializer
    queryset = Poll.objects.filter(is_active=True)


class FeaturedPollList(BaseListAPIView):
    """
    This endpoint allows you to list all featured polls for an organisation.

    ## Listing Featured Polls

    Example:

        GET /api/v1/polls/org/1/featured/

    Response is a list of the featured polls, most recent first. \
    An empty list is returned if there are no polls with questions.

        {
            "count": 2,
            "next": "/api/v1/polls/org/1/featured",
            "previous": null,
            "results": [
            {
                "id": 1,
                "flow_uuid": "a22991df-6d84-4b94-b6da-7b00086a2023",
                "title": "test",
                "org": 1,
                "category": {
                    "image_url": "http://fake.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                    "name": "tests"
                }
            },
            {
                "id": 2,
                "flow_uuid": "8d82bac4-0f11-4dfa-822b-50a4d76c8998",
                "title": "the featured poll",
                "org": 1,
                "category": {
                    "image_url": null,
                    "name": "some category name"
                }
            }
        }
    """
    serializer_class = PollReadSerializer
    model = Poll

    def get_queryset(self):
        q = super(FeaturedPollList, self).get_queryset().filter(is_featured=True).order_by('-created_on')
        return q


class NewsItemList(BaseListAPIView):
    """
    This endpoint allows you to list news items.

    ## Listing news items

    By making a ```GET``` request you can list all the news items for an organization, filtering them as needed.  Each
    news item has the following attributes:

    * **id** - the ID of the item (int)
    * **short_description** - the SHORT_DESCRIPTION of the news item (string)
    * **title** - the TITLE of the news item (string)
    * **org** - the ID of the org that owns this news item (int)
    * **link** - the link to the source of this news item (string)
    * **category** - the CATEGORY of of this news item (dictionary)

    Example:

        GET /api/v1/news/org/1/

    Response is the list of news items of the organisation, most recent first:

        {
            "count": 389,
            "next": "/api/v1/news/org/1/?page=2",
            "previous": null,
            "results": [
            {
                "id": 1,
                "short_description": "This is a test news item that I want to use to test my api and speed of typing",
                "title": "test",
                "description": "This is a test news item that I want to use to test my api and speed of typing",
                "link": "http://stackoverflow.com/questions/3876977/update-git-branches-from-master",
                "org": 1,
                "category": {
                    "image_url": "http://fake.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                    "name": "tests"
                }
            },
            ...
        }
    """
    serializer_class = NewsItemReadSerializer
    model = NewsItem


class NewsItemDetails(RetrieveAPIView):
    """
    This endpoint allows you to get a single news item

    ## A single news item
    Example:

        GET /api/v1/news/1/

    Response is a single news item:

        {
            "id": 1,
            "short_description": "This is a test news item that I want to use to test my api and speed of typing",
            "title": "test",
            "description": "This is a test news item that I want to use to test my api and speed of typing",
            "link": "http://stackoverflow.com/questions/3876977/update-git-branches-from-master",
            "org": 1,
            "category": {
                "image_url": "http://fake.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                "name": "tests"
            }
        }
    """
    serializer_class = NewsItemReadSerializer
    queryset = NewsItem.objects.filter(is_active=True)


class VideoList(BaseListAPIView):
    """
    This endpoint allows you to list videos.

    ## Listing videos

    By making a ```GET``` request you can list all the videos for an organization, filtering them as needed.  Each
    video has the following attributes:

    * **id** - the ID of the video (int)
    * **description** - the DESCRIPTION of the video (string)
    * **title** - the TITLE of the video (string)
    * **org** - the ID of the org that owns this video (int)
    * **link** - the link to the source of this news item (string)
    * **category** - the CATEGORY of of this news item (dictionary)

    Example:

        GET /api/v1/videos/org/1/

    Response is the list of videos of the organisation, most recent first:

        {
            "count": 389,
            "next": "/api/v1/videos/org/1/?page=2",
            "previous": null,
            "results": [
            {
                "id": 1,
                "title": "test",
                "description": "This guy is hating on the benz",
                "video_id": "ZPJ64sTa7KI",
                "org": 1,
                "category": {
                    "image_url": "http://fake.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                    "name": "tests"
                }
            },
            ...
        }
    """
    serializer_class = VideoReadSerializer
    model = Video


class VideoDetails(RetrieveAPIView):
    """
    This endpoint allows you to a single video

    ## A single Video

    Example:

        GET /api/v1/videos/1/

    Response is a single Video:

        {
            "id": 1,
            "title": "test",
            "description": "This guy is hating on the benz",
            "video_id": "ZPJ64sTa7KI",
            "org": 1,
            "category": {
                "image_url": "http://fake.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                "name": "tests"
            }
        }
    """
    serializer_class = VideoReadSerializer
    queryset = Video.objects.filter(is_active=True)


class ImageList(BaseListAPIView):
    """
    This endpoint allows you to list assets.

    ## Listing assets

    By making a ```GET``` request you can list all the assets for an organization, filtering them as needed.  Each
    asset has the following attributes:

    * **id** - the ID of the asset (int)
    * **image_type** - the IMAGE_TYPE of the asset (string)
    * **title** - the TITLE of the asset (string)
    * **org** - the ID of the org that owns this asset (int)
    * **name** - the name of the asset (string)

    Example:

        GET /api/v1/assets/org/1/

    Response is the list of assets of the organisation, most recent first:

        {
            "count": 389,
            "next": "/api/v1/assets/org/1/?page=2",
            "previous": null,
            "results": [
            {
                "image_url": "http://test.ureport.in/media/images/Ai5BfWh79w7U8CN7jyiqOwn7S4F5gsUaFScdrRtf9-1o.jpg",
                "image_type": "B",
                "org": 1,
                "name": "Image name"
            },
            ...
        }
    """
    serializer_class = ImageReadSerializer
    model = Image


class ImageDetails(RetrieveAPIView):
    """
    This endpoint allows you to a single assets.

    ## A single asset

    Example:

        GET /api/v1/assets/1/

    Response is a single asset:

        {
            "image_url": "http://test.ureport.in/media/images/Ai5BfWh79w7U8CN7jyiqOwn7S4F5gsUaFScdrRtf9-1o.jpg",
            "image_type": "B",
            "org": 1,
            "name": "Image name"
        }
    """
    serializer_class = ImageReadSerializer
    queryset = Image.objects.filter(is_active=True)


class StoryList(BaseListAPIView):
    """
    This endpoint allows you to list stories.

    ## Listing stories

    By making a ```GET``` request you can list all the stories for an organization, filtering them as needed.  Each
    story has the following attributes:

    * **id** - the ID of the story (int)
    * **title** - the TITLE of the story (string)
    * **featured** - whether the story if FEATURED or not (boolean)
    * **org** - the ID of the org that owns this story (int)
    * **summary** - the summary of the story (string)
    * **video_id** - YouTube ID of the video in this story (string)
    * **audio_link** - the AUDIO_LINK in this story (string)
    * **tags** - the TAGS in this story (string)
    * **images** - the IMAGES in this story (list of strings)
    * **category** - the CATEGORY of the asset (dictionary)

    Example:

        GET /api/v1/stories/org/1/

    Response is the list of stories of the organisation, most recent first:

        {
            "count": 389,
            "next": "/api/v1/stories/org/1/?page=2",
            "previous": null,
            "results": [
            {
                "id": 1,
                "title": "Test Story",
                "featured": true,
                "summary": "This is the summary of the story.",
                "video_id": "",
                "audio_link": null,
                "tags": " test, story ",
                "org": 1,
                "images": [
                    "http://test.ureport.in/media/stories/StraightOuttaSomewhere_1.jpg",
                    "http://test.ureport.in/media/stories/StraightOuttaSomewhere.jpg"
                ],
                "category": {
                    "image_url": "http://test.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                    "name": "tests"
                }
            },
            ...
        }
    """
    serializer_class = StoryReadSerializer
    model = Story


class StoryDetails(RetrieveAPIView):
    """
    This endpoint allows you to a single story.

    ## A single story

    Example:

        GET /api/v1/story/1/

    Response is a single story:

        {
            "id": 1,
            "title": "Test Story",
            "featured": true,
            "summary": "This is the summary of the story.",
            "video_id": "",
            "audio_link": null,
            "tags": " test, story ",
            "org": 1,
            "images": [
                "http://test.ureport.in/media/stories/StraightOuttaSomewhere_1.jpg",
                "http://test.ureport.in/media/stories/StraightOuttaSomewhere.jpg"
            ],
            "category": {
                "image_url": "http://test.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                "name": "tests"
            }
        }
    """
    serializer_class = StoryReadSerializer
    queryset = Story.objects.filter(is_active=True)
