from __future__ import unicode_literals
import json
from datetime import datetime
from django.db import models
from django.utils.text import slugify
from smartmin.models import SmartModel
from django.utils.translation import ugettext_lazy as _
from django.core.cache import cache
from dash.orgs.models import Org
from dash.categories.models import Category, CategoryImage
from dash.utils import temba_client_flow_results_serializer, datetime_to_ms
from django.conf import settings


# cache whether a question is open ended for a month
OPEN_ENDED_CACHE_TIME = getattr(settings, 'OPEN_ENDED_CACHE_TIME', 60 * 60 * 24 * 30)

# cache our featured polls for a month (this will be invalidated by questions changing)
BRICK_POLLS_CACHE_TIME = getattr(settings, 'BRICK_POLLS_CACHE_TIME', 60 * 60 * 30)

POLL_RESULTS_CACHE_TIME = getattr(settings, 'POLL_RESULTS_CACHE_TIME', 60 * 60 * 24)

# big cache time for task cached data, we run more often the task to update the data
UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME = getattr(settings, 'UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME', 60 * 60 * 24 * 15)

# time to cache data we fetch directly from the api not with a task
UREPORT_RUN_FETCHED_DATA_CACHE_TIME = getattr(settings, 'UREPORT_RUN_FETCHED_DATA_CACHE_TIME', 60 * 10)

CACHE_POLL_RESULTS_KEY = 'org:%d:poll:%d:results:%d'

CACHE_ORG_FLOWS_KEY = "org:%d:flows"

CACHE_ORG_REPORTER_GROUP_KEY = "org:%d:reporters:%s"

CACHE_ORG_FIELD_DATA_KEY = "org:%d:field:%s:segment:%s"

CACHE_ORG_GENDER_DATA_KEY = "org:%d:gender:%s"

CACHE_ORG_AGE_DATA_KEY = "org:%d:age:%s"

CACHE_ORG_REGISTRATION_DATA_KEY = "org:%d:registration:%s"

CACHE_ORG_OCCUPATION_DATA_KEY = "org:%d:occupation:%s"


class PollCategory(SmartModel):
    """
    This is a dead class but here so we can perform our migration.
    """
    name = models.CharField(max_length=64,
                            help_text=_("The name of this poll category"))
    org = models.ForeignKey(Org,
                            help_text=_("The organization this category applies to"))

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
    flow_uuid = models.CharField(max_length=36, help_text=_("The Flow this Poll is based on"))
    poll_date = models.DateTimeField()
    title = models.CharField(max_length=255,
                             help_text=_("The title for this Poll"))
    category = models.ForeignKey(Category, related_name="polls",
                                 help_text=_("The category this Poll belongs to"))
    is_featured = models.BooleanField(default=False,
                                      help_text=_("Whether this poll should be featured on the homepage"))
    category_image = models.ForeignKey(CategoryImage, null=True,
                                       help_text=_("The splash category image to display for the poll (optional)"))
    org = models.ForeignKey(Org, related_name="polls",
                            help_text=_("The organization this poll is part of"))

    def fetch_poll_results(self):
        for question in self.questions.all():
            question.fetch_results()
            question.fetch_results(dict(location='State'))

    @classmethod
    def fetch_poll_results_task(cls, poll):
        from ureport.polls.tasks import fetch_poll
        fetch_poll.delay(poll.pk)

    @classmethod
    def get_main_poll(cls, org):
        poll_with_questions = PollQuestion.objects.filter(is_active=True, poll__org=org).values_list('poll', flat=True)

        polls = Poll.objects.filter(org=org, is_active=True, category__is_active=True, pk__in=poll_with_questions).order_by('-created_on')

        main_poll = polls.filter(is_featured=True).first()

        if not main_poll:
            main_poll = polls.first()

        return main_poll

    @classmethod
    def get_brick_polls(cls, org):
        cache_key = 'brick_polls:%d' % org.id
        brick_polls = cache.get(cache_key, None)

        if brick_polls is None:
            poll_with_questions = PollQuestion.objects.filter(is_active=True, poll__org=org).values_list('poll', flat=True)

            main_poll = Poll.get_main_poll(org)

            polls = Poll.objects.filter(org=org, is_active=True, category__is_active=True, pk__in=poll_with_questions).order_by('-is_featured', '-created_on')
            if main_poll:
                polls = polls.exclude(pk=main_poll.pk)

            brick_polls = []

            for poll in polls:
                if poll.get_first_question():
                    brick_polls.append(poll)
            cache.set(cache_key, brick_polls, BRICK_POLLS_CACHE_TIME)

        return brick_polls

    @classmethod
    def clear_brick_polls_cache(self, org):
        cache_key = 'brick_polls:%d' % org.id
        cache.delete(cache_key)

    @classmethod
    def get_other_polls(cls, org):
        main_poll = Poll.get_main_poll(org)
        brick_polls = Poll.get_brick_polls(org)[:5]

        exclude_polls = [poll.pk for poll in brick_polls]
        if main_poll:
            exclude_polls.append(main_poll.pk)

        other_polls = Poll.objects.filter(org=org, is_active=True,
                                          category__is_active=True).exclude(pk__in=exclude_polls).order_by('-created_on')

        return other_polls

    def get_flow(self):
        """
        Returns the underlying flow for this poll
        """
        flows_dict = self.org.get_flows()
        return flows_dict.get(self.flow_uuid, None)

    def best_and_worst(self):
        b_and_w = []

        # get our first question
        question = self.questions.order_by('pk').first()
        if question:
            # do we already have a cached set
            b_and_w = cache.get('b_and_d:%s' % question.ruleset_uuid, [])

            if not b_and_w:
                boundary_results = question.get_results(segment=dict(location='State'))
                if not boundary_results:
                    return []

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

                # no actual results by region yet
                if b_and_w and b_and_w[0]['responded'] == 0:
                    b_and_w = []

                cache.set('b_and_w:%s' % question.ruleset_uuid, b_and_w, 900)

        return b_and_w

    def response_percentage(self):
        """
        The response rate for this flow
        """
        top_question = self.get_questions().first()
        if top_question:
            return top_question.get_response_percentage()

        return '---'

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
        questions = self.get_questions()

        for question in questions:
            if not question.is_open_ended():
                return question

    def get_questions(self):
        return self.questions.filter(is_active=True).order_by('pk')

    def get_images(self):
        return self.images.filter(is_active=True).order_by('pk')

    def runs(self):
        top_question = self.get_questions().first()
        if top_question:
            return top_question.get_polled()
        return "----"

    def responded_runs(self):
        top_question = self.get_questions().first()
        if top_question:
            return top_question.get_responded()
        return "---"

    def get_featured_images(self):
        return self.images.filter(is_active=True).exclude(image='').order_by('-created_on')

    def get_category_image(self):
        if self.category_image:
            return self.category_image.image
        elif self.category.is_active:
            return self.category.get_first_image()

    def __unicode__(self):
        return self.title

class PollImage(SmartModel):
    name = models.CharField(max_length=64,
                            help_text=_("The name to describe this image"))

    poll = models.ForeignKey(Poll, related_name="images",
                             help_text=_("The poll to associate to"))

    image = models.ImageField(upload_to='polls',
                              help_text=_("The image file to use"))

    def __unicode__(self):
        return "%s - %s" % (self.poll, self.name)

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
                             help_text=_("The poll this question is part of"))
    title = models.CharField(max_length=255,
                             help_text=_("The title of this question"))
    ruleset_uuid = models.CharField(max_length=36, help_text=_("The RuleSet this question is based on"))

    def fetch_results(self, segment=None):
        from raven.contrib.django.raven_compat.models import client

        cache_time = UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME
        if segment and segment.get('location', "") == "District":
            cache_time = UREPORT_RUN_FETCHED_DATA_CACHE_TIME

        try:
            key = CACHE_POLL_RESULTS_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
            if segment:
                segment = self.poll.org.substitute_segment(segment)
                key += ":" + slugify(unicode(segment))

            this_time = datetime.now()
            temba_client = self.poll.org.get_temba_client()
            client_results = temba_client.get_results(self.ruleset_uuid, segment=segment)
            results = temba_client_flow_results_serializer(client_results)

            cache.set(key, {'time': datetime_to_ms(this_time), 'results': results}, cache_time)

            # delete the open ended cache
            cache.delete('open_ended:%d' % self.id)

        except:  # pragma: no cover
            client.captureException()
            import traceback
            traceback.print_exc()

    def get_results(self, segment=None):

        key = CACHE_POLL_RESULTS_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
        if segment:
            substituted_segment = self.poll.org.substitute_segment(segment)
            key += ":" + slugify(unicode(json.dumps(substituted_segment)))

        cached_value = cache.get(key, None)
        if cached_value:
            return cached_value['results']

        if segment and segment.get('location', "") in ('District', 'Ward'):
            self.fetch_results(segment=segment)

            cached_value = cache.get(key, None)
            if cached_value:
                return cached_value['results']

    def get_total_summary_data(self):
        cached_results = self.get_results()
        if cached_results:
            return cached_results[0]
        return dict()

    def is_open_ended(self):
        cache_key = 'open_ended:%d' % self.id
        open_ended = cache.get(cache_key, None)

        if open_ended is None:
            open_ended = self.get_total_summary_data().get('open_ended', False)
            cache.set(cache_key, open_ended, OPEN_ENDED_CACHE_TIME)

        return open_ended

    def get_responded(self):
        return self.get_total_summary_data().get('set', 0)

    def get_polled(self):
        return self.get_total_summary_data().get('set', 0) + self.get_total_summary_data().get('unset', 0)

    def get_response_percentage(self):
        polled = self.get_polled()
        responded = self.get_responded()
        if polled and responded:
            percentage = int(round((float(responded) * 100.0) / float(polled)))
            return "%s" % str(percentage) + "%"
        return "___"

    def get_words(self):
        return self.get_total_summary_data().get('categories', [])

    def __unicode__(self):
        return self.title
