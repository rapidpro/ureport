from django.urls import reverse

from ureport.countries.models import CountryAlias
from ureport.tests import UreportTest


class CountriesTest(UreportTest):
    def setUp(self):
        super(CountriesTest, self).setUp()

    def test_country_alias_get_or_create(self):
        self.assertFalse(CountryAlias.objects.all())

        alias1 = CountryAlias.get_or_create('RW', 'Awesome', self.admin)

        self.assertEqual(CountryAlias.objects.all().count(), 1)
        self.assertEqual(CountryAlias.objects.all().first(), alias1)

        alias2 = CountryAlias.get_or_create('RW', 'Awesome', self.admin)

        self.assertEqual(CountryAlias.objects.all().count(), 1)
        self.assertEqual(CountryAlias.objects.all().first(), alias1)
        self.assertEqual(alias1, alias2)

        CountryAlias.get_or_create('RW', '1kHills', self.admin)
        self.assertEqual(CountryAlias.objects.all().count(), 2)

    def test_list(self):
        list_url = reverse('countries.countryalias_list')

        response = self.client.get(list_url, SERVER_NAME='nigeria.ureport.io')
        self.assertLoginRedirect(response)

        self.login(self.superuser)

        response = self.client.get(list_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['object_list']), 0)

        alias1 = CountryAlias.get_or_create('RW', 'Awesome', self.admin)

        response = self.client.get(list_url, SERVER_NAME='nigeria.ureport.io')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['object_list']), 1)
        self.assertContains(response, "Rwanda (RW)")
        self.assertTrue(alias1 in response.context['object_list'])
