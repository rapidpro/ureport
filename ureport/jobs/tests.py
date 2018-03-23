# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals


from django.urls import reverse
from mock import patch
from ureport.jobs.models import JobSource
from ureport.tests import UreportJobsTest


class JobSourceTest(UreportJobsTest):

    def setUp(self):
        super(JobSourceTest, self).setUp()

        self.fb_source_nigeria = self.create_fb_job_source(self.nigeria, self.nigeria.name)
        self.fb_source_uganda = self.create_fb_job_source(self.uganda, self.uganda.name)

        self.tw_source_nigeria = self.create_tw_job_source(self.nigeria, self.nigeria.name)
        self.tw_source_uganda = self.create_tw_job_source(self.uganda, self.uganda.name)

        with patch('feedparser.parse') as mock:
            mock.return_value = dict(feed=dict(title=self.nigeria.name))
            self.rss_source_nigeria = self.create_rss_job_source(self.nigeria, self.nigeria.name)

        with patch('feedparser.parse') as mock:
            mock.return_value = dict(feed=dict(title=self.uganda.name))
            self.rss_source_uganda = self.create_rss_job_source(self.uganda, self.uganda.name)

    def test_get_return_page(self):
        self.assertEqual(self.fb_source_nigeria.get_return_page(), self.fb_source_nigeria.source_url)
        self.assertEqual(self.tw_source_nigeria.get_return_page(), self.tw_source_nigeria.source_url)
        self.assertEqual(self.rss_source_nigeria.get_return_page(), 'http://dummy.rss.com')

    def test_get_entries_always_a_list(self):
        self.assertIsInstance(self.fb_source_nigeria.get_entries(), list)
        self.assertIsInstance(self.tw_source_nigeria.get_entries(), list)
        with patch('feedparser.parse') as mock:
            mock.return_value = dict(feed=dict(entries=['data']))
            self.assertIsInstance(self.rss_source_nigeria.get_entries(), list)

    def test_get_username(self):
        self.assertEqual(self.fb_source_nigeria.get_username(), self.nigeria.name)
        self.assertEqual(self.tw_source_nigeria.get_username(), self.nigeria.name)
        self.assertIsNone(self.rss_source_nigeria.get_username())

    def test_list_job_source(self):
        list_url = reverse('jobs.jobsource_list')

        response = self.client.get(list_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(list_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(response.context['object_list']), 3)
        self.assertTrue(self.fb_source_uganda in response.context['object_list'])
        self.assertTrue(self.tw_source_uganda in response.context['object_list'])
        self.assertTrue(self.rss_source_uganda in response.context['object_list'])
        self.assertFalse(self.fb_source_nigeria in response.context['object_list'])
        self.assertFalse(self.tw_source_nigeria in response.context['object_list'])
        self.assertFalse(self.rss_source_nigeria in response.context['object_list'])

    def test_create_job_source(self):
        create_url = reverse('jobs.jobsource_create')

        response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)

        self.assertEquals(len(response.context['form'].fields), 2)
        self.assertEquals(set(['source_type', 'loc']),
                          set(response.context['form'].fields))

        response = self.client.get(create_url + "?source_type=" + JobSource.FACEBOOK, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)

        self.assertEquals(len(response.context['form'].fields), 4)
        self.assertEquals(set(['is_featured', 'title', 'source_url', 'loc']),
                          set(response.context['form'].fields))

        response = self.client.get(create_url + "?source_type=" + JobSource.TWITTER, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)

        self.assertEquals(len(response.context['form'].fields), 5)
        self.assertEquals(set(['is_featured', 'title', 'source_url', 'widget_id', 'loc']),
                          set(response.context['form'].fields))

        response = self.client.post(create_url + "?source_type=" + JobSource.FACEBOOK, dict(),
                                    SERVER_NAME='uganda.ureport.io')
        self.assertTrue(response.context['form'].errors)
        self.assertEquals(len(response.context['form'].errors), 2)
        self.assertTrue('title' in response.context['form'].errors)
        self.assertTrue('source_url' in response.context['form'].errors)

        self.assertEquals(6, JobSource.objects.all().count())

        post_data = dict(title='Kampala Jobs', source_url='http://facebook.com/kampalajobs')

        response = self.client.post(create_url + "?source_type=" + JobSource.FACEBOOK,
                                    post_data,
                                    follow=True,
                                    SERVER_NAME='uganda.ureport.io')

        self.assertEquals(7, JobSource.objects.all().count())
        self.assertTrue(JobSource.objects.filter(title='Kampala Jobs'))

        job_source = JobSource.objects.filter(title='Kampala Jobs').first()
        self.assertEquals(job_source.source_type, JobSource.FACEBOOK)
        self.assertEquals(job_source.org, self.uganda)

        self.assertEquals(response.request['PATH_INFO'], reverse('jobs.jobsource_list'))

    def test_update_job_source(self):
        update_url_fb_uganda = reverse('jobs.jobsource_update', args=[self.fb_source_uganda.pk])
        update_url_fb_nigeria = reverse('jobs.jobsource_update', args=[self.fb_source_nigeria.pk])

        response = self.client.get(update_url_fb_nigeria, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(update_url_fb_uganda, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(update_url_fb_nigeria, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(update_url_fb_uganda, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)

        self.assertEquals(len(response.context['form'].fields), 5)
        self.assertEquals(set(['is_featured', 'title', 'source_url', 'loc', 'is_active']),
                          set(response.context['form'].fields))

        response = self.client.post(update_url_fb_uganda, dict(), SERVER_NAME='uganda.ureport.io')
        self.assertTrue(response.context['form'].errors)

        self.assertEquals(len(response.context['form'].errors), 2)
        self.assertTrue('title' in response.context['form'].errors)
        self.assertTrue('source_url' in response.context['form'].errors)

        self.assertFalse(JobSource.objects.filter(title='Uganda Jobs').first())

        post_data = dict(is_active=True, title='Uganda Jobs', source_url='http://facebook.com/ugandajobs')

        response = self.client.post(update_url_fb_uganda, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertTrue(JobSource.objects.filter(title='Uganda Jobs').first())

        job_source = JobSource.objects.filter(title='Uganda Jobs').first()
        self.assertEquals(job_source.source_url, 'http://facebook.com/ugandajobs')

        update_url_tw_uganda = reverse('jobs.jobsource_update', args=[self.tw_source_uganda.pk])

        response = self.client.get(update_url_tw_uganda, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)

        self.assertEquals(len(response.context['form'].fields), 6)
        self.assertEquals(set(['is_featured', 'title', 'source_url', 'widget_id', 'loc', 'is_active']),
                          set(response.context['form'].fields))
