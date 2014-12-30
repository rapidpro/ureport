from django.db import models
import feedparser

__author__ = 'awesome'


class Source(models.Model):
    source = models.URLField()
    title = models.CharField(max_length=100)

    def __unicode__(self):
        return self.title

    def get_entries(self):
        feed = feedparser.parse(self.source)
        return feed['entries']

    def get_return_page(self):
        return '/'.join(self.source.split('/')[:3])

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        feed = feedparser.parse(self.source)
        self.title = feed['feed']['title']
        super(Source, self).save()