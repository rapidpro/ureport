from __future__ import absolute_import, division, print_function, unicode_literals

from django.urls import reverse

from ureport.policies.models import Policy
from ureport.tests import UreportTest


class PolicyTest(UreportTest):
    def setUp(self):
        super(PolicyTest, self).setUp()

        Policy.objects.create(
            policy_type=Policy.TYPE_PRIVACY,
            body="Privacy matters",
            summary="Summary",
            language="en",
            created_by=self.admin,
            modified_by=self.admin,
        )

        Policy.objects.create(
            policy_type=Policy.TYPE_TOS,
            body="These are the terms",
            summary="You need to accept these",
            language="en",
            created_by=self.admin,
            modified_by=self.admin,
        )

        Policy.objects.create(
            policy_type=Policy.TYPE_COOKIE,
            body="C is for Cookie",
            summary="That's good enough for me!",
            language="en",
            created_by=self.admin,
            modified_by=self.admin,
        )

    def test_policy_list(self):
        self.login(self.superuser)
        response = self.client.get(reverse("policies.policy_admin"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(3, response.context["active_policies"].count())

    def test_read_policy(self):
        self.login(self.superuser)
        response = self.client.get(reverse("policies.policy_read", args=["privacy"]), SERVER_NAME="nigeria.ureport.io")
        self.assertContains(response, "Privacy matters")

    def test_admin(self):
        self.login(self.superuser)
        post_data = dict(
            policy_type="privacy", body="My privacy policy update", summary="the summary"
        )
        self.client.post(reverse("policies.policy_create"), post_data, SERVER_NAME="nigeria.ureport.io")
        response = self.client.get(reverse("policies.policy_admin"), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(3, response.context["active_policies"].count())

    def test_policy(self):
        policy = Policy.objects.get(policy_type="privacy")
        self.assertEqual("<p>Privacy matters</p>", policy.get_rendered_body())
        self.assertEqual("<p>Summary</p>", policy.get_rendered_summary())
        self.assertEqual("English", policy.get_policy_language())

    def test_history(self):
        self.login(self.superuser)
        response = self.client.get(reverse("policies.policy_history", args=[1]), SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(1, response.context["object_list"].count())
        self.assertContains("Privacy", response)
