import feedparser

from dash.orgs.models import Org
from django.db import models
from django.utils.translation import ugettext_lazy as _

from smartmin.models import SmartModel

class JobSource(SmartModel):
    TWITTER = 'T'
    FACEBOOK = 'F'
    RSS = 'R'
    SOURCE_TYPES = ((TWITTER, 'Twitter'), (FACEBOOK, 'Facebook'), (RSS, 'RSS'))

    title = models.CharField(max_length=100)
    source_type = models.CharField(max_length=1, choices=SOURCE_TYPES)
    source_url = models.URLField()
    widget_id = models.CharField(max_length=50, blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    org = models.ForeignKey(Org,
                            help_text=_("The organization this job source is for"))

    def __unicode__(self):
        return self.title

    def get_entries(self):
        entries = []
        try:
            feed = feedparser.parse(self.source_url)
            entries = feed['entries']
        except Exception as e:
            #log e somewhere
            pass

        return entries

    def get_return_page(self):
        if self.source_type in [JobSource.FACEBOOK, JobSource.TWITTER]:
            return self.source_url
        return '/'.join(self.source_url.split('/')[:3])

    def get_username(self):
        if self.source_type in [JobSource.FACEBOOK, JobSource.TWITTER]:
            return self.source_url.split('/')[3]
        return None

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.source_type == JobSource.RSS and not self.title:
            feed = feedparser.parse(self.source_url)
            self.title = feed['feed']['title']
        super(JobSource, self).save()