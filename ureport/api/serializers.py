import json
from dash.categories.models import Category
from dash.orgs.models import Org
from dash.stories.models import Story
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from ureport.assets.models import Image
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll

__author__ = 'kenneth'


def generate_absolute_url_from_file(request, file):
    return request.build_absolute_uri(file.url)


class CategoryReadSerializer(serializers.ModelSerializer):
    image_url = SerializerMethodField()

    class Meta:
        model = Category
        fields = ('image_url', 'name',)

    def get_image_url(self, obj):
        image = None
        if obj.image:
            image = obj.image
        elif obj.get_first_image():
            image = obj.get_first_image()
        if image:
            return generate_absolute_url_from_file(self.context['request'], image)
        return None


class OrgReadSerializer(serializers.ModelSerializer):
    logo_url = SerializerMethodField()
    gender_stats = SerializerMethodField()
    age_stats = SerializerMethodField()
    registration_stats = SerializerMethodField()
    occupation_stats = SerializerMethodField()
    reporters_count = SerializerMethodField()

    class Meta:
        model = Org
        fields = ('id', 'logo_url', 'name', 'language', 'subdomain', 'domain', 'timezone', 'gender_stats', 'age_stats',
                  'registration_stats', 'occupation_stats', 'reporters_count')

    def get_logo_url(self, obj):
        if obj.logo:
            return generate_absolute_url_from_file(self.context['request'], obj.logo)
        return None

    def get_gender_stats(self, obj):
        return obj.get_gender_stats()

    def get_age_stats(self, obj):
        return json.loads(obj.get_age_stats())

    def get_registration_stats(self, obj):
        return json.loads(obj.get_registration_stats())

    def get_occupation_stats(self, obj):
        return json.loads(obj.get_occupation_stats())

    def get_reporters_count(self, obj):
        return obj.get_reporters_count()


class StoryReadSerializer(serializers.ModelSerializer):
    category = CategoryReadSerializer()
    images = SerializerMethodField()

    class Meta:
        model = Story
        fields = ('id', 'title', 'featured', 'summary', 'video_id', 'audio_link', 'tags', 'org', 'images', 'category')

    def get_images(self, obj):
        return [generate_absolute_url_from_file(self.context['request'], image.image)
                for image in obj.get_featured_images()]


class PollReadSerializer(serializers.ModelSerializer):
    category = CategoryReadSerializer()

    class Meta:
        model = Poll
        fields = ('id', 'flow_uuid', 'title', 'org', 'category')


class NewsItemReadSerializer(serializers.ModelSerializer):
    short_description = SerializerMethodField()
    category = CategoryReadSerializer()

    class Meta:
        model = NewsItem
        fields = ('id', 'short_description', 'category', 'title', 'description', 'link', 'org')

    def get_short_description(self, obj):
        return obj.short_description()


class VideoReadSerializer(serializers.ModelSerializer):
    category = CategoryReadSerializer()

    class Meta:
        model = Video
        fields = ('id', 'category', 'title', 'description', 'video_id', 'org')


class ImageReadSerializer(serializers.ModelSerializer):
    image_url = SerializerMethodField()

    class Meta:
        model = Image
        fields = ('id', 'image_url', 'image_type', 'org', 'name',)

    def get_image_url(self, obj):
        return generate_absolute_url_from_file(self.context['request'], obj.image)
