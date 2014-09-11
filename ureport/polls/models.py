from django.db import models
from django.utils import cache
from smartmin.models import SmartModel
from django.utils.translation import ugettext_lazy as _
from django.core.cache import cache
from dash.orgs.models import Org
from dash.api import API
from ureport.categories.models import Category

class PollCategory(SmartModel):
    """
    This is a dead class but here so we can perform our migration.
    """
    name = models.CharField(max_length=64,
                            help_text="The name of this poll category")
    org = models.ForeignKey(Org,
                            help_text="The organization this category applies to")

    def __unicode__(self):
        return self.name

    class Meta:
        unique_together = ('name', 'org')
        verbose_name_plural = _("Poll Categories")

class Poll(SmartModel):
    """
    A poll represents a single Flow that has been brought in for
    display and sharing in the UReport platform.
    """
    flow_id = models.IntegerField(help_text=_("The Flow this Poll is based on"))
    title = models.CharField(max_length=255,
                             help_text=_("The title for this Poll"))

    category = models.ForeignKey(Category, related_name="polls",
                                 help_text=_("The category this Poll belongs to"))

    image = models.ImageField(upload_to='polls', null=True, blank=True,
                              help_text=_("An image that should be displayed with this poll on the homepage"))
    is_featured = models.BooleanField(default=False,
                                      help_text=_("Whether this poll should be featured on the homepage"))
    org = models.ForeignKey(Org,
                            help_text="The organization this poll is part of")

    @classmethod
    def get_featured_polls_for_homepage(cls, org, latest_poll):
        featured_polls = []
        polls = Poll.objects.filter(org=org, is_active=True).exclude(pk=latest_poll.pk).order_by('-created_on')

        for poll in polls:
            first_question = poll.get_first_question()
            if first_question:
                if not first_question.is_open_ended():
                    featured_polls.append(poll)

        return featured_polls

    def get_flow(self):
        """
        Returns the underlying flow for this poll
        """
        api = API(self.org)
        return api.get_flow(self.flow_id)

    def best_and_worst(self):
        b_and_w = []

        # get our first question
        question = self.questions.order_by('ruleset_id').first()
        if question:
            # do we already have a cached set
            b_and_w = cache.get('b_and_d:%d' % question.ruleset_id, [])

            if not b_and_w:
                api = API(self.org)
                boundary_results = api.get_ruleset_results(question.ruleset_id, segment=dict(location='State'))
                boundary_responses = dict()
                for boundary in boundary_results:
                    total = boundary['set'] + boundary['unset']
                    responded = boundary['set']
                    boundary_responses[boundary['label']] = dict(responded=responded, total=total)

                for boundary in sorted(boundary_responses, key=lambda x: boundary_responses[x]['responded'], reverse=True)[:3]:
                    responded = boundary_responses[boundary]
                    percent = int(round((100 * responded['responded'])) / responded['total']) if responded['total'] > 0 else 0
                    b_and_w.append(dict(boundary=boundary, responded=responded['responded'], total=responded['total'], type='best', percent=percent))

                for boundary in sorted(boundary_responses, key=lambda x: boundary_responses[x]['responded'], reverse=True)[-2:]:
                    responded = boundary_responses[boundary]
                    percent = int(round((100 * responded['responded'])) / responded['total']) if responded['total'] > 0 else 0
                    b_and_w.append(dict(boundary=boundary, responded=responded['responded'], total=responded['total'], type='worst', percent=percent))

                cache.set('b_and_w:%d' % question.ruleset_id, b_and_w, 300)

        return b_and_w

    def response_percentage(self):
        """
        The response rate for this flow
        """
        flow = self.get_flow()
        if flow['completed_runs']:
            return int(round((flow['completed_runs'] * 100.0) / flow['runs']))
        else:
            return '--'


    def get_trending_words(self):
        key = 'trending_words:%d' % self.pk

        trending_words = cache.get(key)

        if not trending_words:
            words = dict()

            questions = self.questions.all()
            for question in questions:
                for category in question.get_words():
                    key = category['label'].lower()

                    if not key in words:
                        words[key] = int(category['count'])

                    else:
                        words[key] += int(category['count'])

            tuples = [(k, v) for k, v in words.iteritems()]
            tuples.sort(key=lambda t: t[1])

            trending_words =  [k for k, v in tuples]

            cache.set(key, trending_words, 3600)

        return trending_words

    def get_featured_responses(self):
        return self.featured_responses.filter(is_active=True).order_by('-created_on')

    def get_first_question(self):
        questions = self.questions.filter(is_active=True)

        for question in questions:
            if not question.is_open_ended():
                return question

    def runs(self):
        flow = self.get_flow()
        return flow['runs']

    def completed_runs(self):
        flow = self.get_flow()
        return flow['completed_runs']

    def get_category_image(self):
        if self.category:
            return self.category.get_random_image()
        elif self.image:
            return self.image

    def get_image(self):
        if self.image:
            return self.image
        elif self.category:
            return self.category.get_random_image()

    def __unicode__(self):
        return self.title

class FeaturedResponse(SmartModel):
    """
    A highlighted response for a poll and location.
    """
    poll = models.ForeignKey(Poll, related_name="featured_responses",
                             help_text=_("The poll for this response"))

    location = models.CharField(max_length=255,
                                help_text=_("The location for this response"))

    reporter = models.CharField(max_length=255, null=True, blank=True,
                                help_text=_("The name of the sender of the message"))

    message = models.CharField(max_length=255,
                               help_text=_("The featured response message"))

    def __unicode__(self):
        return "%s - %s - %s" % (self.poll, self.location, self.message)


class PollQuestion(SmartModel):
    """
    Represents a single question that was asked in a poll, these questions tie 1-1 to
    the RuleSets in a flow.
    """
    poll = models.ForeignKey(Poll, related_name='questions',
                             help_text=("The poll this question is part of"))
    title = models.CharField(max_length=255,
                             help_text=_("The title of this question"))
    ruleset_id = models.IntegerField(help_text=("The RuleSet this question is based on"))

    def get_results(self, segment=None):
        api = API(self.poll.org)
        return api.get_ruleset_results(self.ruleset_id, segment=segment)

    def is_open_ended(self):
        return self.get_results()[0].get('open_ended', False)

    def get_responded(self):
        return self.get_results()[0]['set']

    def get_polled(self):
        return self.get_results()[0]['set'] + self.get_results()[0]['unset']

    def get_words(self):
        return self.get_results()[0]['categories']

    def __unicode__(self):
        return self.title
