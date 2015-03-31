from django.conf import settings
from django.core.cache import cache
import feedparser

from dash.orgs.models import Org
from django.db import models
from django.utils.translation import ugettext_lazy as _

from smartmin.models import SmartModel

RSS_JOBS_FEED_CACHE_TIME = getattr(settings, 'RSS_JOBS_FEED_CACHE_TIME', 60 * 60 * 24)
RSS_JOBS_KEY = 'jobsource:%d:%d'

class JobSource(SmartModel):
    TWITTER = 'T'
    FACEBOOK = 'F'
    RSS = 'R'
    SOURCE_TYPES = ((TWITTER, 'Twitter'), (FACEBOOK, 'Facebook'), (RSS, 'RSS'))

    title = models.CharField(max_length=100, help_text=_("The title or name to reference this Job source."))
    source_type = models.CharField(max_length=1, choices=SOURCE_TYPES,
                                   help_text=_("Choose the type for the Job source. Twitter, Facebook or RSS feed"))
    source_url = models.URLField(help_text=_("The full URL to navigate to this Job source."))
    widget_id = models.CharField(max_length=50, blank=True, null=True,
                                 help_text=_("For Twitter, a widget Id is required to embed tweets on the website. "
                                             "Read carefully the instructions above on how to get the right widget Id"))
    is_featured = models.BooleanField(default=False,
                                      help_text=_("Featured job sources are shown first on the jobs page."))
    org = models.ForeignKey(Org,
                            help_text=_("The organization this job source is for"))

    def __unicode__(self):
        return self.title

    def get_feed(self):
        if self.source_type != JobSource.RSS:
            return None

        key = RSS_JOBS_KEY % (self.org.id, self.id)

        cache_value = cache.get(key)

        if cache_value is not None:
            return cache_value

        feed = feedparser.parse(self.source_url)
        cache.set(key, feed, RSS_JOBS_FEED_CACHE_TIME)

        return feed

    def get_entries(self):
        entries = []
        try:
            feed = self.get_feed()
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
            feed = self.get_feed()
            self.title = feed['feed']['title']
        super(JobSource, self).save()