from django.conf import settings
from django.core.urlresolvers import reverse
from ureport.assets.models import Image
from ureport.tests import DashTest


class ImageTest(DashTest):

    def setUp(self):
        super(ImageTest, self).setUp()

        self.uganda = self.create_org('uganda', self.admin)
        self.nigeria = self.create_org('nigeria', self.admin)

    def clear_uploads(self):
        import os
        for bg in Image.objects.all():
            os.remove(bg.image.path)

    def test_assets_image(self):
        create_url = reverse('assets.image_create')

        response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(response.context['form'].fields), 4)
        self.assertTrue('org' not in response.context['form'].fields)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "r")

        post_data = dict(name="Orange Pattern", image_type="P", image=upload)
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        uganda_org_bg = Image.objects.order_by('-pk')[0]
        self.assertEquals(uganda_org_bg.org, self.uganda)
        self.assertEquals(uganda_org_bg.name, 'Orange Pattern')

        response = self.client.get(create_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(response.context['form'].fields), 4)
        self.assertTrue('org' not in response.context['form'].fields)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "r")

        post_data = dict(name="Orange Pattern", image_type="P", image=upload)
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.status_code, 200)
        nigeria_org_bg = Image.objects.order_by('-pk')[0]
        self.assertEquals(nigeria_org_bg.org, self.nigeria)
        self.assertEquals(nigeria_org_bg.name, 'Orange Pattern')

        list_url = reverse('assets.image_list')

        response = self.client.get(list_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(len(response.context['object_list']), 1)
        self.assertEquals(response.context['object_list'][0], uganda_org_bg)

        response = self.client.get(list_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(len(response.context['object_list']), 1)
        self.assertEquals(response.context['object_list'][0], nigeria_org_bg)

        uganda_bg_update_url = reverse('assets.image_update', args=[uganda_org_bg.pk])
        nigeria_bg_update_url = reverse('assets.image_update', args=[nigeria_org_bg.pk])

        response = self.client.get(uganda_bg_update_url, SERVER_NAME='nigeria.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(nigeria_bg_update_url, SERVER_NAME='uganda.ureport.io')
        self.assertLoginRedirect(response)

        response = self.client.get(uganda_bg_update_url, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], uganda_bg_update_url)
        self.assertEquals(len(response.context['form'].fields), 5)
        self.assertTrue('org' not in response.context['form'].fields)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "r")
        post_data = dict(name="Orange Pattern Updated", image_type="P", image=upload)
        response = self.client.post(uganda_bg_update_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], list_url)
        self.assertEquals(len(response.context['object_list']), 1)
        self.assertEquals(response.context['object_list'][0].name, "Orange Pattern Updated")

        self.login(self.superuser)
        response = self.client.get(create_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(response.context['form'].fields), 5)
        self.assertTrue('org' in response.context['form'].fields)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "r")

        post_data = dict(name="Blue Pattern", image_type="P", image=upload)
        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertTrue('form' in response.context)
        self.assertTrue('org' in response.context['form'].errors)

        upload = open("%s/image.jpg" % settings.TESTFILES_DIR, "r")

        post_data = dict(name="Blue Pattern", image_type="P", image=upload, org=self.uganda.pk)

        response = self.client.post(create_url, post_data, follow=True, SERVER_NAME='uganda.ureport.io')
        self.assertTrue('form' not in response.context)
        blue_bg = Image.objects.get(name="Blue Pattern")
        self.assertEquals(blue_bg.org, self.uganda)

        response = self.client.get(list_url, SERVER_NAME='uganda.ureport.io')
        self.assertEquals(len(response.context['object_list']), Image.objects.count())
        self.assertTrue(isinstance(response.context['pattern_bg'], Image))

        response = self.client.get(nigeria_bg_update_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEquals(response.request['PATH_INFO'], nigeria_bg_update_url)
        self.assertEquals(len(response.context['form'].fields), 6)

        self.clear_uploads()
