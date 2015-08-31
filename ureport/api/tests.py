from collections import OrderedDict
from dash.categories.models import Category
from dash.orgs.models import Org
from dash.stories.models import Story
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase
from ureport.api.serializers import generate_absolute_url_from_file, CategoryReadSerializer, StoryReadSerializer
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
        self.featured_poll = self.create_poll('featured', is_featured=True)
        self.poll_question = PollQuestion.objects.create(poll=self.featured_poll, title='test question',
                                                         ruleset_uuid='uuid', created_by=self.superuser,
                                                         modified_by=self.superuser)
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
            org =orgs[0]
            org.name = name
            org.save()
        else:
            org = Org.objects.create(domain=subdomain, name=name, created_by=user, modified_by=user)

        org.administrators.add(user)

        self.assertEquals(Org.objects.filter(domain=subdomain).count(), 1)
        return Org.objects.get(domain=subdomain)

    def create_poll(self, title, is_featured=False):
        return Poll.objects.create(flow_uuid="uuid-1",
                                    title=title,
                                    category=self.health_uganda,
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
        self.client.login(username=self.superuser.username, password='super')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Org.objects.count())

    def test_single_org(self):
        url = '/api/v1/orgs/%d/' % self.uganda.pk
        self.client.login(username=self.superuser.username, password='super')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        org = self.uganda
        logo_url = generate_absolute_url_from_file(response, org.logo) if org.logo else None
        self.assertDictEqual(response.data, dict(id=org.pk,
                                                 logo_url=logo_url,
                                                 name=org.name,
                                                 language=org.language,
                                                 subdomain=org.subdomain,
                                                 domain=org.domain,
                                                 timezone=org.timezone))

    def test_polls_by_org_list(self):
        url = '/api/v1/polls/org/%d/' % self.uganda.pk
        url2 = '/api/v1/polls/org/%d/' % self.nigeria.pk
        self.client.login(username=self.superuser.username, password='super')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Poll.objects.filter(org=self.uganda).count())
        response = self.client.get(url2)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Poll.objects.filter(org=self.nigeria).count())

    def test_single_poll(self):
        url = '/api/v1/polls/%d/' % self.reg_poll.pk
        self.client.login(username=self.superuser.username, password='super')
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

    def test_featured_poll(self):
        url = '/api/v1/polls/org/%d/featured/' % self.uganda.pk
        self.client.login(username=self.superuser.username, password='super')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        poll = self.featured_poll
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
        self.client.login(username=self.superuser.username, password='super')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], NewsItem.objects.filter(org=self.uganda).count())
        response = self.client.get(url1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], NewsItem.objects.filter(org=self.nigeria).count())

    def test_single_news_item(self):
        url = '/api/v1/news/%d/' % self.news_item.pk
        self.client.login(username=self.superuser.username, password='super')
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
        self.client.login(username=self.superuser.username, password='super')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Video.objects.filter(org=self.uganda).count())
        response = self.client.get(url1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Video.objects.filter(org=self.nigeria).count())

    def test_single_video(self):
        url = '/api/v1/videos/%d/' % self.uganda_video.pk
        self.client.login(username=self.superuser.username, password='super')
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
        self.client.login(username=self.superuser.username, password='super')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Story.objects.filter(org=self.uganda).count())
        response = self.client.get(url1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], Story.objects.filter(org=self.nigeria).count())

    def test_single_story(self):
        url = '/api/v1/stories/%d/' % self.uganda_story.pk
        self.client.login(username=self.superuser.username, password='super')
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
