from django.core.urlresolvers import reverse
from ureport.tests import UreportJobsTest


class JobSourceTest(UreportJobsTest):

    def setUp(self):
        super(JobSourceTest, self).setUp()

        self.uganda = self.create_org('uganda', self.admin)
        self.nigeria = self.create_org('nigeria', self.admin)

        self.fb_source_nigeria = self.create_fb_job_source(self.nigeria, self.nigeria.name)
        self.fb_source_uganda = self.create_fb_job_source(self.uganda, self.uganda.name)

        self.tw_source_nigeria = self.create_tw_job_source(self.nigeria, self.nigeria.name)
        self.tw_source_uganda = self.create_tw_job_source(self.uganda, self.uganda.name)

        #self.rss_source_nigeria = self.create_rss_job_source(self.nigeria, self.nigeria.name)
        #self.rss_source_uganda = self.create_rss_job_source(self.uganda, self.uganda.name)

    def test_get_return_page(self):
        self.assertEqual(self.fb_source_nigeria.get_return_page(), self.fb_source_nigeria.source_url)
        self.assertEqual(self.tw_source_nigeria.get_return_page(), self.tw_source_nigeria.source_url)
        #self.assertEqual(self.rss_source_nigeria.get_return_page(), 'http://dummy.rss.com')

    def test_get_entries_always_a_list(self):
        self.assertIsInstance(self.fb_source_nigeria.get_entries(), list)
        self.assertIsInstance(self.tw_source_nigeria.get_entries(), list)
        #self.assertIsInstance(self.rss_source_nigeria.get_entries(), list)

    def test_get_username(self):
        self.assertEqual(self.fb_source_nigeria.get_username(), self.nigeria.name)
        self.assertEqual(self.tw_source_nigeria.get_username(), self.nigeria.name)
        #self.assertIsNone(self.rss_source_nigeria.get_username())

    def test_list_job_source(self):
        list_url = reverse('jobs.jobsource_list')

        response = self.client.get(list_url, SERVER_NAME='uganda.ureport.oi')
        self.assertLoginRedirect(response)

        self.login(self.admin)

        response = self.client.get(list_url, SERVER_NAME='uganda.ureport.oi')
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(response.context['object_list']), 2)
        self.assertTrue(self.fb_source_uganda in response.context['object_list'])
        self.assertTrue(self.tw_source_uganda in response.context['object_list'])
        self.assertFalse(self.fb_source_nigeria in response.context['object_list'])
        self.assertFalse(self.tw_source_nigeria in response.context['object_list'])

    def test_create_job_source(self):
        create_url = reverse('jobs.jobsource_create')

        response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertTrue('form' in response.context)

        self.assertEquals(len(response.context['form'].fields), 6)
        self.assertEquals(set(['is_featured', 'title', 'source_type', 'source_url', 'widget_id', 'loc']),
                          set(response.context['form'].fields))

        response = self.client.post(create_url, dict(), SERVER_NAME='uganda.ureport.io')
        self.assertTrue(response.context['form'].errors)

