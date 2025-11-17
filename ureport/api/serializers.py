# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json

import six
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from sorl.thumbnail import get_thumbnail

from dash.categories.models import Category
from dash.dashblocks.models import DashBlock
from dash.orgs.models import Org
from dash.stories.models import Story
from ureport.assets.models import Image
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll


def generate_absolute_url_from_file(request, file, thumbnail_geometry):
    thumnail = get_thumbnail(file, thumbnail_geometry, crop="center", quality=99)
    return request.build_absolute_uri(thumnail.url)


class CategoryReadSerializer(serializers.ModelSerializer):
    image_url = SerializerMethodField()

    def get_image_url(self, obj):
        image = None
        if obj.image:
            image = obj.image
        elif obj.get_first_image():
            image = obj.get_first_image()
        if image:
            return generate_absolute_url_from_file(self.context["request"], image, "800x600")
        return None

    class Meta:
        model = Category
        fields = ("image_url", "name")


class OrgReadSerializer(serializers.ModelSerializer):
    logo_url = SerializerMethodField()
    gender_stats = SerializerMethodField()
    age_stats = SerializerMethodField()
    registration_stats = SerializerMethodField()
    occupation_stats = SerializerMethodField()
    schemes_stats = SerializerMethodField()
    reporters_count = SerializerMethodField()
    timezone = SerializerMethodField()

    class Meta:
        model = Org
        fields = (
            "id",
            "logo_url",
            "name",
            "language",
            "subdomain",
            "domain",
            "timezone",
            "gender_stats",
            "age_stats",
            "registration_stats",
            "occupation_stats",
            "schemes_stats",
            "reporters_count",
        )

    def get_logo_url(self, obj):
        if obj.get_logo():
            return generate_absolute_url_from_file(self.context["request"], obj.get_logo(), "x180")
        return None

    def get_gender_stats(self, obj):
        return obj.get_gender_stats()

    def get_age_stats(self, obj):
        return json.loads(obj.get_age_stats())

    def get_registration_stats(self, obj):
        return json.loads(obj.get_registration_stats())

    def get_occupation_stats(self, obj):
        # Occupation stats have been removed
        return []

    def get_schemes_stats(self, obj):
        return obj.get_schemes_stats()

    def get_reporters_count(self, obj):
        return obj.get_reporters_count()

    def get_timezone(self, obj):
        return six.text_type(obj.timezone)


class StoryReadSerializer(serializers.ModelSerializer):
    category = CategoryReadSerializer()
    images = SerializerMethodField()

    def get_images(self, obj):
        return [
            generate_absolute_url_from_file(self.context["request"], image.image, "800x600")
            for image in obj.get_featured_images()
        ]

    # Function to use ?fields and ?exclude API calls for specific attributes in stories
    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        request = kwargs.get("context", {}).get("request")
        str_exclude_fields = request.GET.get("exclude", "") if request else None
        str_fields = request.GET.get("fields", "") if request else None
        fields = str_fields.split(",") if str_fields else None
        exclude_fields = str_exclude_fields.split(",") if str_exclude_fields else None

        # Instantiate the superclass normally
        super(StoryReadSerializer, self).__init__(*args, **kwargs)

        if exclude_fields is not None:
            # Drop any fields that are specified in the `exclude` argument.
            exclude_allowed = set(exclude_fields)
            for field_name in exclude_allowed:
                self.fields.pop(field_name)
        elif fields is not None:
            allowed_fields = set(fields)
            existing_data = set(self.fields)
            for field_names in existing_data - allowed_fields:
                self.fields.pop(field_names)

    class Meta:
        model = Story
        fields = (
            "id",
            "title",
            "featured",
            "summary",
            "content",
            "video_id",
            "audio_link",
            "tags",
            "org",
            "images",
            "category",
            "created_on",
        )


class PollReadSerializer(serializers.ModelSerializer):
    category = CategoryReadSerializer()
    questions = SerializerMethodField()

    # Function to use ?fields and ?exclude API calls for specific attributes in polls
    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        request = kwargs.get("context", {}).get("request")
        str_exclude_fields = request.GET.get("exclude", "") if request else None
        str_fields = request.GET.get("fields", "") if request else None
        fields = str_fields.split(",") if str_fields else None
        exclude_fields = str_exclude_fields.split(",") if str_exclude_fields else None

        # Instantiate the superclass normally
        super(PollReadSerializer, self).__init__(*args, **kwargs)

        if exclude_fields is not None:
            # Drop any fields that are specified in the `exclude` argument.
            exclude_allowed = set(exclude_fields)
            for field_name in exclude_allowed:
                self.fields.pop(field_name)
        elif fields is not None:
            allowed_fields = set(fields)
            existing_data = set(self.fields)
            for field_names in existing_data - allowed_fields:
                self.fields.pop(field_names)

    def get_questions(self, obj):
        questions = []
        for question in obj.get_questions():
            open_ended = question.is_open_ended()
            results_dict = dict(open_ended=open_ended)
            results = question.get_results()
            if results:
                results_dict = results[0]
            results_by_age = question.get_results(segment=dict(age="Age"))
            results_by_gender = question.get_results(segment=dict(gender="Gender"))
            results_by_state = question.get_results(segment=dict(location="State"))

            question_data = {
                "id": question.pk,
                "ruleset_uuid": question.flow_result.result_uuid,
                "title": question.title,
                "results": results_dict,
            }

            if not open_ended:
                question_data["results_by_age"] = results_by_age
                question_data["results_by_gender"] = results_by_gender
                question_data["results_by_location"] = results_by_state

            questions.append(question_data)

        return questions

    class Meta:
        model = Poll
        fields = ("id", "flow_uuid", "title", "org", "category", "poll_date", "modified_on", "created_on", "questions")


class NewsItemReadSerializer(serializers.ModelSerializer):
    short_description = SerializerMethodField()
    category = CategoryReadSerializer()

    def get_short_description(self, obj):
        return obj.short_description()

    class Meta:
        model = NewsItem
        fields = ("id", "short_description", "category", "title", "description", "link", "org", "created_on")


class VideoReadSerializer(serializers.ModelSerializer):
    category = CategoryReadSerializer()

    class Meta:
        model = Video
        fields = ("id", "category", "title", "description", "video_id", "org", "created_on")


class ImageReadSerializer(serializers.ModelSerializer):
    image_url = SerializerMethodField()

    def get_image_url(self, obj):
        return generate_absolute_url_from_file(self.context["request"], obj.image, "x180")

    class Meta:
        model = Image
        fields = ("id", "image_url", "image_type", "org", "name", "created_on")


class DashblockReadSerializer(serializers.ModelSerializer):
    dashblock_type = SerializerMethodField()
    image_url = SerializerMethodField()
    path = SerializerMethodField()

    def get_image_url(self, obj):
        if obj.image:
            return generate_absolute_url_from_file(self.context["request"], obj.image, "800x600")
        return None

    def get_dashblock_type(self, obj):
        return obj.dashblock_type.slug

    def get_path(self, obj):
        return obj.link

    class Meta:
        model = DashBlock
        fields = (
            "id",
            "org",
            "dashblock_type",
            "priority",
            "title",
            "summary",
            "content",
            "image_url",
            "color",
            "path",
            "video_id",
            "tags",
        )
