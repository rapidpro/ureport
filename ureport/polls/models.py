from __future__ import unicode_literals
import json
import time
from collections import defaultdict
from datetime import datetime

import pytz
from django.contrib.auth.models import User
from django.core.exceptions import MultipleObjectsReturned
from django.db import models, connection
from django.db.models import Sum, Count, F
from django.utils.text import slugify
from django.utils import timezone
from smartmin.models import SmartModel
from django.utils.translation import ugettext_lazy as _
from django.core.cache import cache
from dash.orgs.models import Org
from dash.categories.models import Category, CategoryImage
from dash.utils import temba_client_flow_results_serializer, datetime_to_ms
from django.conf import settings
from stop_words import safe_get_stop_words

from django_redis import get_redis_connection


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

    POLL_PULL_RESULTS_TASK_LOCK = 'poll-pull-results-task-lock:%s:%s'

    POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG = 'poll-results-pull-after-delete-flag:%s:%s'

    flow_uuid = models.CharField(max_length=36, help_text=_("The Flow this Poll is based on"))

    poll_date = models.DateTimeField(help_text=_("The date to display for this poll. "
                                                 "Make it empty to use flow created_on."))

    flow_archived = models.BooleanField(default=False,
                                        help_text=_("Whether the flow for this poll is archived on RapidPro"))

    base_language = models.CharField(max_length=4, default='base', help_text=_("The base language of the flow to use"))

    runs_count = models.IntegerField(default=0,
                                     help_text=_("The number of polled reporters on this poll"))

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

    @classmethod
    def pull_results(cls, poll_id):
        from ureport.backend import get_backend
        backend = get_backend()
        poll = Poll.objects.get(pk=poll_id)

        created, updated, ignored = backend.pull_results(poll, None, None)

        poll.rebuild_poll_results_counts()

        return created, updated, ignored

    def delete_poll_results_counter(self):
        from ureport.utils import chunk_list

        rulesets = self.questions.all().values_list('ruleset_uuid', flat=True)

        counters_ids = PollResultsCounter.objects.filter(org_id=self.org_id, ruleset__in=rulesets)
        counters_ids = counters_ids.values_list('pk', flat=True)

        counters_ids_count = len(counters_ids)

        for batch in chunk_list(counters_ids, 1000):
            PollResultsCounter.objects.filter(pk__in=batch).delete()

        print "Deleted %d poll results counters for poll #%d on org #%d" % (counters_ids_count, self.pk, self.org_id)

    def delete_poll_results(self):
        from ureport.utils import chunk_list

        results_ids = PollResult.objects.filter(org_id=self.org_id, flow=self.flow_uuid).values_list('pk', flat=True)

        results_ids_count = len(results_ids)

        for batch in chunk_list(results_ids, 1000):
            PollResult.objects.filter(pk__in=batch).delete()

        print "Deleted %d poll results for poll #%d on org #%d" % (results_ids_count, self.pk, self.org_id)

        cache.delete(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.org_id, self.pk))

    def pull_refresh_task(self):
        from ureport.utils import datetime_to_json_date
        from ureport.polls.tasks import pull_refresh

        now = timezone.now()
        cache.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.org_id, self.pk),
                  datetime_to_json_date(now.replace(tzinfo=pytz.utc)), None)

        pull_refresh.apply_async((self.pk,), queue='sync')

    def rebuild_poll_results_counts(self):
        from ureport.utils import chunk_list
        import time

        start = time.time()

        poll_id = self.pk
        org_id = self.org_id
        flow = self.flow_uuid

        r = get_redis_connection()

        key = PollResult.POLL_REBUILD_COUNTS_LOCK % (org_id, poll_id)

        if r.get(key):
            print "Already rebuilding counts for poll #%d on org #%d" % (poll_id, org_id)

        else:
            with r.lock(key):
                # Delete existing counters
                self.delete_poll_results_counter()

                poll_results_ids = PollResult.objects.filter(org_id=org_id, flow=flow).values_list('pk', flat=True)

                poll_results_ids_count = len(poll_results_ids)

                print "Results query time for pair %s, %s took %ds" % (org_id, flow, time.time() - start)

                processed_results = 0
                counters_dict = defaultdict(int)

                for batch in chunk_list(poll_results_ids, 1000):
                    poll_results = list(PollResult.objects.filter(pk__in=batch))

                    for result in poll_results:
                        gen_counters = result.generate_counters()
                        for key in gen_counters.keys():
                            counters_dict[(result.org_id, result.ruleset, key)] += gen_counters[key]

                        processed_results += 1

                print "Rebuild counts progress... build counters dict for pair %s, %s, processed %d of %d in %ds" % (org_id, flow, processed_results, poll_results_ids_count, time.time() - start)

                counters_to_insert = []
                for counter_tuple in counters_dict.keys():
                    org_id, ruleset, counter_type = counter_tuple
                    count = counters_dict[counter_tuple]
                    counters_to_insert.append(PollResultsCounter(org_id=org_id, ruleset=ruleset, type=counter_type,
                                                                 count=count))

                PollResultsCounter.objects.bulk_create(counters_to_insert)
                print "Finished Rebuilding the counters for poll #%d on org #%d in %ds, inserted %d counters objects for %s results" % (poll_id, org_id, time.time() - start, len(counters_to_insert), poll_results_ids_count)

    def fetch_poll_results(self):

        for question in self.questions.filter(is_active=True):
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

    def update_or_create_questions(self, user=None):
        if not user:
            user = User.objects.get(pk=-1)

        org = self.org
        temba_client = org.get_temba_client()
        flow_definition = temba_client.get_flow_definition(self.flow_uuid)

        base_language = flow_definition.base_language

        self.base_language = base_language
        self.save()

        for ruleset in flow_definition.rule_sets:
            label = ruleset['label']
            ruleset_uuid = ruleset['uuid']
            ruleset_type = ruleset['ruleset_type']

            question = PollQuestion.update_or_create(user, self, label, ruleset_uuid, ruleset_type)

            rapidpro_rules = []
            for rule in ruleset['rules']:
                category = rule['category'][base_language]
                rule_uuid = rule['uuid']
                rapidpro_rules.append(rule_uuid)

                PollResponseCategory.update_or_create(question, rule_uuid, category)

            # deactivate if corresponding rules are removed
            PollResponseCategory.objects.filter(
                question=question).exclude(rule_uuid__in=rapidpro_rules).update(is_active=False)

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
        The response rate for this poll
        """
        top_question = self.get_questions().first()
        if top_question and self.runs_count:
            responded = top_question.get_responded()
            polled = self.runs_count
            percentage = int(round((float(responded) * 100.0) / float(polled)))
            return "%s" % str(percentage) + "%"
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
        return self.questions.filter(is_active=True).order_by('-priority', 'pk')

    def get_images(self):
        return self.images.filter(is_active=True).order_by('pk')

    def runs(self):
        if self.runs_count:
            return self.runs_count
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

    POLL_QUESTION_RESULTS_CACHE_KEY = "org:%d:poll:%d:question_results:%d"
    POLL_QUESTION_RESULTS_CACHE_TIMEOUT = 60 * 5

    poll = models.ForeignKey(Poll, related_name='questions',
                             help_text=_("The poll this question is part of"))
    title = models.CharField(max_length=255,
                             help_text=_("The title of this question"))
    ruleset_uuid = models.CharField(max_length=36, help_text=_("The RuleSet this question is based on"))

    ruleset_type = models.CharField(max_length=32, default='wait_message')

    ruleset_label = models.CharField(max_length=255, null=True, blank=True,
                                     help_text=_("The label of the ruleset on RapidPro"))

    priority = models.IntegerField(default=0, null=True, blank=True,
                                   help_text=_("The priority number for this question on the poll"))


    @classmethod
    def update_or_create(cls, user, poll, ruleset_label, uuid, ruleset_type):
        existing = cls.objects.filter(ruleset_uuid=uuid, poll=poll)

        if existing:
            existing.update(ruleset_type=ruleset_type, ruleset_label=ruleset_label)
            question = existing.first()
        else:
            question = PollQuestion.objects.create(poll=poll, ruleset_uuid=uuid, title=ruleset_label,
                                                   ruleset_type=ruleset_type, ruleset_label=ruleset_label,
                                                   is_active=False, created_by=user, modified_by=user)
        return question

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

            cache.set(key, {'time': datetime_to_ms(this_time), 'results': results}, None)

            # delete the open ended cache
            cache.delete('open_ended:%d' % self.id)

        except:  # pragma: no cover
            client.captureException()
            import traceback
            traceback.print_exc()

    def get_results(self, segment=None):
        key = PollQuestion.POLL_QUESTION_RESULTS_CACHE_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
        if segment:
            substituted_segment = self.poll.org.substitute_segment(segment)
            key += ":" + slugify(unicode(json.dumps(substituted_segment)))

        cached_value = cache.get(key, None)
        if cached_value:
            return cached_value["results"]

        org = self.poll.org
        open_ended = self.is_open_ended()
        responded = self.get_responded()
        polled = self.get_polled()

        results = []

        if open_ended and not segment:
            cursor = connection.cursor()

            custom_sql = """
                      SELECT w.label, count(*) AS count FROM (SELECT regexp_split_to_table(LOWER(text), E'[^[:alnum:]_]') AS label FROM polls_pollresult WHERE polls_pollresult.org_id = %d AND polls_pollresult.flow = '%s' AND polls_pollresult.ruleset = '%s') w group by w.label order by count desc;
                      """ % (org.id, self.poll.flow_uuid, self.ruleset_uuid)

            cursor.execute(custom_sql)
            from ureport.utils import get_dict_from_cursor
            unclean_categories = get_dict_from_cursor(cursor)
            categories = []

            ureport_languages = getattr(settings, 'LANGUAGES', [('en', 'English')])

            org_languages = [lang[1].lower() for lang in ureport_languages if lang[0] == org.language]

            if 'english' not in org_languages:
                org_languages.append('english')

            ignore_words = []
            for lang in org_languages:
                ignore_words += safe_get_stop_words(lang)

            categories = []

            for category in unclean_categories:
                if len(category['label']) > 1 and category['label'] not in ignore_words and len(categories) < 100:
                    categories.append(dict(label=category['label'], count=int(category['count'])))

            # sort by count, then alphabetically
            categories = sorted(categories, key=lambda c: (-c['count'], c['label']))
            results.append(dict(open_ended=open_ended, set=responded, unset=polled-responded, categories=categories))

        else:
            categories_label = self.response_categories.filter(is_active=True).values_list('category', flat=True)
            question_results = self.get_question_results()

            if segment:

                location_part = segment.get('location').lower()

                if location_part not in ['state', 'district']:
                    return None

                location_boundaries = org.get_segment_org_boundaries(segment)

                for boundary in location_boundaries:
                    categories = []
                    osm_id = boundary.get('osm_id').upper()
                    set_count = 0
                    unset_count_key = "ruleset:%s:nocategory:%s:%s" % (self.ruleset_uuid, location_part, osm_id)
                    unset_count = question_results.get(unset_count_key, 0)

                    for categorie_label in categories_label:
                        category_count_key = "ruleset:%s:category:%s:%s:%s" % (self.ruleset_uuid, categorie_label.lower(), location_part, osm_id)
                        category_count = question_results.get(category_count_key, 0)
                        set_count += category_count
                        categories.append(dict(count=category_count, label=categorie_label))

                    if open_ended:
                        # For home page best and worst location responses
                        from ureport.contacts.models import Contact
                        if segment.get('location') == 'District':
                            boundary_contacts_count = Contact.objects.filter(org=org, district=osm_id).count()
                        else:
                            boundary_contacts_count = Contact.objects.filter(org=org, state=osm_id).count()
                        unset_count = boundary_contacts_count - set_count

                    results.append(dict(open_ended=open_ended, set=set_count, unset=unset_count,
                                        boundary=osm_id, label=boundary.get('name'),
                                        categories=categories))

            else:
                categories = []
                for categorie_label in categories_label:
                    category_count_key = "ruleset:%s:category:%s" % (self.ruleset_uuid, categorie_label.lower())
                    if categorie_label.lower() != 'other':
                        category_count = question_results.get(category_count_key, 0)
                        categories.append(dict(count=category_count, label=categorie_label))

                results.append(dict(open_ended=open_ended, set=responded, unset=polled-responded, categories=categories))

        cache.set(key, {"results": results}, PollQuestion.POLL_QUESTION_RESULTS_CACHE_TIMEOUT)

        return results

    def get_total_summary_data(self):
        cached_results = self.get_results()
        if cached_results:
            return cached_results[0]
        return dict()

    def get_question_results(self):
        return PollResultsCounter.get_question_results(self)

    def is_open_ended(self):
        return self.response_categories.filter(is_active=True).count() == 1

    def get_responded(self):
        results = self.get_question_results()
        key = 'ruleset:%s:total-ruleset-responded' % self.ruleset_uuid
        return results.get(key, 0)

    def get_polled(self):
        first_question = self.poll.get_questions()[0]
        if self.pk == first_question.pk:
            try:
                polled = int(self.poll.runs_count)
            except ValueError:
                polled = 0
            return polled

        results = self.get_question_results()
        key = 'ruleset:%s:total-ruleset-polled' % self.ruleset_uuid
        return results.get(key, 0)

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

    class Meta:
        unique_together = ('poll', 'ruleset_uuid')


class PollResponseCategory(models.Model):
    question = models.ForeignKey(PollQuestion, related_name='response_categories')

    rule_uuid = models.CharField(max_length=36, help_text=_("The Rule this response category is based on"))

    category = models.TextField(null=True)

    is_active = models.BooleanField(default=True)

    @classmethod
    def update_or_create(cls, question, rule_uuid, category):
        existing = cls.objects.filter(question=question, rule_uuid=rule_uuid)
        if existing:
            existing.update(category=category, is_active=True)
        else:
            cls.objects.create(question=question, rule_uuid=rule_uuid, category=category, is_active=True)

    class Meta:
        unique_together = ('question', 'rule_uuid')


class PollResult(models.Model):

    POLL_RESULTS_LAST_PULL_CACHE_KEY = 'last:pull_results:org:%d:poll:%d'

    POLL_REBUILD_COUNTS_LOCK = 'poll-rebuild-counts-lock:org:%d:poll:%d'

    POLL_REBUILD_COUNTS_FINISHED_FLAG = 'poll-counts-finished:org:%d:poll:%d'

    org = models.ForeignKey(Org, related_name="poll_results", db_index=False)

    flow = models.CharField(max_length=36)

    ruleset = models.CharField(max_length=36)

    contact = models.CharField(max_length=36)

    date = models.DateTimeField(null=True)

    completed = models.BooleanField()

    category = models.CharField(max_length=255, null=True)

    text = models.CharField(max_length=640, null=True)

    state = models.CharField(max_length=255, null=True)

    district = models.CharField(max_length=255, null=True)

    ward = models.CharField(max_length=255, null=True)

    def generate_counters(self):
        generated_counters = dict()

        if not self.org_id or not self.flow or not self.ruleset:
            return generated_counters

        org_id = self.org_id
        ruleset = ''
        category = ''
        state = ''
        district = ''
        ward = ''

        if self.ruleset:
            ruleset = self.ruleset.lower()

        if self.category:
            category = self.category.lower()

        if self.state:
            state = self.state.upper()

        if self.district:
            district = self.district.upper()

        if self.ward:
            ward = self.ward.upper()

        generated_counters['ruleset:%s:total-ruleset-polled' % ruleset] = 1

        if category:
            generated_counters['ruleset:%s:total-ruleset-responded' % ruleset] = 1

            generated_counters['ruleset:%s:category:%s' % (ruleset, category)] = 1

        if state and category:
            generated_counters['ruleset:%s:category:%s:state:%s' % (ruleset, category, state)] = 1

        elif state:

            generated_counters['ruleset:%s:nocategory:state:%s' % (ruleset, state)] = 1

        if district and category:
            generated_counters['ruleset:%s:category:%s:district:%s' % (ruleset, category, district)] = 1

        elif district:
            generated_counters['ruleset:%s:nocategory:district:%s' % (ruleset, district)] = 1

        if ward and category:
            generated_counters['ruleset:%s:category:%s:ward:%s' % (ruleset, category, ward)] = 1

        elif ward:
            generated_counters['ruleset:%s:nocategory:ward:%s' % (ruleset, ward)] = 1

        return generated_counters

    class Meta:
        index_together = ["org", "flow"]


class PollResultsCounter(models.Model):

    LAST_SQUASH_KEY = 'last-poll-results-counter-squash'
    COUNTS_SQUASH_LOCK = 'poll-results-counter-squash-lock'

    org = models.ForeignKey(Org, related_name='results_counters')

    ruleset = models.CharField(max_length=36)

    type = models.CharField(max_length=255)

    count = models.IntegerField(default=0, help_text=_("Number of items with this counter"))

    @classmethod
    def get_poll_results(cls, poll, types=None):
        """
        Get the poll results counts by counter type for a given poll
        """
        poll_rulesets = poll.questions.all().values_list('ruleset_uuid', flat=True)

        counters = cls.objects.filter(org=poll.org, ruleset__in=poll_rulesets)
        if types:
            counters = counters.filter(type__in=types)

        results = counters.values('type').order_by('type').annotate(count_sum=Sum('count'))

        return {c['type']: c['count_sum'] for c in results}

    @classmethod
    def get_question_results(cls, question, types=None):
        """
        Get the poll question results counts by counter type for a given poll
        """
        counters = cls.objects.filter(org=question.poll.org, ruleset=question.ruleset_uuid)
        if types:
            counters = counters.filter(type__in=types)

        results = counters.values('type').order_by('type').annotate(count_sum=Sum('count'))

        return {c['type']: c['count_sum'] for c in results}

    class Meta:
        index_together = ["org", "ruleset", "type"]
