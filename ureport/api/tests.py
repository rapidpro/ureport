import json

from django.test import TestCase
from django.contrib.auth.models import User
from django.test.client import RequestFactory

from dash.orgs.models import Org
from dash.categories.models import Category

from ureport.polls.models import Poll

from views import get_flow_info


class ApiTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user('some user', 'some@user.com', 's0meus3r')
        self.org = Org.objects.create(subdomain='sub', name='ACME', created_by=self.user, modified_by=self.user)
        self.category = Category.objects.create(name='some category', org=self.org,
                                                created_by=self.user, modified_by=self.user)
        self.poll = Poll(flow_uuid='forestry-that-soar-fire-wordsmithies', title='super poll title', org=self.org,
                         category=self.category, created_by=self.user, modified_by=self.user)
        self.poll.save()

    def tearDown(self):
        self.user.delete()
        self.org.delete()
        self.category.delete()
        self.poll.delete()

    def test_get_existing_flow_info(self):
        request = self.factory.post('/api/flow/1')
        flow_info = json.loads(get_flow_info(request, 1).content)
        self.assertEqual(flow_info['poll_id'], 1)
        self.assertEqual(flow_info['flow_uuid'], 'forestry-that-soar-fire-wordsmithies')
        self.assertEqual(flow_info['title'], 'super poll title')

    def test_get_non_existing_flow_info(self):
        request = self.factory.post('/api/flow/999')
        flow_info = get_flow_info(request, 999)
        self.assertEqual(flow_info.status_code, 404)
        self.assertEqual(flow_info.content, '<h1>Page not found</h1>')
