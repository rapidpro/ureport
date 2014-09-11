from dash.api import API
from django.db import models
import json
from smartmin.models import SmartModel
from django.contrib.auth.models import User, Group
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from django.utils import timezone
from dash.dash_email import send_dash_email

import random

class Org(SmartModel):
    name = models.CharField(verbose_name=_("Name"), max_length=128,
                            help_text=_("The name of this organization"))

    logo = models.ImageField(upload_to='logos', null=True, blank=True,
                             help_text=_("The logo that should be used for this organization"))

    administrators = models.ManyToManyField(User, verbose_name=_("Administrators"), related_name="org_admins",
                                            help_text=_("The administrators in your organization"))

    viewers = models.ManyToManyField(User, verbose_name=_("Viewers"), related_name="org_viewers",
                                     help_text=_("The viewers in your organization"))

    editors = models.ManyToManyField(User, verbose_name=_("Editors"), related_name="org_editors",
                                     help_text=_("The editors in your organization"))

    language = models.CharField(verbose_name=_("Language"), max_length=64, null=True, blank=True,
                                choices=settings.LANGUAGES,
                                help_text=_("The main language used by this organization"))

    subdomain = models.SlugField(verbose_name=_("Subdomain"), max_length=255, unique=True, error_messages=dict(unique=_("This subdomain is not available")),
                                 help_text=_("The subdomain for this UReport instance"))

    api_token = models.CharField(max_length=128, null=True, blank=True,
                                 help_text=_("The API token for the RapidPro account this dashboard is tied to"))

    config = models.TextField(null=True, blank=True,
                              help_text=_("JSON blob used to store configuration information associated with this organization"))

    def get_config(self, name):
        config = getattr(self, '_config', None)

        if config is None:
            if not self.config:
                return None

            config = json.loads(self.config)
            self._config = config

        return config.get(name, None)

    def set_config(self, name, value):
        if not self.config:
            config = dict()
        else:
            config = json.loads(self.config)

        config[name] = value
        self.config = json.dumps(config)
        self._config = config
        self.save()

    def get_org_admins(self):
        return self.administrators.all()

    def get_org_editors(self):
        return self.editors.all()

    def get_org_viewers(self):
        return self.viewers.all()

    def get_org_users(self):
        org_users = self.get_org_admins() | self.get_org_editors() | self.get_org_viewers()
        return org_users.distinct()

    def get_user_org_group(self, user):
        if user in self.get_org_admins():
            user._org_group = Group.objects.get(name="Administrators")
        elif user in self.get_org_editors():
            user._org_group = Group.objects.get(name="Editors")
        elif user in self.get_org_viewers():
            user._org_group = Group.objects.get(name="Viewers")
        else:
            user._org_group = None

        return getattr(user, '_org_group', None)

    def get_user(self):
        user = self.administrators.filter(is_active=True).first()
        if user:
            org_user = user
            org_user.set_org(self)
            return org_user
        else:
            return None

    def get_api(self):
        return API(self)

    def get_contact_field_results(self, contact_field, segment):
        return self.get_api().get_contact_field_results(contact_field, segment)

    def get_most_active_regions(self):
        regions = self.get_contact_field_results(self.get_config('gender_label'), dict(location="State"))
        active_regions = dict()

        for region in regions:
            active_regions[region['label']] = region['set'] + region['unset']

        tuples = [(k, v) for k, v in active_regions.iteritems()]
        tuples.sort(key=lambda t: t[1])

        return [k for k, v in tuples]


    @classmethod
    def create_user(cls, email, password):
        user = User.objects.create_user(username=email, email=email, password=password)
        return user

    @classmethod
    def get_org(cls, user):
        if not user:
            return None

        if not hasattr(user, '_org'):
            org = Org.objects.filter(administrators=user, is_active=True).first()
            if org:
                user._org = org

        return getattr(user, '_org', None)

    def __unicode__(self):
        return self.name

def get_user_orgs(user):
    if user.is_superuser:
        return Org.objects.all()
    user_orgs = user.org_admins.all() | user.org_editors.all() | user.org_viewers.all()
    return user_orgs.distinct()

# monkey patch user, add a get_org() to it
def get_org(obj):
    return getattr(obj, '_org', None)

User.get_org = get_org
User.get_user_orgs = get_user_orgs

def set_org(obj, org):
    obj._org = org

User.set_org = set_org

def get_org_group(obj):
    org_group = None
    org = obj.get_org()
    if org:
        org_group = org.get_user_org_group(obj)
    return org_group

User.get_org_group = get_org_group

USER_GROUPS = (('A', _("Administrator")),
               ('E', _("Editor")),
               ('V', _("Viewer")))


class Invitation(SmartModel):
    org = models.ForeignKey(Org, verbose_name=_("Org"), related_name="invitations",
                            help_text=_("The organization to which the account is invited to view"))

    email = models.EmailField(verbose_name=_("Email"), help_text=_("The email to which we send the invitation of the viewer"))

    secret = models.CharField(verbose_name=_("Secret"), max_length=64, unique=True,
                              help_text=_("a unique code associated with this invitation"))

    user_group = models.CharField(max_length=1, choices=USER_GROUPS, default='V', verbose_name=_("User Role"))

    def save(self, *args, **kwargs):
        if not self.secret:
            secret = Invitation.generate_random_string(64)

            while Invitation.objects.filter(secret=secret):
                secret = Invitation.generate_random_string(64)

            self.secret = secret

        return super(Invitation, self).save(*args, **kwargs)

    @classmethod
    def generate_random_string(cls, length):
        """
        Generatesa a [length] characters alpha numeric secret
        """
        letters="23456789ABCDEFGHJKLMNPQRSTUVWXYZ" # avoid things that could be mistaken ex: 'I' and '1'
        return ''.join([random.choice(letters) for _ in range(length)])

    def send_invitation(self):
        from .tasks import send_invitation_email_task
        send_invitation_email_task(self.id)


    def send_email(self):
        # no=op if we do not know the email
        if not self.email:
            return


        subject = _("%s Invitation") % self.org.name
        template = "orgs/email/invitation_email"
        to_email = self.email

        context = dict(org=self.org, now=timezone.now(), invitation=self)
        context['subject'] = subject

        send_dash_email(to_email, subject, template, context)


BACKGROUND_TYPES = (('B', _("Banner")),
                   ('P', _("Pattern")))

class OrgBackground(SmartModel):
    org = models.ForeignKey(Org, verbose_name="Org", related_name="backgrounds",
                            help_text="The organization in which the image will be used")


    name = models.CharField(verbose_name=_("Name"), max_length=128,
                            help_text=_("The name to describe this background"))

    background_type = models.CharField(max_length=1, choices=BACKGROUND_TYPES, default='P', verbose_name=_("Background type"))

    image = models.ImageField(upload_to='org_bgs', help_text=_("The image file"))
