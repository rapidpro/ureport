from collections import OrderedDict
import json
from random import randint
from django.utils import timezone
from dash.categories.models import Category
from dash.orgs.models import Org
from dash.stories.models import Story
from datetime import datetime
from django.contrib.auth.models import User
from mock import patch
import pytz
from rest_framework import status
from rest_framework.test import APITestCase
from ureport.api.serializers import generate_absolute_url_from_file, CategoryReadSerializer, StoryReadSerializer
from ureport.contacts.models import ReportersCounter
from ureport.news.models import NewsItem, Video
from ureport.polls.models import Poll, PollQuestion


class UreportAPITests(APITestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(username="super", email="super@user.com", password="super")
        self.uganda = self.create_org('uganda', self.superuser)
        self.nigeria = self.create_org('testserver', self.superuser)

        self.health_uganda = Category.objects.create(org=self.uganda,
                                                     name="Health",
                                                     created_by=self.superuser,
                                                     modified_by=self.superuser)

        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.superuser,
                                                         modified_by=self.superuser)

        self.reg_poll = self.create_poll('registration')
        self.another_poll = self.create_poll('another')
        self.first_featured_poll = self.create_poll('first featured', is_featured=True)
        self.first_poll_question = PollQuestion.objects.create(
            poll=self.first_featured_poll, title='test question', ruleset_uuid='uuid1',
            created_by=self.superuser, modified_by=self.superuser)
        self.second_featured_poll = self.create_poll('second featured', is_featured=True)
        self.second_poll_question = PollQuestion.objects.create(
            poll=self.second_featured_poll, title='another test question', ruleset_uuid='uuid2',
            created_by=self.superuser, modified_by=self.superuser)

        self.news_item = self.create_news_item('Some item')
        self.create_video('Test Video')
        self.create_story("Test Story")

    def create_org(self, subdomain, user):
        email = subdomain + "@user.com"
        first_name = subdomain + "_First"
        last_name = subdomain + "_Last"
        name = subdomain

        orgs = Org.objects.filter(subdomain=subdomain)
        if orgs:
            org = orgs[0]
            org.name = name
            org.save()
        else:
            org = Org.objects.create(domain=subdomain, name=name, created_by=user, modified_by=user)

        org.administrators.add(user)

        self.assertEquals(Org.objects.filter(domain=subdomain).count(), 1)
        return Org.objects.get(domain=subdomain)

    def create_poll(self, title, is_featured=False):
        now = timezone.now()
        return Poll.objects.create(flow_uuid=str(randint(1000, 9999)),
                                   title=title,
                                   category=self.health_uganda,
                                   poll_date=now,
                                   org=self.uganda,
                                   is_featured=is_featured,
                                   created_by=self.superuser,
                                   modified_by=self.superuser)

    def create_news_item(self, title):
        return NewsItem.objects.create(title=title,
                                       description='uganda description 1',
                                       link='http://uganda.ug',
                                       category=self.health_uganda,
                                       org=self.uganda,
                                       created_by=self.superuser,
                                       modified_by=self.superuser)

    def create_video(self, title):
        self.uganda_video = Video.objects.create(title=title,
                                                 description='You are welcome to Kampala',
                                                 video_id='Kplatown',
                                                 category=self.health_uganda,
                                                 org=self.uganda,
                                                 created_by=self.superuser,
                                                 modified_by=self.superuser)

    def create_story(self, title):
        self.uganda_story = Story.objects.create(title=title,
                                                 featured=True,
                                                 summary="This is a test summary",
                                                 content="This is test content",
                                                 video_id='iouiou',
                                                 tags='tag1, tag2, tag3',
                                                 category=self.health_uganda,
                                                 created_by=self.superuser,
                                                 modified_by=self.superuser,
                                                 org=self.uganda)

    def test_orgs_list(self):
        url = '/api/v1/orgs/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Org.objects.count())

    def test_single_org(self):
        url = '/api/v1/orgs/%d/' % self.uganda.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        org = self.uganda
        logo_url = generate_absolute_url_from_file(response, org.logo) if org.logo else None
        gender_stats = response.data.pop('gender_stats')
        age_stats = response.data.pop('age_stats')
        registration_stats = response.data.pop('registration_stats')
        occupation_stats = response.data.pop('occupation_stats')
        reporters_count = response.data.pop('reporters_count')
        self.assertDictEqual(response.data, dict(id=org.pk,
                                                 logo_url=logo_url,
                                                 name=org.name,
                                                 language=org.language,
                                                 subdomain=org.subdomain,
                                                 domain=org.domain,
                                                 timezone=org.timezone))

        self.assertEquals(gender_stats, dict(female_count=0, female_percentage="---",
                                             male_count=0, male_percentage="---"))

        self.assertEqual(age_stats, [dict(name='0-14', y=0), dict(name='15-19', y=0), dict(name='20-24', y=0),
                                     dict(name='25-30', y=0), dict(name='31-34', y=0), dict(name='35+', y=0)])
        self.assertEquals(reporters_count, 0)
        self.assertEquals(occupation_stats, [])

        ReportersCounter.objects.create(org=org, type='gender:f', count=2)
        ReportersCounter.objects.create(org=org, type='gender:m', count=2)
        ReportersCounter.objects.create(org=org, type='gender:m', count=1)

        now = timezone.now()
        now_year = now.year

        two_years_ago = now_year - 2
        five_years_ago = now_year - 5
        twelve_years_ago = now_year - 12
        forthy_five_years_ago = now_year - 45

        ReportersCounter.objects.create(org=org, type='born:%s' % two_years_ago, count=2)
        ReportersCounter.objects.create(org=org, type='born:%s' % five_years_ago, count=1)
        ReportersCounter.objects.create(org=org, type='born:%s' % twelve_years_ago, count=3)
        ReportersCounter.objects.create(org=org, type='born:%s' % twelve_years_ago, count=2)
        ReportersCounter.objects.create(org=org, type='born:%s' % forthy_five_years_ago, count=2)

        ReportersCounter.objects.create(org=org, type='born:10', count=10)
        ReportersCounter.objects.create(org=org, type='born:732837', count=20)

        ReportersCounter.objects.create(org=org, type='total-reporters', count=5)

        ReportersCounter.objects.create(org=org, type='occupation:student', count=5)
        ReportersCounter.objects.create(org=org, type='occupation:writer', count=2)
        ReportersCounter.objects.create(org=org, type='occupation:all responses', count=13)

        response = self.client.get(url)


        gender_stats = response.data.pop('gender_stats')
        self.assertEqual(gender_stats, dict(female_count=2, female_percentage="40%",
                                            male_count=3, male_percentage="60%"))

        age_stats = response.data.pop('age_stats')
        self.assertEqual(age_stats, [dict(name='0-14', y=80), dict(name='15-19', y=0), dict(name='20-24', y=0),
                                     dict(name='25-30', y=0), dict(name='31-34', y=0), dict(name='35+', y=20)])

        reporters_count = response.data.pop('reporters_count')
        self.assertEqual(reporters_count, 5)

        occupation_stats = response.data.pop('occupation_stats')
        self.assertEqual(occupation_stats, [dict(label='student', count=5), dict(label='writer', count=2)])

        tz = pytz.timezone('UTC')

        with patch.object(timezone, 'now', return_value=tz.localize(datetime(2015, 9, 4, 3, 4, 5, 6))):

            for entry in registration_stats:
                self.assertEqual(entry['count'], 0)

            ReportersCounter.objects.create(org=org, type='registered_on:2015-08-27', count=3)
            ReportersCounter.objects.create(org=org, type='registered_on:2015-08-25', count=2)
            ReportersCounter.objects.create(org=org, type='registered_on:2015-08-25', count=3)
            ReportersCounter.objects.create(org=org, type='registered_on:2015-08-25', count=1)
            ReportersCounter.objects.create(org=org, type='registered_on:2015-06-30', count=2)
            ReportersCounter.objects.create(org=org, type='registered_on:2015-06-30', count=2)
            ReportersCounter.objects.create(org=org, type='registered_on:2014-11-25', count=6)

            response = self.client.get(url)

            stats = response.data.pop('registration_stats')

            non_zero_keys = {'08/24/15': 9, '06/29/15': 4}

            for entry in stats:
                self.assertFalse(entry['label'].endswith('14'))
                if entry['count'] != 0:
                    self.assertTrue(entry['label'] in non_zero_keys.keys())
                    self.assertEqual(entry['count'], non_zero_keys[entry['label']])


    def test_polls_by_org_list(self):
        url = '/api/v1/polls/org/%d/' % self.uganda.pk
        url2 = '/api/v1/polls/org/%d/' % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Poll.objects.filter(org=self.uganda).count())
        response = self.client.get(url2)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Poll.objects.filter(org=self.nigeria).count())

    def test_polls_by_org_list_with_flow_uuid_parameter(self):
        url = '/api/v1/polls/org/%d/?flow_uuid=%s' % (self.uganda.pk, self.reg_poll.flow_uuid)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['title'], 'registration')

    def test_featured_poll_by_org_list_when_featured_polls_exists(self):
        url = '/api/v1/polls/org/%d/featured/' % self.uganda.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['title'], 'second featured')
        self.assertEqual(response.data['results'][1]['title'], 'first featured')

    def test_featured_poll_by_org_list_when_no_featured_polls_exists(self):
        url = '/api/v1/polls/org/%d/featured/' % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_single_poll(self):
        url = '/api/v1/polls/%d/' % self.reg_poll.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        poll = self.reg_poll
        category = response.data.pop('category')
        self.assertDictEqual(response.data, dict(id=poll.pk,
                                                 flow_uuid=poll.flow_uuid,
                                                 title=poll.title,
                                                 org=poll.org_id,
                                                 ))
        self.assertDictEqual(dict(category), dict(OrderedDict(name=poll.category.name,
                                                  image_url=CategoryReadSerializer().
                                                  get_image_url(poll.category))))

    def test_news_item_by_org_list(self):
        url = '/api/v1/news/org/%d/' % self.uganda.pk
        url1 = '/api/v1/news/org/%d/' % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], NewsItem.objects.filter(org=self.uganda).count())
        response = self.client.get(url1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], NewsItem.objects.filter(org=self.nigeria).count())

    def test_single_news_item(self):
        url = '/api/v1/news/%d/' % self.news_item.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        news = self.news_item
        category = response.data.pop('category')
        self.assertDictEqual(response.data, dict(id=news.pk,
                                                 short_description=news.short_description(),
                                                 title=news.title,
                                                 description=news.description,
                                                 link=news.link,
                                                 org=news.org_id))
        self.assertDictEqual(dict(category), dict(name=news.category.name,
                                                  image_url=CategoryReadSerializer().get_image_url(news.category)))

    def test_video_by_org_list(self):
        url = '/api/v1/videos/org/%d/' % self.uganda.pk
        url1 = '/api/v1/videos/org/%d/' % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Video.objects.filter(org=self.uganda).count())
        response = self.client.get(url1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Video.objects.filter(org=self.nigeria).count())

    def test_single_video(self):
        url = '/api/v1/videos/%d/' % self.uganda_video.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        video = self.uganda_video
        category = response.data.pop('category')
        self.assertDictEqual(response.data, dict(id=video.pk,
                                                 title=video.title,
                                                 video_id=video.video_id,
                                                 description=video.description,
                                                 org=video.org_id))
        self.assertDictEqual(dict(category), dict(name=video.category.name,
                                                  image_url=CategoryReadSerializer().get_image_url(video.category)))

    def test_story_by_org_list(self):
        url = '/api/v1/stories/org/%d/' % self.uganda.pk
        url1 = '/api/v1/stories/org/%d/' % self.nigeria.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Story.objects.filter(org=self.uganda).count())
        response = self.client.get(url1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Story.objects.filter(org=self.nigeria).count())

    def test_single_story(self):
        url = '/api/v1/stories/%d/' % self.uganda_story.pk
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        story = self.uganda_story
        category = response.data.pop('category')
        self.assertDictEqual(response.data, dict(id=story.pk,
                                                 title=story.title,
                                                 video_id=story.video_id,
                                                 audio_link=story.audio_link,
                                                 summary=story.summary,
                                                 featured=story.featured,
                                                 tags=story.tags,
                                                 images=StoryReadSerializer().get_images(story),
                                                 org=story.org_id))
        self.assertDictEqual(dict(category), dict(name=story.category.name,
                                                  image_url=CategoryReadSerializer().get_image_url(story.category)))
