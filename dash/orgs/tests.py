from django.core import mail
from django.contrib.auth.models import User

from smartmin.tests import *

from dash.tests import DashTest
from dash.orgs.models import Org, Invitation


class OrgTest(DashTest):

    def setUp(self):
        super(OrgTest, self).setUp()

        self.org = self.create_org("uganda", self.admin)


    def test_org_create(self):
        create_url = reverse("orgs.org_create")

        response = self.client.get(create_url)
        self.assertLoginRedirect(response)

        self.login(self.superuser)
        response = self.client.get(create_url)
        self.assertEquals(200, response.status_code)
        self.assertFalse(Org.objects.filter(name="kLab"))
        self.assertEquals(User.objects.all().count(), 4)

        user_alice = User.objects.create_user("alicefox")

        data = dict(name="kLab", subdomain="klab", administrators=[user_alice.pk])
        response = self.client.post(create_url, data, follow=True)
        self.assertTrue('form' not in response.context)
        self.assertTrue(Org.objects.filter(name="kLab"))
        org = Org.objects.get(name="kLab")
        self.assertEquals(User.objects.all().count(), 5)
        self.assertTrue(org.administrators.filter(username="alicefox"))

 
    def test_manage_accounts(self):
        manage_accounts_url = reverse('orgs.org_manage_accounts')
        self.editor = self.create_user("Editor")
        self.user = self.create_user("User")
        
        self.org = self.create_org("uganda", self.admin)

        self.login(self.admin)
        self.admin.set_org(self.org)

        self.org.editors.add(self.editor)
        self.org.administrators.add(self.user)

        response = self.client.get(manage_accounts_url, SERVER_NAME="uganda.ureport.io")

        self.assertEquals(200, response.status_code)

        # we have 12 fields in the form including 9 checkboxes for the three users, an emails field a user group field and 'loc' field.
        self.assertEquals(12, len(response.context['form'].fields))
        self.assertTrue('emails' in response.context['form'].fields)
        self.assertTrue('user_group' in response.context['form'].fields)
        for user in [self.editor, self.user, self.admin]:
            self.assertTrue("administrators_%d" % user.pk in response.context['form'].fields)
            self.assertTrue("editors_%d" % user.pk in response.context['form'].fields)
            self.assertTrue("viewers_%d" % user.pk in response.context['form'].fields)

        self.assertFalse(response.context['form'].fields['emails'].initial)
        self.assertEquals('V', response.context['form'].fields['user_group'].initial)

        post_data = dict()

        # keep all the admins
        post_data['administrators_%d' % self.admin.pk] = 'on'
        post_data['administrators_%d' % self.user.pk] = 'on'
        post_data['administrators_%d' % self.editor.pk] = 'on'

        # add self.editor to editors
        post_data['editors_%d' % self.editor.pk] = 'on'
        post_data['user_group'] = 'E'

        response = self.client.post(manage_accounts_url, post_data, SERVER_NAME="uganda.ureport.io")
        self.assertEquals(302, response.status_code)

        org = Org.objects.get(pk=self.org.pk)
        self.assertEquals(org.administrators.all().count(), 3)
        self.assertFalse(org.viewers.all())
        self.assertTrue(org.editors.all())
        self.assertEquals(org.editors.all()[0].pk, self.editor.pk)

        # add to post_data an email to invite as admin
        post_data['emails'] = "norkans7gmail.com"
        post_data['user_group'] = 'A'
        response = self.client.post(manage_accounts_url, post_data, SERVER_NAME="uganda.ureport.io")
        self.assertTrue('emails' in response.context['form'].errors)
        self.assertEquals("One of the emails you entered is invalid.", response.context['form'].errors['emails'][0])

        # now post with right email
        post_data['emails'] = "norkans7@gmail.com"
        post_data['user_group'] = 'A'
        response = self.client.post(manage_accounts_url, post_data, SERVER_NAME="uganda.ureport.io")

        # an invitation is created and sent by email
        self.assertEquals(1, Invitation.objects.all().count())
        self.assertTrue(len(mail.outbox) == 1)

        invitation = Invitation.objects.get()

        self.assertEquals(invitation.org, self.org)
        self.assertEquals(invitation.email, "norkans7@gmail.com")
        self.assertEquals(invitation.user_group, "A")

        # pretend our invite was acted on
        Invitation.objects.all().update(is_active=False)

        # send another invitation, different group
        post_data['emails'] = "norkans7@gmail.com"
        post_data['user_group'] = 'E'
        self.client.post(manage_accounts_url, post_data, SERVER_NAME="uganda.ureport.io")

        # old invite should be updated
        new_invite = Invitation.objects.all().first()
        self.assertEquals(1, Invitation.objects.all().count())
        self.assertEquals(invitation.pk, new_invite.pk)
        self.assertEquals('E', new_invite.user_group)
        self.assertEquals(2, len(mail.outbox))
        self.assertTrue(new_invite.is_active)


        # post many emails to the form
        post_data['emails'] = "norbert@nyaruka.com,code@nyaruka.com"
        post_data['user_group'] = 'A'
        self.client.post(manage_accounts_url, post_data, SERVER_NAME="uganda.ureport.io")

        # now 2 new invitations are created and sent
        self.assertEquals(3, Invitation.objects.all().count())
        self.assertEquals(4, len(mail.outbox))

    def test_join(self):
        editor_invitation = Invitation.objects.create(org=self.org,
                                               user_group="E",
                                               email="norkans7@gmail.com",
                                               created_by=self.admin,
                                               modified_by=self.admin)

        self.org2 = self.create_org("kenya", self.admin)
        editor_join_url = reverse('orgs.org_join', args=[editor_invitation.secret])
        self.client.logout()

        # if no user is logged we redirect to the create_login page
        response = self.client.get(editor_join_url, SERVER_NAME="uganda.ureport.io")
        self.assertEquals(302, response.status_code)
        response = self.client.get(editor_join_url, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertEquals(response.request['PATH_INFO'], reverse('orgs.org_create_login', args=[editor_invitation.secret]))

        # a user is already logged in
        self.invited_editor = self.create_user("InvitedEditor")
        self.login(self.invited_editor)

        response = self.client.get(editor_join_url, SERVER_NAME="kenya.ureport.io")
        self.assertEquals(302, response.status_code)

        response = self.client.get(editor_join_url, follow=True, SERVER_NAME="kenya.ureport.io")
        self.assertEquals(200, response.status_code)
        self.assertEquals("uganda.ureport.io", response.request['SERVER_NAME'])
        self.assertEquals(response.wsgi_request.org, self.org)

        response = self.client.get(editor_join_url, SERVER_NAME="uganda.ureport.io")
        self.assertEquals(200, response.status_code)

        self.assertEquals(self.org.pk, response.context['org'].pk)
        # we have a form without field except one 'loc'
        self.assertEquals(1, len(response.context['form'].fields))

        post_data = dict()
        response = self.client.post(editor_join_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertEquals(200, response.status_code)

        self.assertTrue(self.invited_editor in self.org.editors.all())
        self.assertFalse(Invitation.objects.get(pk=editor_invitation.pk).is_active)

    def test_create_login(self):
        admin_invitation = Invitation.objects.create(org=self.org,
                                                     user_group="A",
                                                     email="norkans7@gmail.com",
                                                     created_by=self.admin,
                                                     modified_by=self.admin)

        self.org2 = self.create_org("kenya", self.admin)

        admin_create_login_url = reverse('orgs.org_create_login', args=[admin_invitation.secret])
        self.client.logout()

        response = self.client.get(admin_create_login_url, SERVER_NAME="kenya.ureport.io")
        self.assertEquals(302, response.status_code)

        response = self.client.get(admin_create_login_url, follow=True, SERVER_NAME="kenya.ureport.io")
        self.assertEquals(200, response.status_code)
        self.assertEquals("uganda.ureport.io", response.request['SERVER_NAME'])
        self.assertEquals(response.wsgi_request.org, self.org)

        response = self.client.get(admin_create_login_url, SERVER_NAME="uganda.ureport.io")
        self.assertEquals(200, response.status_code)

        self.assertEquals(self.org.pk, response.context['org'].pk)

        # we have a form with 4 fields and one hidden 'loc'
        self.assertEquals(5, len(response.context['form'].fields))
        self.assertTrue('first_name' in response.context['form'].fields)
        self.assertTrue('last_name' in response.context['form'].fields)
        self.assertTrue('email' in response.context['form'].fields)
        self.assertTrue('password' in response.context['form'].fields)

        post_data = dict()
        post_data['first_name'] = "Norbert"
        post_data['last_name'] = "Kwizera"
        post_data['email'] = "norkans7@gmail.com"
        post_data['password'] = "norbertkwizeranorbert"

        response = self.client.post(admin_create_login_url, post_data, follow=True, SERVER_NAME="uganda.ureport.io")
        self.assertEquals(200, response.status_code)

        new_invited_user = User.objects.get(email="norkans7@gmail.com")
        self.assertTrue(new_invited_user in self.org.administrators.all())
        self.assertFalse(Invitation.objects.get(pk=admin_invitation.pk).is_active)
