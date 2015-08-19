from dash.categories.models import Category
from dash.orgs.models import Org
from dash.stories.models import Story
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from ureport.assets.models import Image
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll

__author__ = 'kenneth'


class CategoryReadSerializer(serializers.ModelSerializer):
    image_url = SerializerMethodField()

    class Meta:
        model = Category
        exclude = ('org', 'image', 'created_on', 'modified_on', 'created_by', 'modified_by', 'id')

    def get_image_url(self, obj):
        url = None
        if obj.image:
            url = obj.image.url
        elif obj.get_first_image():
            url = obj.get_first_image().url
        if url:
            return self.context['request'].build_absolute_uri(url)
        return None


class OrgReadSerializer(serializers.ModelSerializer):
    logo_url = SerializerMethodField()

    class Meta:
        model = Org
        exclude = ('administrators', 'viewers', 'editors', 'api_token', 'config', 'logo')

    def get_logo_url(self, obj):
        if obj.logo:
            return self.context['request'].build_absolute_uri(obj.logo.url)
        return None


class StoryReadSerializer(serializers.ModelSerializer):
    category = CategoryReadSerializer()
    images = SerializerMethodField()

    class Meta:
        model = Story
        exclude = ('created_on', 'modified_on', 'created_by', 'modified_by', 'content')

    def get_images(self, obj):
        return [self.context['request'].build_absolute_uri(image.image.url) for image in obj.get_featured_images()]


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
        exclude = ('created_on', 'modified_on', 'created_by', 'modified_by')

    def get_short_description(self, obj):
        return obj.short_description()


class VideoReadSerializer(serializers.ModelSerializer):
    category = CategoryReadSerializer()

    class Meta:
        model = Video
        exclude = ('created_on', 'modified_on', 'created_by', 'modified_by')


class ImageReadSerializer(serializers.ModelSerializer):
    image_url = SerializerMethodField()

    class Meta:
        model = Image
        exclude = ('image', 'created_on', 'modified_on', 'created_by', 'modified_by')

    def get_image_url(self, obj):
        return self.context['request'].build_absolute_uri(obj.image.url)