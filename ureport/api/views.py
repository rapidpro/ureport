# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from rest_framework.generics import ListAPIView, RetrieveAPIView

from django.db.models import Q

from dash.dashblocks.models import DashBlock
from dash.orgs.models import Org
from dash.stories.models import Story
from ureport.api.serializers import (
    DashblockReadSerializer,
    ImageReadSerializer,
    NewsItemReadSerializer,
    OrgReadSerializer,
    PollReadSerializer,
    StoryReadSerializer,
    VideoReadSerializer,
)
from ureport.assets.models import Image
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll


class OrgList(ListAPIView):
    """
    This endpoint allows you to list orgs.

    ## Listing Orgs

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
        q = self.model.objects.filter(is_active=True).order_by("-created_on")
        if self.kwargs.get("org", None):
            q = q.filter(org_id=self.kwargs.get("org"))
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

    * **sort** - Order the results by modified on desceding if specified and equal to ```modified_on```

    Example:

        GET /api/v1/polls/org/1/

    Response is the list of polls, most recent first:

        {
            "count": 389,
            "next": "/api/v1/polls/org/1/?page=2",
            "previous": null,
            "results": [
                {
                    "id": 2,
                    "flow_uuid": "a497ba0f-6b58-4bed-ba52-05c3f40403e2",
                    "title": "Food Poll",
                    "org": 1,
                    "category": {
                        "image_url": null,
                        "name": "Education"
                     },
                    "questions": [
                        {
                            "id": 14,
                            "title": "Are you hungry?",
                            "ruleset_uuid": "ea74b2c2-7425-443a-97cb-331d4e11abb6",
                            "results":
                                 {
                                     "open_ended": false,
                                     "set": 100,
                                     "unset": 150,
                                     "categories": [
                                         {
                                             "count": 60,
                                             "label": "Yes"
                                         },
                                         {
                                              "count": 30,
                                              "label": "NO"
                                         },
                                         {
                                              "count": 10,
                                              "label": "Thirsty"
                                         },
                                         {
                                              "count": 0,
                                              "label": "Other"
                                         },
                                     ]
                                 }
                        },
                        {



                            "id": 16,
                            "title": "What would you like to eat",
                            "ruleset_uuid": "66e08f93-cdff-4dbc-bd02-c746770a4fac",
                            "results":
                                {
                                    "open_ended": true,
                                    "set": 70,
                                    "unset": 30,
                                    "categories": [
                                        {
                                            "count": 40,
                                            "label": "Food"
                                        },
                                        {
                                            "count": 10,
                                            "label": "Cake"
                                        },
                                        {
                                            "count": 15,
                                            "label": "Fruits"
                                        },
                                        {
                                            "count": 5,
                                            "label": "Coffee"
                                        },
                                    ]
                                }
                        },
                        {
                            "id": 17,
                            "title": "Where would you like to eat?",
                            "ruleset_uuid": "e31755dd-c61a-460c-acaf-0eeee1ce0107",
                            "results":
                                {
                                    "open_ended": false,
                                    "set": 50,
                                    "unset": 20,
                                    "categories": [
                                        {
                                            "count": 30,
                                            "label": "Home"
                                        },
                                        {
                                            "count": 12,
                                            "label": "Resto"
                                        },
                                        {
                                            "count": 5,
                                            "label": "Fast Food"
                                        },
                                        {
                                            "count": 3,
                                            "label": "Other"
                                        },
                                    ]
                                }
                        }

                    ]


                    "category": {
                        "image_url": "http://test.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                        "name": "tests"
                    },
                    "poll_date": "2015-09-02T08:53:30.313251Z",
                    "modified_on": "2015-09-02T08:53:30.313251Z",
                    "created_on": "2015-09-02T08:53:30.313251Z"
                }
                ...
            ]
        }


    If you want to get polls with only specific attributes:

    Example:

        GET /api/v1/polls/org/{org}/?fields=title,flow_uuid

    Response is polls with only title and flow_uuid attributes.


    If you want to get polls without specific attributes:

    Example:

        GET /api/v1/polls/org/{org}/?exclude=title,flow_uuid

    Response is polls without title and flow_uuid attributes.


    """

    serializer_class = PollReadSerializer
    model = Poll

    def get_queryset(self):
        q = super(PollList, self).get_queryset()
        q = q.filter(is_active=True, published=True, has_synced=True).exclude(flow_uuid="")
        if self.request.query_params.get("flow_uuid", None):
            q = q.filter(flow_uuid=self.request.query_params.get("flow_uuid"))

        if self.request.query_params.get("sort", None) == "modified_on":
            q = q.order_by("-modified_on")

        return q


class PollDetails(RetrieveAPIView):
    """
    This endpoint allows you to get a single poll.

    ## Get a single poll

    Example:

        GET /api/v1/polls/1/

    Response is a single poll with that ID:

        {
            "id": 2,
            "flow_uuid": "a497ba0f-6b58-4bed-ba52-05c3f40403e2",
            "title": "Food Poll",
            "org": 1,
            "category": {
                "image_url": null,
                "name": "Education"
            },
            "questions": [
                {
                    "id": 14,
                    "title": "Are you hungry?",
                    "ruleset_uuid": "ea74b2c2-7425-443a-97cb-331d4e11abb6",
                    "results":
                        {
                            "open_ended": false,
                            "set": 100,
                            "unset": 150,
                            "categories": [
                                {
                                    "count": 60,
                                    "label": "Yes"
                                },
                                {
                                    "count": 30,
                                    "label": "NO"
                                },
                                {
                                    "count": 10,
                                    "label": "Thirsty"
                                },
                                {
                                    "count": 0,
                                    "label": "Other"
                                },
                            ]
                        }
                },
                {
                    "id": 16,
                    "title": "What would you like to eat",
                    "ruleset_uuid": "66e08f93-cdff-4dbc-bd02-c746770a4fac",
                    "results":
                        {
                            "open_ended": true,
                            "set": 70,
                            "unset": 30,
                            "categories": [
                                {
                                    "count": 40,
                                    "label": "Food"
                                },
                                {
                                    "count": 10,
                                    "label": "Cake"
                                },
                                {
                                    "count": 15,
                                    "label": "Fruits"
                                },
                                {
                                    "count": 5,
                                    "label": "Coffee"
                                },
                            ]
                        }
                },
                {
                    "id": 17,
                    "title": "Where would you like to eat?",
                    "ruleset_uuid": "e31755dd-c61a-460c-acaf-0eeee1ce0107",
                    "results":
                        {
                            "open_ended": false,
                            "set": 50,
                            "unset": 20,
                            "categories": [
                                {
                                    "count": 30,
                                    "label": "Home"
                                },
                                {
                                    "count": 12,
                                    "label": "Resto"
                                },
                                {
                                    "count": 5,
                                    "label": "Fast Food"
                                },
                                {
                                    "count": 3,
                                    "label": "Other"
                                },
                            ]
                        }
                }
            ],
            "category": {
                "image_url": "http://test.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                "name": "tests"
            },
            "created_on": "2015-09-02T08:53:30.313251Z"
        }


    If you want to get a poll with only specific attributes:

    Example:

        GET /api/v1/polls/{id}/?fields=title,flow_uuid

    Response is a poll with only title and flow_uuid attributes.


    If you want to get a poll without specific attributes:

    Example:

        GET /api/v1/polls/{id}/?exclude=title,flow_uuid

    Response is a poll without title and flow_uuid attributes.


    """

    serializer_class = PollReadSerializer
    queryset = Poll.objects.filter(is_active=True, published=True, has_synced=True).exclude(flow_uuid="")


class FeaturedPollList(BaseListAPIView):
    """
    This endpoint allows you to list all featured polls for an organisation.

    ## Listing Featured Polls

    * **sort** - Order the results by modified on desceding if specified and equal to ```modified_on```

    Example:

        GET /api/v1/polls/org/1/featured/

    Response is a list of the featured polls, most recent first. \
    An empty list is returned if there are no polls with questions.

        {
            "count": 389,
            "next": "/api/v1/polls/org/1/?page=2",
            "previous": null,
            "results": [
                {
                    "id": 2,
                    "flow_uuid": "a497ba0f-6b58-4bed-ba52-05c3f40403e2",
                    "title": "Food Poll",
                    "org": 1,
                    "questions": [
                        {
                            "id": 14,
                            "title": "Are you hungry?",
                            "ruleset_uuid": "ea74b2c2-7425-443a-97cb-331d4e11abb6",
                            "results":
                                 {
                                     "open_ended": false,
                                     "set": 100,
                                     "unset": 150,
                                     "categories": [
                                         {
                                             "count": 60,
                                             "label": "Yes"
                                         },
                                         {
                                              "count": 30,
                                              "label": "NO"
                                         },
                                         {
                                              "count": 10,
                                              "label": "Thirsty"
                                         },
                                         {
                                              "count": 0,
                                              "label": "Other"
                                         },
                                     ]
                                 }
                        },
                        {



                            "id": 16,
                            "title": "What would you like to eat",
                            "ruleset_uuid": "66e08f93-cdff-4dbc-bd02-c746770a4fac",
                            "results":
                                {
                                    "open_ended": true,
                                    "set": 70,
                                    "unset": 30,
                                    "categories": [
                                        {
                                            "count": 40,
                                            "label": "Food"
                                        },
                                        {
                                            "count": 10,
                                            "label": "Cake"
                                        },
                                        {
                                            "count": 15,
                                            "label": "Fruits"
                                        },
                                        {
                                            "count": 5,
                                            "label": "Coffee"
                                        },
                                    ]
                                }
                        },
                        {
                            "id": 17,
                            "title": "Where would you like to eat?",
                            "ruleset_uuid": "e31755dd-c61a-460c-acaf-0eeee1ce0107",
                            "results":
                                {
                                    "open_ended": false,
                                    "set": 50,
                                    "unset": 20,
                                    "categories": [
                                        {
                                            "count": 30,
                                            "label": "Home"
                                        },
                                        {
                                            "count": 12,
                                            "label": "Resto"
                                        },
                                        {
                                            "count": 5,
                                            "label": "Fast Food"
                                        },
                                        {
                                            "count": 3,
                                            "label": "Other"
                                        },
                                    ]
                                }
                        }

                    ]


                    "category": {
                        "image_url": "http://test.ureport.in/media/categories/StraightOuttaSomewhere_2.jpg",
                        "name": "tests"
                    },
                    "poll_date": "2015-09-02T08:53:30.313251Z",
                    "modified_on": "2015-09-02T08:53:30.313251Z",
                    "created_on": "2015-09-02T08:53:30.313251Z"
                }
                ...
            ]
        }

    If you want to get the featured poll with only specific attributes:

    Example:

        GET /api/v1/polls/org/{org}/featured/?fields=title,flow_uuid

    Response is the featured poll with only title and flow_uuid attributes.


    If you want to get the featured poll without specific attributes:

    Example:

        GET /api/v1/polls/org/{org}/featured/?exclude=title,flow_uuid

    Response is the featured poll without title and flow_uuid attributes.


    """

    serializer_class = PollReadSerializer
    model = Poll

    def get_queryset(self):
        q = super(FeaturedPollList, self).get_queryset()

        if self.request.query_params.get("sort", None) == "modified_on":
            q = (
                q.filter(is_active=True, published=True, has_synced=True)
                .exclude(flow_uuid="")
                .filter(is_featured=True)
                .order_by("-modified_on")
            )
        else:
            q = (
                q.filter(is_active=True, published=True, has_synced=True)
                .exclude(flow_uuid="")
                .filter(is_featured=True)
                .order_by("-created_on")
            )
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

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(is_active=True, image_type="L")


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
    queryset = Image.objects.filter(is_active=True, image_type="L")


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
    * **content** - the content of the story (string), this can be containing HTML code data as the content is managed as WYSIWYG
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
                "content": "This is the <b>content</b> of the story.",
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


    If you want to get stories with only specific attributes:

    Example:

        GET /api/v1/stories/org/{org}/?fields=title,content

    Response is stories with only title and content attributes.


    If you want to get stories without specific attributes:

    Example:

        GET /api/v1/stories/org/{org}/?exclude=title,content

    Response is stories without title and content attributes.


    """

    serializer_class = StoryReadSerializer
    model = Story
    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(is_active=True).filter(Q(attachment="") | Q(attachment=None))

class StoryDetails(RetrieveAPIView):
    """
    This endpoint allows you to a single story.

    ## A single story

    Example:

        GET /api/v1/stories/1/

    Response is a single story:

        {
            "id": 1,
            "title": "Test Story",
            "featured": true,
            "summary": "This is the summary of the story.",
            "content": "This is the <b>content</b> of the story.",
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

    If you want to get a story with only specific attributes:

    Example:

        GET /api/v1/stories/{id}/?fields=title,content

    Response is a story with only title and content attributes.


    If you want to get a story without specific attributes:

    Example:

        GET /api/v1/stories/{id}/?exclude=title,content

    Response is a story without title and content attributes.


    """

    serializer_class = StoryReadSerializer
    queryset = Story.objects.filter(is_active=True).filter(Q(attachment="") | Q(attachment=None))


class DashBlockList(BaseListAPIView):
    """
    This endpoint allows you to list dashblocks.

    ## Listing dashblocks

    By making a ```GET``` request you can list all the dashblocks for an organization, filtering them as needed.  Each
    dashblock has the following attributes:

    * **id** - the ID of the story (int)
    * **org** - the ID of the org that owns this dashblock (int)
    * **dashblock_type** - the type of the dashblock (string)  filterable as `dashblock_type`.
    * **priority** - the priority of the dashblock (int)
    * **title** - the title of the dashblock (string)
    * **summary** - the summary of the dashblock (string)
    * **content** - the content of the dashblock (string), this can be containing HTML code data as the content is managed as WYSIWYG
    * **image_url** - the image url of the dashblock image (string)
    * **color** - the color of the dashblock (string)
    * **path** - the path of the dashblock to use after the root URL (string)
    * **video_id** - the video_id of the dashblock image (string)
    * **tags** - the tags of the dashblock (string)


    Example:

        GET /api/v1/dashblocks/org/1/

    Response is the list of dashblocks of the organisation
        {
            "count": 13,
            "next": "http://test.ureport.in/api/v1/dashblocks/org/1/?limit=10&offset=10",
            "previous": null,
            "results": [
                {
                  "id": 12,
                  "org": 1,
                  "dashblock_type": "photos",
                  "priority": 1,
                  "title": "CRC@30",
                  "summary": null,
                  "content": "Happy Child",
                  "image_url": "http://test.ureport.in/media/cache/ac/a7/aca7e7ae228e107b9186e77f222faabe.jpg",
                  "color": null,
                  "path": null,
                  "video_id": null,
                  "tags": null
                },
                {
                  "id": 54,
                  "org": 1,
                  "dashblock_type": "photos",
                  "priority": 0,
                  "title": "World Mental Day Poll",
                  "summary": null,
                  "content": "",
                  "image_url": "http://test.ureport.in/media/cache/0b/0b/0b0ba4976ac12600c1e1b957d21f5d6d.jpg",
                  "color": null,
                  "link": null,
                  "video_id": null,
                  "tags": null
                }
            ]
        }

    """

    serializer_class = DashblockReadSerializer
    model = DashBlock
    exclusive_params = ("dashblock_type",)

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(is_active=True).select_related("dashblock_type")

    def filter_queryset(self, queryset):
        params = self.request.query_params

        # filter by UUID (optional)
        d_type = params.get("dashblock_type")
        if d_type:
            queryset = queryset.filter(dashblock_type__slug=d_type)

        return queryset


class DashBlockDetails(RetrieveAPIView):
    """
    This endpoint allows you to a single dashblock.

    ## A single dashblock

    Example:

        GET /api/v1/dashblocks/1/

    Response is a single dashblock:

        {
            "id": 1,
            "org": 1,
            "dashblock_type": "about",
            "priority": 0,
            "title": "About",
            "summary": "U-report is a free SMS social monitoring.",
            "content": "U-report is a free SMS social monitoring tool for community participation, designed to address issues that the population cares about.",
            "image_url": "http://test.ureport.in/media/cache/0b/0b/0b0ba4976ac12600c1e1b957d21f5d6d.jpg",
            "color": null,
            "link": null,
            "video_id": null,
            "tags": null
        },
    """

    serializer_class = DashblockReadSerializer
    model = DashBlock
    queryset = DashBlock.objects.filter(is_active=True)
