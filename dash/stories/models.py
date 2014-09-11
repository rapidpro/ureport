from django.db import models
from smartmin.models import SmartModel
from dash.orgs.models import Org
from django.utils.translation import ugettext_lazy as _
from ureport.categories.models import Category

class Story(SmartModel):
    title = models.CharField(max_length=255,
                             help_text=_("The title for this story"))

    featured = models.BooleanField(default=False,
                                   help_text=_("Whether this story is featured"))
    summary = models.TextField(null=True, blank=True, help_text=_("The summary for the story"))
    
    content = models.TextField(help_text=_("The body of text for the story"))

    
    image = models.ImageField(upload_to='stories', null=True, blank=True,
                              help_text=_("Any image that should be displayed with this story"))

    video_id = models.CharField(blank=True, null=True, max_length=255,
                                help_text=_("The id of the YouTube video that should be linked to this story"))

    tags = models.CharField(blank=True, null=True, max_length=255,
                            help_text=_("Any tags for this story, separated by spaces, can be used to do more advanced filtering, optional"))

    category = models.ForeignKey(Category, null=True, blank=True,
                                 help_text=_("The category for this story"))
    
    org = models.ForeignKey(Org, help_text=_("The organization this story belongs to"))



    def space_tags(self):
        """
        If we have tags set, then adds spaces before and after to allow for SQL querying for them.
        """
        if self.tags and self.tags.strip():
            self.tags = " " + self.tags.strip().lower() + " "

    def teaser(self, field, length):
        if not field:
            return ""
        words = field.split(" ")
        
        if len(words) < length:
            return field
        else:
            return " ".join(words[:length]) + " .."

    def long_teaser(self):
        if self.summary:
            return self.teaser(self.summary, 100)
        return self.teaser(self.content, 100)

    def short_teaser(self):
        if self.summary:
           return self.teaser(self.summary, 40)
        return self.teaser(self.content, 40)

    def get_category_image(self):
        if self.category and self.category.images.all():
            cat_image = self.category.images.order_by('?').first()
            return cat_image.image
        elif self.image:
            return self.image

    def get_image(self):
        if self.image:
            return self.image
        elif self.category and self.category.images.all():
            return self.get_category_image()

    class Meta:
        verbose_name_plural = "Stories"

