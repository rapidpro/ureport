from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import reverse

from ureport.policies.models import Policy
from ureport.tests import UreportTest


class PolicyTest(UreportTest):
    def setUp(self):
        super(PolicyTest, self).setUp()

        self.nigeria.language = "en"

    def test_create_policy(self):
        create_url = reverse("policies.policy_create")
        response = self.client.get(create_url, SERVER_NAME="nigeria.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.superuser)

        response = self.client.get(create_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(len(response.context["form"].fields), 5)
        self.assertTrue("org" not in response.context["form"].fields)
        self.assertTrue("body" in response.context["form"].fields)
        self.assertTrue("summary" in response.context["form"].fields)
        self.assertTrue("policy_type" in response.context["form"].fields)
        self.assertTrue("language" in response.context["form"].fields)
        self.assertEqual(
            list(response.context["form"].fields["policy_type"].choices),
            [("", "---------"), ("privacy", "Privacy Policy")],
        )
        self.assertEqual(Policy.objects.count(), 0)

        response = self.client.post(create_url, dict(), SERVER_NAME="nigeria.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(response.context["form"].errors.keys()), 4)
        self.assertTrue("body" in response.context["form"].errors.keys())
        self.assertTrue("summary" in response.context["form"].errors.keys())
        self.assertTrue("policy_type" in response.context["form"].errors.keys())
        self.assertTrue("language" in response.context["form"].errors.keys())

        post_data = dict(
            body="First Privacy Policy", summary="U-Report Policy", policy_type="privacy", language=self.nigeria.language
        )

        response = self.client.post(create_url, post_data, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(Policy.objects.count(), 1)
        policy = Policy.objects.get()

        self.assertEqual(policy.body, "First Privacy Policy")
        self.assertEqual(policy.summary, "U-Report Policy")
        self.assertEqual(policy.policy_type, "privacy")
        self.assertEqual(policy.language, self.nigeria.language)

        self.login(self.superuser)
