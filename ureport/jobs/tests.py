from django.test import TestCase
from ureport.jobs.models import Source

__author__ = 'awesome'


class SourceTest(TestCase):
    FB_SOURCE = 'http://www.facebook.com/username'
    TW_SOURCE = 'http://twitter.com/username'
    RSS_SOURCE = 'http://dummy.rss.com/rss.xml'

    def setUp(self):
        self.fb_source = Source.objects.create(source=SourceTest.FB_SOURCE, source_type=Source.FACEBOOK)
        self.tw_source = Source.objects.create(source=SourceTest.TW_SOURCE, widget_id='WIDGETID',
                                               source_type=Source.TWITTER)
        # self.rss_source = Source.objects.create(source=SourceTest.RSS_SOURCE, source_type=Source.RSS)

    def test_get_return_page(self):
        self.assertEqual(self.fb_source.get_return_page(), self.fb_source.source)
        self.assertEqual(self.tw_source.get_return_page(), self.tw_source.source)
        # self.assertEqual(self.rss_source.get_return_page(), 'http://dummy.rss.com')

    def test_get_entries_always_a_list(self):
        self.assertIsInstance(self.fb_source.get_entries(), list)
        self.assertIsInstance(self.tw_source.get_entries(), list)
        # self.assertIsInstance(self.rss_source.get_entries(), list)

    def test_get_username(self):
        self.assertEqual(self.fb_source.get_username(), 'username')
        self.assertEqual(self.tw_source.get_username(), 'username')