import json
from urllib import urlencode
from dash.api import API
from dash.stories.models import Story, StoryImage
from django.core.urlresolvers import reverse


import mock
from dash.categories.models import Category
from ureport.news.models import Video, NewsItem
from ureport.polls.models import Poll, PollQuestion
from ureport.tests import DashTest, MockAPI


class PublicTest(DashTest):
    def setUp(self):
        super(PublicTest, self).setUp()
        self.uganda = self.create_org('uganda', self.admin)
        self.nigeria = self.create_org('nigeria', self.admin)


        self.health_uganda = Category.objects.create(org=self.uganda,
                                                     name="Health",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.education_nigeria = Category.objects.create(org=self.nigeria,
                                                         name="Education",
                                                         created_by=self.admin,
                                                         modified_by=self.admin)

    @mock.patch('dash.orgs.models.API', MockAPI)
    def test_index(self):
        home_url = reverse('public.index')

        response = self.client.get(home_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.nigeria)
        self.assertEquals(response.context['view'].template_name, 'public/index.html')

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertIsNone(response.context['latest_poll'])
        self.assertFalse('trending_words' in response.context)
        self.assertTrue('recent_polls' in response.context)
        self.assertFalse(response.context['recent_polls'])

        self.assertFalse(response.context['stories'])
        self.assertFalse(response.context['other_stories'])
        self.assertFalse(response.context['videos'])
        self.assertFalse(response.context['news'])
        self.assertTrue('most_active_regions' in response.context)

        poll1 = Poll.objects.create(flow_id=1,
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertIsNone(response.context['latest_poll'])
        self.assertFalse('trending_words' in response.context)
        self.assertTrue('recent_polls' in response.context)
        self.assertFalse(response.context['recent_polls'])

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_id='101',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertEquals(poll1, response.context['latest_poll'])
        self.assertTrue('trending_words' in response.context)
        self.assertTrue('recent_polls' in response.context)
        self.assertFalse(response.context['recent_polls'])

        poll2 = Poll.objects.create(flow_id=2,
                                        title="Poll 2",
                                        category=self.education_nigeria,
                                        org=self.nigeria,
                                        created_by=self.admin,
                                        modified_by=self.admin)

        poll2_question = PollQuestion.objects.create(poll=poll2,
                                                     title='question poll 2',
                                                     ruleset_id='202',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertEquals(poll1, response.context['latest_poll'])
        self.assertTrue('trending_words' in response.context)
        self.assertTrue('recent_polls' in response.context)
        self.assertFalse(response.context['recent_polls'])

        poll3 = Poll.objects.create(flow_id=3,
                                    title="Poll 3",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll3_question = PollQuestion.objects.create(poll=poll3,
                                                     title='question poll 3',
                                                     ruleset_id='303',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertEquals(poll3, response.context['latest_poll'])
        self.assertTrue('trending_words' in response.context)
        self.assertTrue('recent_polls' in response.context)
        self.assertTrue(response.context['recent_polls'])
        self.assertTrue(poll1 in response.context['recent_polls'])

        story1 = Story.objects.create(title="story 1",
                                      featured=True,
                                      content="body contents 1",
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['stories'])
        self.assertTrue(story1 in response.context['stories'])
        self.assertFalse(response.context['other_stories'])

        story2 = Story.objects.create(title="story 2",
                                      featured=True,
                                      content="body contents 2",
                                      org=self.nigeria,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['stories'])
        self.assertTrue(story1 in response.context['stories'])
        self.assertFalse(response.context['other_stories'])

        story3 = Story.objects.create(title="story 3",
                                      featured=False,
                                      content="body contents 3",
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['stories'])
        self.assertTrue(story1 in response.context['stories'])
        self.assertTrue(response.context['other_stories'])
        self.assertTrue(story3 in response.context['other_stories'])

        video1 = Video.objects.create(title='video 1',
                                      video_id='video_1',
                                      category=self.health_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['videos'])
        self.assertTrue(video1 in response.context['videos'])

        video2 = Video.objects.create(title='video 2',
                                      video_id='video_2',
                                      category=self.education_nigeria,
                                      org=self.nigeria,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['videos'])
        self.assertTrue(video1 in response.context['videos'])
        self.assertTrue(video2 not in response.context['videos'])

        video3 = Video.objects.create(title='video 3',
                                      video_id='video_3',
                                      category=self.health_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['videos'])
        self.assertTrue(video1 in response.context['videos'])
        self.assertTrue(video2 not in response.context['videos'])
        self.assertTrue(video3 in response.context['videos'])

        video1.is_active = False
        video1.save()

        response = self.client.get(home_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['videos'])
        self.assertTrue(video1 not in response.context['videos'])
        self.assertTrue(video2 not in response.context['videos'])
        self.assertTrue(video3 in response.context['videos'])



    def test_about(self):
        about_url = reverse('public.about')

        response = self.client.get(about_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/about/')
        self.assertEquals(response.context['org'], self.nigeria)
        self.assertEquals(response.context['view'].template_name, 'public/about.html')

        response = self.client.get(about_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/about/')
        self.assertEquals(response.context['org'], self.uganda)

        video1 = Video.objects.create(title='video 1',
                                      video_id='video_1',
                                      category=self.health_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)


        response = self.client.get(about_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/about/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['videos'])
        self.assertTrue(video1 in response.context['videos'])

        video2 = Video.objects.create(title='video 2',
                                      video_id='video_2',
                                      category=self.education_nigeria,
                                      org=self.nigeria,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(about_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/about/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['videos'])
        self.assertTrue(video1 in response.context['videos'])
        self.assertTrue(video2 not in response.context['videos'])

        video3 = Video.objects.create(title='video 3',
                                      video_id='video_3',
                                      category=self.health_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(about_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/about/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['videos'])
        self.assertTrue(video1 in response.context['videos'])
        self.assertTrue(video2 not in response.context['videos'])
        self.assertTrue(video3 in response.context['videos'])

        video1.is_active = False
        video1.save()

        response = self.client.get(about_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/about/')
        self.assertEquals(response.context['org'], self.uganda)

        self.assertTrue(response.context['videos'])
        self.assertTrue(video1 not in response.context['videos'])
        self.assertTrue(video2 not in response.context['videos'])
        self.assertTrue(video3 in response.context['videos'])


    def test_join_engage(self):
        join_engage_url = reverse('public.join')

        response = self.client.get(join_engage_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/join/')
        self.assertEquals(response.context['org'], self.nigeria)
        self.assertEquals(response.context['view'].template_name, 'public/join_engage.html')

        response = self.client.get(join_engage_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/join/')
        self.assertEquals(response.context['org'], self.uganda)

    def test_ureporters(self):
        ureporters_url = reverse('public.ureporters')

        response = self.client.get(ureporters_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/ureporters/')
        self.assertEquals(response.context['org'], self.nigeria)
        self.assertEquals(response.context['view'].template_name, 'public/ureporters.html')

        response = self.client.get(ureporters_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/ureporters/')
        self.assertEquals(response.context['org'], self.uganda)

    @mock.patch('dash.orgs.models.API', MockAPI)
    def test_polls_list(self):
        polls_url = reverse('public.polls')

        response = self.client.get(polls_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/polls/')
        self.assertEquals(response.context['org'], self.nigeria)
        self.assertEquals(response.context['tab'], 'list')
        self.assertEquals(response.context['view'].template_name, 'public/polls.html')
        self.assertFalse(response.context['latest_poll'])
        self.assertFalse(response.context['polls'])
        self.assertFalse(response.context['related_stories'])

        self.assertEquals(len(response.context['categories']), 1)
        self.assertTrue(self.education_nigeria in response.context['categories'])
        self.assertTrue(self.health_uganda not in response.context['categories'])


        education_uganda = Category.objects.create(org=self.uganda,
                                                   name="Education",
                                                   created_by=self.admin,
                                                   modified_by=self.admin)

        poll1 = Poll.objects.create(flow_id=1,
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_id='101',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        poll2 = Poll.objects.create(flow_id=2,
                                    title="Poll 2",
                                    category=education_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2_question = PollQuestion.objects.create(poll=poll2,
                                                     title='question poll 2',
                                                     ruleset_id='102',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        poll3 = Poll.objects.create(flow_id=3,
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll3_question = PollQuestion.objects.create(poll=poll3,
                                                     title='question poll 3',
                                                     ruleset_id='103',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        poll4 = Poll.objects.create(flow_id=4,
                                    title="Poll 4",
                                    category=self.education_nigeria,
                                    org=self.nigeria,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll4_question = PollQuestion.objects.create(poll=poll4,
                                                     title='question poll 4',
                                                     ruleset_id='104',
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        response = self.client.get(polls_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/polls/')
        self.assertEquals(response.context['org'], self.nigeria)
        self.assertEquals(response.context['tab'], 'list')
        self.assertEquals(response.context['view'].template_name, 'public/polls.html')
        self.assertEquals(response.context['latest_poll'], poll4)

        self.assertEquals(len(response.context['categories']), 1)
        self.assertTrue(self.education_nigeria in response.context['categories'])
        self.assertTrue(self.health_uganda not in response.context['categories'])
        self.assertTrue(education_uganda not in response.context['categories'])

        self.assertEquals(len(response.context['polls']), 1)
        self.assertTrue(poll4 in response.context['polls'])
        self.assertTrue(poll1 not in response.context['polls'])
        self.assertTrue(poll2 not in response.context['polls'])
        self.assertTrue(poll3 not in response.context['polls'])

        self.assertFalse(response.context['related_stories'])

        story1 = Story.objects.create(title="story 1",
                                      content="body contents 1",
                                      category=self.health_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        story2 = Story.objects.create(title="story 2",
                                      content="body contents 2",
                                      category=education_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        story3 = Story.objects.create(title="story 3",
                                      content="body contents 3",
                                      category=self.health_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        story4 = Story.objects.create(title="story 4",
                                      content="body contents 4",
                                      category=self.education_nigeria,
                                      org=self.nigeria,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(polls_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(len(response.context['related_stories']), 1)
        self.assertTrue(story4 in response.context['related_stories'])
        self.assertTrue(story1 not in response.context['related_stories'])
        self.assertTrue(story2 not in response.context['related_stories'])
        self.assertTrue(story3 not in response.context['related_stories'])

        response = self.client.get(polls_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], '/polls/')
        self.assertEquals(response.context['org'], self.uganda)
        self.assertEquals(response.context['latest_poll'], poll3)

        self.assertEquals(len(response.context['categories']), 2)
        self.assertTrue(self.education_nigeria not in response.context['categories'])
        self.assertTrue(self.health_uganda in response.context['categories'])
        self.assertTrue(education_uganda in response.context['categories'])
        self.assertEquals(response.context['categories'][0], education_uganda)
        self.assertEquals(response.context['categories'][1], self.health_uganda)

        self.assertEquals(len(response.context['polls']), 3)
        self.assertTrue(poll4 not in response.context['polls'])
        self.assertTrue(poll1 in response.context['polls'])
        self.assertTrue(poll2 in response.context['polls'])
        self.assertTrue(poll3 in response.context['polls'])
        self.assertEquals(response.context['polls'][0], poll3)
        self.assertEquals(response.context['polls'][1], poll2)
        self.assertEquals(response.context['polls'][2], poll1)

        self.assertEquals(len(response.context['related_stories']), 2)
        self.assertTrue(story4 not in response.context['related_stories'])
        self.assertTrue(story1 in response.context['related_stories'])
        self.assertTrue(story2 not in response.context['related_stories'])
        self.assertTrue(story3 in response.context['related_stories'])
        self.assertEquals(response.context['related_stories'][0], story3)
        self.assertEquals(response.context['related_stories'][1], story1)

        story1.featured = True
        story1.save()

        response = self.client.get(polls_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(len(response.context['related_stories']), 2)
        self.assertTrue(story4 not in response.context['related_stories'])
        self.assertTrue(story1 in response.context['related_stories'])
        self.assertTrue(story2 not in response.context['related_stories'])
        self.assertTrue(story3 in response.context['related_stories'])
        self.assertEquals(response.context['related_stories'][0], story1)
        self.assertEquals(response.context['related_stories'][1], story3)

        story1.is_active = False
        story1.save()

        response = self.client.get(polls_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(len(response.context['related_stories']), 1)
        self.assertTrue(story4 not in response.context['related_stories'])
        self.assertTrue(story1 not in response.context['related_stories'])
        self.assertTrue(story2 not in response.context['related_stories'])
        self.assertTrue(story3 in response.context['related_stories'])
        self.assertEquals(response.context['related_stories'][0], story3)

        poll1.is_featured = True
        poll1.save()

        response = self.client.get(polls_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.context['latest_poll'], poll1)

        self.assertEquals(len(response.context['categories']), 2)
        self.assertTrue(self.education_nigeria not in response.context['categories'])
        self.assertTrue(self.health_uganda in response.context['categories'])
        self.assertTrue(education_uganda in response.context['categories'])
        self.assertEquals(response.context['categories'][0], education_uganda)
        self.assertEquals(response.context['categories'][1], self.health_uganda)

        self.assertEquals(len(response.context['polls']), 3)
        self.assertTrue(poll4 not in response.context['polls'])
        self.assertTrue(poll1 in response.context['polls'])
        self.assertTrue(poll2 in response.context['polls'])
        self.assertTrue(poll3 in response.context['polls'])
        self.assertEquals(response.context['polls'][0], poll3)
        self.assertEquals(response.context['polls'][1], poll2)
        self.assertEquals(response.context['polls'][2], poll1)

        poll3.is_active = False
        poll3.save()

        response = self.client.get(polls_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.context['latest_poll'], poll1)

        self.assertEquals(len(response.context['polls']), 2)
        self.assertTrue(poll4 not in response.context['polls'])
        self.assertTrue(poll1 in response.context['polls'])
        self.assertTrue(poll2 in response.context['polls'])
        self.assertTrue(poll3 not in response.context['polls'])
        self.assertEquals(response.context['polls'][0], poll2)
        self.assertEquals(response.context['polls'][1], poll1)

        education_uganda.is_active = False
        education_uganda.save()

        response = self.client.get(polls_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.context['latest_poll'], poll1)

        self.assertEquals(len(response.context['polls']), 1)
        self.assertTrue(poll4 not in response.context['polls'])
        self.assertTrue(poll1 in response.context['polls'])
        self.assertTrue(poll2 not in response.context['polls'])
        self.assertTrue(poll3 not in response.context['polls'])
        self.assertEquals(response.context['polls'][0], poll1)

    @mock.patch('dash.orgs.models.API', MockAPI)
    def test_polls_read(self):
        poll1 = Poll.objects.create(flow_id=1,
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2 = Poll.objects.create(flow_id=2,
                                    title="Poll 2",
                                    category=self.education_nigeria,
                                    org=self.nigeria,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        uganda_poll_read_url = reverse('public.poll_read', args=[poll1.pk])
        nigeria_poll_read_url = reverse('public.poll_read', args=[poll2.pk])

        response = self.client.get(uganda_poll_read_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertEquals(response.context['object'], poll1)

        response = self.client.get(nigeria_poll_read_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 404)

        poll1.is_active = False
        poll1.save()

        response = self.client.get(uganda_poll_read_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 404)

    @mock.patch('dash.orgs.models.API', MockAPI)
    def test_boundary_view(self):
        country_boundary_url = reverse('public.boundaries')
        state_boundary_url = reverse('public.boundaries', args=['R123'])

        mock_api = MockAPI(API)

        response = self.client.get(country_boundary_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)

        output = dict(
                   type="FeatureCollection",
                   features=[
                       dict(
                           type='Feature',
                           properties=dict(
                               id="R3713501",
                               level=1,
                               name="Abia"
                           ),
                           geometry=dict(
                               type="MultiPolygon",
                               coordinates=[
                                   [
                                       [
                                           [7, 5]
                                       ]
                                   ]
                               ]
                           )
                       )
                   ]
            )

        self.assertEquals(json.dumps(output), response.content)

        response = self.client.get(state_boundary_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)

        output = dict(type="FeatureCollection",
                    features=[dict(type='Feature',
                                   properties=dict(id="R3713502",
                                                   level=2,
                                                   name="Aba North"),
                                   geometry=dict(type="MultiPolygon",
                                                 coordinates=[[[[8, 4]]]]
                                                 )
                                   )
                            ]
                    )

        self.assertEquals(json.dumps(output), response.content)

    def test_stories_list(self):
        stories_url = reverse('public.stories')

        education_uganda = Category.objects.create(org=self.uganda,
                                                   name="Education",
                                                   created_by=self.admin,
                                                   modified_by=self.admin)

        story1 = Story.objects.create(title="story 1",
                                      content="body contents 1",
                                      category=self.health_uganda,
                                      featured=True,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        story2 = Story.objects.create(title="story 2",
                                      content="body contents 2",
                                      category=education_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        story3 = Story.objects.create(title="story 3",
                                      content="body contents 3",
                                      category=self.health_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        story4 = Story.objects.create(title="story 4",
                                      content="body contents 4",
                                      category=self.education_nigeria,
                                      org=self.nigeria,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        response = self.client.get(stories_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.context['org'], self.nigeria)
        self.assertEquals(len(response.context['categories']), 1)
        self.assertEquals(response.context['categories'][0], self.education_nigeria)
        self.assertEquals(len(response.context['other_stories']), 1)
        self.assertEquals(response.context['other_stories'][0], story4)
        self.assertFalse(response.context['featured'])

        response = self.client.get(stories_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.context['org'], self.uganda)
        self.assertEquals(len(response.context['categories']), 2)
        self.assertEquals(response.context['categories'][0], education_uganda)
        self.assertEquals(response.context['categories'][1], self.health_uganda)

        self.assertEquals(len(response.context['other_stories']), 2)
        self.assertEquals(response.context['other_stories'][0], story3)
        self.assertEquals(response.context['other_stories'][1], story2)
        self.assertEquals(len(response.context['featured']), 1)
        self.assertEquals(response.context['featured'][0], story1)

        story2.is_active = False
        story2.save()

        response = self.client.get(stories_url, SERVER_NAME='uganda.ureport.io')

        self.assertEquals(len(response.context['other_stories']), 1)
        self.assertEquals(response.context['other_stories'][0], story3)

        story2.is_active = True
        story2.save()
        education_uganda.is_active = False
        education_uganda.save()

        self.assertEquals(len(response.context['other_stories']), 1)
        self.assertEquals(response.context['other_stories'][0], story3)

    def test_story_read(self):

        education_uganda = Category.objects.create(org=self.uganda,
                                                   name="Education",
                                                   created_by=self.admin,
                                                   modified_by=self.admin)


        story1 = Story.objects.create(title="story 1",
                                      content="body contents 1",
                                      category=self.health_uganda,
                                      featured=True,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        story2 = Story.objects.create(title="story 2",
                                      content="body contents 2",
                                      category=education_uganda,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        story3 = Story.objects.create(title="story 3",
                                      content="body contents 3",
                                      category=self.health_uganda,
                                      featured=True,
                                      org=self.uganda,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        story4 = Story.objects.create(title="story 4",
                                      content="body contents 4",
                                      category=self.education_nigeria,
                                      org=self.nigeria,
                                      created_by=self.admin,
                                      modified_by=self.admin)

        poll1 = Poll.objects.create(flow_id=1,
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2 = Poll.objects.create(flow_id=2,
                                    title="Poll 2",
                                    category=education_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        uganda_story_read_url = reverse('public.story_read', args=[story1.pk])
        nigeria_story_read_url = reverse('public.story_read', args=[story4.pk])

        response = self.client.get(nigeria_story_read_url, SERVER_NAME='uganda.uerport.io')
        self.assertEquals(response.status_code, 404)

        response = self.client.get(uganda_story_read_url, SERVER_NAME='uganda.uerport.io')
        self.assertEquals(response.status_code, 200)
        self.assertEquals(response.context['org'], self.uganda)

        self.assertEquals(response.context['object'], story1)
        self.assertEquals(len(response.context['categories']), 2)
        self.assertEquals(response.context['categories'][0], education_uganda)
        self.assertEquals(response.context['categories'][1], self.health_uganda)

        self.assertEquals(len(response.context['other_stories']), 1)
        self.assertEquals(response.context['other_stories'][0], story2)

        self.assertEquals(len(response.context['related_polls']), 1)
        self.assertEquals(response.context['related_polls'][0], poll1)

        self.assertEquals(len(response.context['related_stories']), 1)
        self.assertEquals(response.context['related_stories'][0], story3)

        self.assertFalse(response.context['story_featured_images'])

        story_image1 = StoryImage.objects.create(story=story1, image='stories/someimage.jpg', name='image 1',
                                                 created_by=self.admin, modified_by=self.admin)

        response = self.client.get(uganda_story_read_url, SERVER_NAME='uganda.uerport.io')

        self.assertEquals(len(response.context['story_featured_images']), 1)
        self.assertEquals(response.context['story_featured_images'][0], story_image1)

        story_image2 = StoryImage.objects.create(story=story1, image='stories/someimage.jpg', name='image 2',
                                                 created_by=self.admin, modified_by=self.admin)

        response = self.client.get(uganda_story_read_url, SERVER_NAME='uganda.uerport.io')

        self.assertEquals(len(response.context['story_featured_images']), 2)
        self.assertEquals(response.context['story_featured_images'][0], story_image2)
        self.assertEquals(response.context['story_featured_images'][1], story_image1)
        
        story_image2.is_active = False
        story_image2.save()
        
        response = self.client.get(uganda_story_read_url, SERVER_NAME='uganda.uerport.io')

        self.assertEquals(len(response.context['story_featured_images']), 1)
        self.assertEquals(response.context['story_featured_images'][0], story_image1)
        
        story_image1.image = ''
        story_image1.save()
        
        response = self.client.get(uganda_story_read_url, SERVER_NAME='uganda.uerport.io')
        self.assertFalse(response.context['story_featured_images'])


    def test_poll_question_results(self):
        poll1 = Poll.objects.create(flow_id=1,
                                    title="Poll 1",
                                    category=self.health_uganda,
                                    org=self.uganda,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll1_question = PollQuestion.objects.create(poll=poll1,
                                                     title='question poll 1',
                                                     ruleset_id=101,
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        poll2 = Poll.objects.create(flow_id=2,
                                    title="Poll 2",
                                    category=self.education_nigeria,
                                    org=self.nigeria,
                                    created_by=self.admin,
                                    modified_by=self.admin)

        poll2_question = PollQuestion.objects.create(poll=poll2,
                                                     title='question poll 2',
                                                     ruleset_id=102,
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        uganda_results_url = reverse('public.pollquestion_results', args=[poll1_question.pk])
        nigeria_results_url = reverse('public.pollquestion_results', args=[poll2_question.pk])

        with mock.patch('dash.api.API.get_ruleset_results') as mock_results:
            mock_results.return_value = [dict(open_ended=False,
                                      set=3462,
                                      unset=3694,
                                      categories=[
                                          dict(count=2210,
                                               label='Yes'
                                               ),
                                          dict(count=1252,
                                               label='No'
                                               )
                                          ],
                                      label='All')
                                      ]


            response = self.client.get(nigeria_results_url, SERVER_NAME='uganda.ureport.io')
            self.assertEquals(response.status_code, 404)

            response = self.client.get(uganda_results_url, SERVER_NAME='uganda.ureport.io')
            self.assertEquals(response.status_code, 200)
            mock_results.assert_called_with(poll1_question.ruleset_id, segment=None)

            response = self.client.get(uganda_results_url + "?" + urlencode(dict(segment=json.dumps(dict(location='State')))), SERVER_NAME='uganda.ureport.io')
            mock_results.assert_called_with(poll1_question.ruleset_id, segment=dict(location='State'))


    def test_reporters_results(self):
        reporters_results = reverse('public.contact_field_results')

        response = self.client.get(reporters_results, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)

        self.assertEquals(response.content, "[]")

        with mock.patch('dash.api.API.get_contact_field_results') as mock_results:
            mock_results.return_value = "API_RESULTS"

            with mock.patch('dash.orgs.models.Org.organize_categories_data') as mock_organize:
                mock_organize.return_value = "ORGANIZED"

                response = self.client.get(reporters_results + "?" + urlencode(dict(contact_field='field_name')), SERVER_NAME='uganda.ureport.io')
                self.assertEquals(response.status_code, 200)
                self.assertEquals(response.content, json.dumps("ORGANIZED"))
                mock_results.assert_called_with('field_name', None)
                mock_organize.assert_called_with('field_name', "API_RESULTS")

                response = self.client.get(reporters_results + "?" + urlencode(dict(contact_field='field_name', segment=json.dumps(dict(location='State')))), SERVER_NAME='uganda.ureport.io')
                self.assertEquals(response.status_code, 200)
                self.assertEquals(response.content, json.dumps("ORGANIZED"))
                mock_results.assert_called_with('field_name', dict(location='State'))
                mock_organize.assert_called_with('field_name', "API_RESULTS")



    def test_news(self):
        news_url = reverse('public.news')

        self.uganda_news1 = NewsItem.objects.create(title='uganda news 1',
                                                    description='uganda description 1',
                                                    link='http://uganda.ug',
                                                    category=self.health_uganda,
                                                    org=self.uganda,
                                                    created_by=self.admin,
                                                    modified_by=self.admin)

        response = self.client.get(news_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)

        self.assertEquals(json.loads(response.content), dict(next=False, news=[self.uganda_news1.as_brick_json()]))

        response = self.client.get(news_url + "?page=1", SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)

        self.assertEquals(json.loads(response.content), dict(next=False, news=[self.uganda_news1.as_brick_json()]))

        self.uganda_news2 = NewsItem.objects.create(title='uganda news 2',
                                                    description='uganda description 2',
                                                    link='http://uganda2.ug',
                                                    category=self.health_uganda,
                                                    org=self.uganda,
                                                    created_by=self.admin,
                                                    modified_by=self.admin)

        self.uganda_news3 = NewsItem.objects.create(title='uganda news 3',
                                                    description='uganda description 3',
                                                    link='http://uganda3.ug',
                                                    category=self.health_uganda,
                                                    org=self.uganda,
                                                    created_by=self.admin,
                                                    modified_by=self.admin)

        self.uganda_news4 = NewsItem.objects.create(title='uganda news 4',
                                                    description='uganda description 4',
                                                    link='http://uganda4.ug',
                                                    category=self.health_uganda,
                                                    org=self.uganda,
                                                    created_by=self.admin,
                                                    modified_by=self.admin)

        self.uganda_news5 = NewsItem.objects.create(title='uganda news 5',
                                                    description='uganda description 5',
                                                    link='http://uganda.ug',
                                                    category=self.health_uganda,
                                                    org=self.uganda,
                                                    created_by=self.admin,
                                                    modified_by=self.admin)

        response = self.client.get(news_url + "?page=1", SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)

        self.assertEquals(json.loads(response.content), dict(next=True, news=[self.uganda_news5.as_brick_json(),
                                                                              self.uganda_news4.as_brick_json(),
                                                                              self.uganda_news3.as_brick_json(),
                                                                              ]))

        response = self.client.get(news_url + "?page=2", SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)

        self.assertEquals(json.loads(response.content), dict(next=False, news=[self.uganda_news2.as_brick_json(),
                                                                              self.uganda_news1.as_brick_json(),
                                                                              ]))

        response = self.client.get(news_url + "?page=3", SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)

        self.assertEquals(json.loads(response.content), dict(next=False, news=[]))
