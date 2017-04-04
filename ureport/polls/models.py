from __future__ import unicode_literals
import json
from collections import defaultdict

import logging
import pytz
from datetime import timedelta
from django.contrib.auth.models import User
from django.db import models, connection
from django.db.models import Sum, Count
from django.utils.text import slugify
from django.utils import timezone
from smartmin.models import SmartModel
from django.utils.translation import ugettext_lazy as _, ugettext
from django.core.cache import cache
from dash.orgs.models import Org
from dash.categories.models import Category, CategoryImage
from django.conf import settings
from stop_words import safe_get_stop_words

from django_redis import get_redis_connection
from xlrd import XLRDError

logger = logging.getLogger(__name__)

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

    POLL_REBUILD_COUNTS_LOCK = 'poll-rebuild-counts-lock:org:%d:poll:%s'

    POLL_RESULTS_LAST_PULL_CACHE_KEY = 'last:pull_results:org:%d:poll:%s'

    POLL_RESULTS_MAX_SYNC_RUNS = 100000

    POLL_RESULTS_LAST_PULL_CURSOR = 'last:poll_pull_results_cursor:org:%d:poll:%s'

    POLL_RESULTS_CURSOR_AFTER_CACHE_KEY = 'last:poll_pull_results_cursor_after:org:%d:poll:%s'

    POLL_RESULTS_CURSOR_BEFORE_CACHE_KEY = 'last:poll_pull_results_cursor_before:org:%d:poll:%s'

    POLL_RESULTS_BATCHES_LATEST_CACHE_KEY = 'last:poll_pull_results_cursor_latest:org:%d:poll:%s'

    POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG = 'poll-results-pull-after-delete-flag:%s:%s'

    POLL_MOST_RESPONDED_REGIONS_CACHE_KEY = 'most-responded-regions:%s'

    POLL_SYNC_LOCK_TIMEOUT = 60 * 30

    flow_uuid = models.CharField(max_length=36, help_text=_("The Flow this Poll is based on"))

    poll_date = models.DateTimeField(help_text=_("The date to display for this poll. "
                                                 "Leave empty to use flow creation date."))

    flow_archived = models.BooleanField(default=False,
                                        help_text=_("Whether the flow for this poll is archived on RapidPro"))

    base_language = models.CharField(max_length=4, default='base', help_text=_("The base language of the flow to use"))

    runs_count = models.IntegerField(default=0,
                                     help_text=_("The number of polled reporters on this poll"))

    has_synced = models.BooleanField(default=False,
                                     help_text=_("Whether the poll has finished the initial results sync."))

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

    def get_sync_progress(self):
        if not self.runs_count:
            return float(0)

        results_added = PollResult.objects.filter(flow=self.flow_uuid, org=self.org_id).values('ruleset').distinct()
        results_added = results_added.annotate(Count('id')).order_by('-id__count').first()
        pulled_runs = 0
        if results_added:
            pulled_runs = results_added.get("id__count", 0)

        return pulled_runs * 100 / float(self.runs_count)

    @classmethod
    def pull_results(cls, poll_id):
        from ureport.backend import get_backend
        backend = get_backend()
        poll = Poll.objects.get(pk=poll_id)

        (num_val_created, num_val_updated, num_val_ignored,
         num_path_created, num_path_updated, num_path_ignored) = backend.pull_results(poll, None, None)

        poll.rebuild_poll_results_counts()

        Poll.objects.filter(org=poll.org_id, flow_uuid=poll.flow_uuid).update(has_synced=True)

        return num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored

    def get_pull_cached_params(self):

        after = cache.get(Poll.POLL_RESULTS_CURSOR_AFTER_CACHE_KEY % (self.org.pk, self.flow_uuid), None)

        before = cache.get(Poll.POLL_RESULTS_CURSOR_BEFORE_CACHE_KEY % (self.org.pk, self.flow_uuid), None)

        batches_latest = cache.get(Poll.POLL_RESULTS_BATCHES_LATEST_CACHE_KEY % (self.org.pk, self.flow_uuid), None)

        latest_synced_obj_time = cache.get(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.org.pk, self.flow_uuid), None)

        resume_cursor = cache.get(Poll.POLL_RESULTS_LAST_PULL_CURSOR % (self.org.pk, self.flow_uuid), None)

        pull_after_delete = cache.get(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.org.pk, self.pk), None)

        return after, before, latest_synced_obj_time, batches_latest, resume_cursor, pull_after_delete

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

    def update_questions_results_cache(self):
        for question in self.questions.all():
            question.calculate_results()
            question.calculate_results(segment=dict(location='State'))
            question.calculate_results(segment=dict(age='Age'))
            question.calculate_results(segment=dict(gender='Gender'))
            question.get_most_responded_regions()

    @classmethod
    def pull_poll_results_task(cls, poll):
        from ureport.polls.tasks import pull_refresh
        pull_refresh.apply_async((poll.pk,), queue='sync')

    def pull_refresh_task(self):
        from ureport.utils import datetime_to_json_date

        now = timezone.now()
        cache.set(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.org_id, self.pk),
                  datetime_to_json_date(now.replace(tzinfo=pytz.utc)), None)

        Poll.pull_poll_results_task(self)

    def rebuild_poll_results_counts(self):
        from ureport.utils import chunk_list
        import time

        start = time.time()

        poll_id = self.pk
        org_id = self.org_id
        flow = self.flow_uuid

        r = get_redis_connection()

        key = Poll.POLL_REBUILD_COUNTS_LOCK % (org_id, flow)

        if r.get(key):
            print "Already rebuilding counts for poll #%d on org #%d" % (poll_id, org_id)

        else:
            with r.lock(key):
                poll_results_ids = PollResult.objects.filter(org_id=org_id, flow=flow).values_list('pk', flat=True)

                poll_results_ids_count = len(poll_results_ids)

                print "Results query time for pair %s, %s took %ds" % (org_id, flow, time.time() - start)

                processed_results = 0
                counters_dict = defaultdict(int)

                for batch in chunk_list(poll_results_ids, 1000):
                    poll_results = list(PollResult.objects.filter(pk__in=batch))

                    for result in poll_results:
                        gen_counters = result.generate_counters()
                        for dict_key in gen_counters.keys():
                            counters_dict[(result.org_id, result.ruleset, dict_key)] += gen_counters[dict_key]

                        processed_results += 1

                print "Rebuild counts progress... build counters dict for pair %s, %s, processed %d of %d in %ds" % (org_id, flow, processed_results, poll_results_ids_count, time.time() - start)

                counters_to_insert = []
                for counter_tuple in counters_dict.keys():
                    org_id, ruleset, counter_type = counter_tuple
                    count = counters_dict[counter_tuple]
                    counters_to_insert.append(PollResultsCounter(org_id=org_id, ruleset=ruleset, type=counter_type,
                                                                 count=count))

                # Delete existing counters and then create new counters
                self.delete_poll_results_counter()

                PollResultsCounter.objects.bulk_create(counters_to_insert)
                print "Finished Rebuilding the counters for poll #%d on org #%d in %ds, inserted %d counters objects for %s results" % (poll_id, org_id, time.time() - start, len(counters_to_insert), poll_results_ids_count)

                start_update_cache = time.time()
                self.update_questions_results_cache()
                print "Calculated questions results and updated the cache for poll #%d on org #%d in %ds" % (poll_id, org_id, time.time() - start_update_cache)

                print "Poll responses counts for poll #%d on org #%d are %s responded out of %s polled" % (poll_id, org_id, self.responded_runs(), self.runs())

    def get_question_uuids(self):
        return self.questions.values_list('ruleset_uuid', flat=True)

    @classmethod
    def get_public_polls(cls, org):
        return Poll.objects.filter(org=org, is_active=True, category__is_active=True, has_synced=True)

    @classmethod
    def get_main_poll(cls, org):
        poll_with_questions = PollQuestion.objects.filter(is_active=True, poll__org=org).values_list('poll', flat=True)

        polls = Poll.get_public_polls(org=org).filter(pk__in=poll_with_questions).order_by('-created_on')

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

            polls = Poll.get_public_polls(org=org).filter(pk__in=poll_with_questions).order_by('-is_featured', '-created_on')
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

        other_polls = Poll.get_public_polls(org=org).exclude(pk__in=exclude_polls).order_by('-created_on')

        return other_polls

    @classmethod
    def get_recent_other_polls(cls, org):
        now = timezone.now()
        recent_window = now - timedelta(days=7)

        recent_other_polls = Poll.get_other_polls(org).exclude(created_on__lte=recent_window).order_by('-created_on')

        return recent_other_polls

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
        temba_client = org.get_temba_client(api_version=2)
        export_definition = temba_client.get_definitions(flows=(self.flow_uuid, ))

        flow_definition = export_definition.flows[0]

        base_language = flow_definition['base_language']

        self.base_language = base_language
        self.save()

        flow_rulesets = flow_definition['rule_sets']

        for ruleset in flow_rulesets:
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

    def most_responded_regions(self):
        # get our first question
        top_question = self.get_questions().first()
        if top_question:
            # do we already have a cached set
            cached = cache.get(Poll.POLL_MOST_RESPONDED_REGIONS_CACHE_KEY % top_question.ruleset_uuid)
            if cached:
                return cached

            return top_question.get_most_responded_regions()

        return []

    def response_percentage(self):
        """
        The response rate for this flow
        """
        top_question = self.get_questions().first()
        if top_question:
            return top_question.get_response_percentage()
        return '---'

    def get_trending_words(self):
        cache_key = 'trending_words:%d' % self.pk
        trending_words = cache.get(cache_key)

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

            trending_words = [k for k, v in tuples]

            cache.set(cache_key, trending_words, 3600)

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

    @classmethod
    def prepare_fields(cls, field_dict, import_params=None, user=None):
        if not import_params or 'org_id' not in import_params:
            raise Exception('Import params must include org_id')

        field_dict['created_by'] = user
        field_dict['org'] = Org.objects.get(pk=import_params['org_id'])

        return field_dict

    @classmethod
    def create_instance(cls, field_dict):
        if 'org' not in field_dict:
            raise ValueError("Import fields dictionary must include org")

        if 'created_by' not in field_dict:
            raise ValueError("Import fields dictionary must include created_by")

        if 'category' not in field_dict:
            raise ValueError("Import fields dictionary must include category")

        if 'uuid' not in field_dict:
            raise ValueError("Import fields dictionary must include uuid")

        if 'name' not in field_dict:
            raise ValueError("Import fields dictionary must include name")

        if 'created_on' not in field_dict:
            raise ValueError("Import fields dictionary must include created_on")

        if 'ruleset_uuid' not in field_dict:
            raise ValueError("Import fields dictionary must include ruleset_uuid")

        if 'question' not in field_dict:
            raise ValueError("Import fields dictionary must include question")

        org = field_dict.pop('org')
        user = field_dict.pop('created_by')

        category = field_dict.pop('category')

        uuid = field_dict.pop('uuid')
        name = field_dict.pop('name')
        created_on = field_dict.pop('created_on')

        ruleset_uuid = field_dict.pop('ruleset_uuid')
        question = field_dict.pop('question')

        category_obj = Category.objects.filter(org=org, name=category).first()
        if not category_obj:
            category_obj = Category.objects.create(org=org, name=category, created_by=user, modified_by=user)

        existing_polls = Poll.objects.filter(org=org, flow_uuid=uuid, category=category_obj)

        imported_poll = None
        for poll in existing_polls:
            if poll.questions.filter(ruleset_uuid=ruleset_uuid).exists():
                imported_poll = Poll.objects.filter(pk=poll.pk).first()

                if imported_poll:
                    Poll.objects.filter(pk=imported_poll.pk).update(title=name)

        if not imported_poll:
            imported_poll = Poll.objects.create(flow_uuid=uuid, title=name, poll_date=created_on, org=org,
                                                category=category_obj, created_by=user, modified_by=user)

        poll_question = PollQuestion.update_or_create(user, imported_poll, '', ruleset_uuid, 'wait_message')
        PollQuestion.objects.filter(pk=poll_question.pk).update(title=question, is_active=True)

        # hide all other questions
        PollQuestion.objects.filter(poll=imported_poll).exclude(pk=poll_question.pk).update(is_active=False)

        return imported_poll

    @classmethod
    def update_or_create_questions_task(cls, records):
        from .tasks import update_or_create_questions

        record_ids = []

        for record in records:
            record_ids.append(record.id)

        if record_ids:
            update_or_create_questions.delay(record_ids)


    @classmethod
    def import_csv(cls, task, log=None):
        csv_file = task.csv_file
        csv_file.open()

        # this file isn't good enough, lets write it to local disk
        from django.conf import settings
        from uuid import uuid4
        import os

        # make sure our tmp directory is present (throws if already present)
        try:
            os.makedirs(os.path.join(settings.MEDIA_ROOT, 'tmp'))
        except Exception:
            pass

        # write our file out
        tmp_file = os.path.join(settings.MEDIA_ROOT, 'tmp/%s' % str(uuid4()))

        out_file = open(tmp_file, 'wb')
        out_file.write(csv_file.read())
        out_file.close()

        filename = out_file
        user = task.created_by

        import_params = None
        import_results = dict()

        # additional parameters are optional
        if task.import_params:
            try:
                import_params = json.loads(task.import_params)
            except:
                pass

        try:
            records = cls.import_xls(filename, user, import_params, log, import_results)
        except XLRDError:
            records = cls.import_raw_csv(filename, user, import_params, log, import_results)
        finally:
            os.remove(tmp_file)

        task.import_results = json.dumps(import_results)

        Poll.update_or_create_questions_task(records)

        return records

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
    POLL_QUESTION_RESULTS_CACHE_TIMEOUT = 60 * 12

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

    def get_most_responded_regions(self):
        top_regions = []

        boundary_results = self.get_results(segment=dict(location='State'))
        if not boundary_results:
            return []

        boundary_responses = dict()
        for boundary in boundary_results:
            total = boundary['set'] + boundary['unset']
            responded = boundary['set']
            boundary_responses[boundary['label']] = dict(responded=responded, total=total)

        for boundary in sorted(boundary_responses, key=lambda x: boundary_responses[x]['responded'], reverse=True)[:5]:
            responded = boundary_responses[boundary]
            percent = int(round((100 * responded['responded'])) / responded['total']) if responded['total'] > 0 else 0
            top_regions.append(
                dict(boundary=boundary, responded=responded['responded'], total=responded['total'], type='best',
                     percent=percent))

        # no actual results by region yet
        if top_regions and top_regions[0]['responded'] == 0:
            top_regions = []

        cache.set(Poll.POLL_MOST_RESPONDED_REGIONS_CACHE_KEY % self.ruleset_uuid, top_regions, 900)

        return top_regions

    def get_results(self, segment=None):
        key = PollQuestion.POLL_QUESTION_RESULTS_CACHE_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
        if segment:
            substituted_segment = self.poll.org.substitute_segment(segment)
            key += ":" + slugify(unicode(json.dumps(substituted_segment)))

        cached_value = cache.get(key, None)
        if cached_value:
            return cached_value["results"]

        if not segment:
            logger.error('Question get results without segment cache missed', extra={'stack': True,})

        if segment and segment.get('location').lower() == 'state':
            logger.error('Question get results with state segment cache missed', extra={'stack': True,})

        return self.calculate_results(segment=segment)

    def calculate_results(self, segment=None):

        org = self.poll.org
        open_ended = self.is_open_ended()
        responded = self.get_responded()
        polled = self.get_polled()

        results = []

        if open_ended and not segment:
            custom_sql = """
                      SELECT w.label, count(*) AS count FROM (SELECT regexp_split_to_table(LOWER(text), E'[^[:alnum:]_]') AS label FROM polls_pollresult WHERE polls_pollresult.org_id = %d AND polls_pollresult.flow = '%s' AND polls_pollresult.ruleset = '%s' AND polls_pollresult.text IS NOT NULL AND polls_pollresult.text NOT ILIKE '%s') w group by w.label;
                      """ % (org.id, self.poll.flow_uuid, self.ruleset_uuid, "http%")
            with connection.cursor() as cursor:
                cursor.execute(custom_sql)
                from ureport.utils import get_dict_from_cursor
                unclean_categories = get_dict_from_cursor(cursor)

            ureport_languages = getattr(settings, 'LANGUAGES', [('en', 'English')])

            org_languages = [lang[1].lower() for lang in ureport_languages if lang[0] == org.language]

            if 'english' not in org_languages:
                org_languages.append('english')

            ignore_words = []
            for lang in org_languages:
                ignore_words += safe_get_stop_words(lang)

            categories = []

            # sort by count, then alphabetically
            unclean_categories = sorted(unclean_categories, key=lambda c: (-c['count'], c['label']))

            for category in unclean_categories:
                if len(category['label']) > 1 and category['label'] not in ignore_words and len(categories) < 100:
                    categories.append(dict(label=category['label'], count=int(category['count'])))

            results.append(dict(open_ended=open_ended, set=responded, unset=polled-responded, categories=categories))

        else:
            categories_label = self.response_categories.filter(is_active=True).values_list('category', flat=True)
            question_results = self.get_question_results()

            if segment:

                location_part = segment.get('location', '').lower()
                age_part = segment.get('age', '').lower()
                gender_part = segment.get('gender', '').lower()

                if location_part in ['state', 'district', 'ward']:

                    location_boundaries = org.get_segment_org_boundaries(segment)

                    for boundary in location_boundaries:
                        categories = []
                        osm_id = boundary.get('osm_id').upper()
                        set_count = 0
                        unset_count_key = "ruleset:%s:nocategory:%s:%s" % (self.ruleset_uuid, location_part, osm_id)
                        unset_count = question_results.get(unset_count_key, 0)

                        for categorie_label in categories_label:
                            if categorie_label.lower() not in PollResponseCategory.IGNORED_CATEGORY_RULES:
                                category_count_key = "ruleset:%s:category:%s:%s:%s" % (self.ruleset_uuid, categorie_label.lower(), location_part, osm_id)
                                category_count = question_results.get(category_count_key, 0)
                                set_count += category_count
                                categories.append(dict(count=category_count, label=categorie_label))

                        results.append(dict(open_ended=open_ended, set=set_count, unset=unset_count,
                                            boundary=osm_id, label=boundary.get('name'),
                                            categories=categories))
                elif age_part:
                    poll_year = self.poll.poll_date.year

                    born_results = {k: v for k, v in question_results.iteritems() if k[-9:-5] == 'born'}

                    age_intervals = dict()
                    age_intervals['35+'] = (35, 2000)
                    age_intervals['31-34'] = (31, 34)
                    age_intervals['25-30'] = (25, 30)
                    age_intervals['20-24'] = (20, 24)
                    age_intervals['15-19'] = (15, 19)
                    age_intervals['0-14'] = (0, 14)

                    for age_group in age_intervals.keys():
                        lower_bound, upper_bound = age_intervals[age_group]
                        unset_count = 0

                        categories_count = dict()
                        for categorie_label in categories_label:
                            if categorie_label.lower() not in PollResponseCategory.IGNORED_CATEGORY_RULES:
                                categories_count[categorie_label.lower()] = 0

                        for result_key, result_count in born_results.iteritems():
                            age = poll_year - int(result_key[-4:])

                            if lower_bound <= age < upper_bound:
                                if 'nocategory' in result_key:
                                    unset_count += result_count

                                for categorie_label in categories_label:
                                    if categorie_label.lower() not in PollResponseCategory.IGNORED_CATEGORY_RULES:
                                        if result_key.startswith('ruleset:%s:category:%s:' % (self.ruleset_uuid, categorie_label.lower())):
                                            categories_count[categorie_label.lower()] += result_count

                        categories = [dict(count=v, label=k) for k, v in categories_count.iteritems()]

                        set_count = sum([elt['count'] for elt in categories])

                        results.append(dict(set=set_count, unset=unset_count, label=age_group,
                                            categories=categories))

                    results = sorted(results, key=lambda i:i['label'])

                elif gender_part:

                    genders = ['f', 'm']
                    gender_labels = dict(f=_('Female'), m=_('Male'))

                    for gender in genders:
                        categories = []
                        set_count = 0
                        unset_count_key = "ruleset:%s:nocategory:%s:%s"% (self.ruleset_uuid, 'gender', gender)
                        unset_count = question_results.get(unset_count_key, 0)

                        for categorie_label in categories_label:
                            category_count_key = "ruleset:%s:category:%s:%s:%s" % (self.ruleset_uuid, categorie_label.lower(), 'gender', gender)
                            if categorie_label.lower() not in PollResponseCategory.IGNORED_CATEGORY_RULES:
                                category_count = question_results.get(category_count_key, 0)
                                set_count += category_count
                                categories.append(dict(count=category_count, label=categorie_label))

                        results.append(dict(set=set_count, unset=unset_count, label=gender_labels.get(gender),
                                            categories=categories))

            else:
                categories = []
                for categorie_label in categories_label:
                    category_count_key = "ruleset:%s:category:%s" % (self.ruleset_uuid, categorie_label.lower())
                    if categorie_label.lower() not in PollResponseCategory.IGNORED_CATEGORY_RULES:
                        category_count = question_results.get(category_count_key, 0)
                        categories.append(dict(count=category_count, label=categorie_label))

                results.append(dict(open_ended=open_ended, set=responded, unset=polled-responded, categories=categories))

        cache_time = PollQuestion.POLL_QUESTION_RESULTS_CACHE_TIMEOUT
        if not segment:
            cache_time = None

        if segment and segment.get('location', '').lower() == 'state':
            cache_time = None

        if segment and segment.get('age', '').lower() == 'age':
            cache_time = None

        if segment and segment.get('gender', '').lower() == 'gender':
            cache_time = None

        key = PollQuestion.POLL_QUESTION_RESULTS_CACHE_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
        if segment:
            substituted_segment = self.poll.org.substitute_segment(segment)
            key += ":" + slugify(unicode(json.dumps(substituted_segment)))

        cache.set(key, {"results": results}, cache_time)

        return results

    def get_total_summary_data(self):
        cached_results = self.get_results()
        if cached_results:
            return cached_results[0]
        return dict()

    def get_question_results(self):
        return PollResultsCounter.get_question_results(self)

    def is_open_ended(self):
        return self.response_categories.filter(is_active=True).exclude(category__icontains='no response').count() == 1

    def get_responded(self):
        results = self.get_question_results()
        key = 'ruleset:%s:total-ruleset-responded' % self.ruleset_uuid
        return results.get(key, 0)

    def get_polled(self):
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
    IGNORED_CATEGORY_RULES = ['other', 'no response']

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

    gender = models.CharField(max_length=1, null=True)

    born = models.IntegerField(null=True)

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
        born = ''
        gender = ''
        text = ''

        if self.text and self.text != "None":
            text = self.text

        if self.ruleset:
            ruleset = self.ruleset.lower()

        if self.category and self.category.lower() not in PollResponseCategory.IGNORED_CATEGORY_RULES:
            category = self.category.lower()

        if self.state:
            state = self.state.upper()

        if self.district:
            district = self.district.upper()

        if self.ward:
            ward = self.ward.upper()

        if self.born:
            born = self.born

        if self.gender:
            gender = self.gender.lower()

        generated_counters['ruleset:%s:total-ruleset-polled' % ruleset] = 1

        if category or (self.category is not None and self.category.lower() == 'no response' and text):
            generated_counters['ruleset:%s:total-ruleset-responded' % ruleset] = 1

        if category:
            generated_counters['ruleset:%s:category:%s' % (ruleset, category)] = 1

        if category and born:
            generated_counters['ruleset:%s:category:%s:born:%s' % (ruleset, category, born)] = 1
        elif born:
            generated_counters['ruleset:%s:nocategory:born:%s' % (ruleset, born)] = 1

        if category and gender:
            generated_counters['ruleset:%s:category:%s:gender:%s' % (ruleset, category, gender)] = 1
        elif gender:
            generated_counters['ruleset:%s:nocategory:gender:%s' % (ruleset, gender)] = 1

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
        index_together = [["org", "flow"], ["org", "flow", "ruleset", "text"]]


class PollResultsCounter(models.Model):

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
