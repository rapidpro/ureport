from django.db import models
import feedparser

__author__ = 'awesome'


class Source(models.Model):
    TWITTER = 't'
    FACEBOOK = 'f'
    RSS = 'r'
    SOURCE_TYPES = ((TWITTER, 'twitter'), (FACEBOOK, 'facebook'), (RSS, 'rss'))

    source = models.URLField()
    title = models.CharField(max_length=100, blank=True)
    widget_id = models.CharField(max_length=50, blank=True, null=True)
    source_type = models.CharField(max_length=1, choices=SOURCE_TYPES)
    is_featured = models.BooleanField(default=False)

    def __unicode__(self):
        return self.title or self.get_username()

    def get_entries(self):
        try:
            feed = feedparser.parse(self.source)
            return feed['entries']
        except Exception as e:
            #log e somewhere
            return []

    def get_return_page(self):
        if self.source_type in [Source.FACEBOOK, Source.TWITTER]:
            return self.source
        return '/'.join(self.source.split('/')[:3])

    def get_username(self):
        if self.source_type in [Source.FACEBOOK, Source.TWITTER]:
            return self.source.split('/')[3]
        return None

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.is_featured:
            Source.objects.filter(is_featured=True).update(is_featured=False)
            self.is_featured = True
        if self.source_type == Source.RSS and not self.title:
            feed = feedparser.parse(self.source)
            self.title = feed['feed']['title']
        super(Source, self).save()