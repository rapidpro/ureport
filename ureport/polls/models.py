# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import logging
import uuid
from collections import defaultdict
from datetime import timedelta, timezone as tzone

import six
from django_valkey import get_valkey_connection

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection, models
from django.db.models import Count, F, Prefetch, Q, Sum
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from dash.categories.models import Category, CategoryImage
from dash.orgs.models import Org, OrgBackend
from dash.tags.models import Tag
from smartmin.models import SmartModel
from ureport.flows.models import FlowResult, FlowResultCategory


logger = logging.getLogger(__name__)

# cache whether a question is open ended for a month

OPEN_ENDED_CACHE_TIME = getattr(settings, "OPEN_ENDED_CACHE_TIME", 60 * 60 * 24 * 30)

# cache our featured polls for a month (this will be invalidated by questions changing)
BRICK_POLLS_CACHE_TIME = getattr(settings, "BRICK_POLLS_CACHE_TIME", 60 * 60 * 30)

POLL_RESULTS_CACHE_TIME = getattr(settings, "POLL_RESULTS_CACHE_TIME", 60 * 60 * 24)

# big cache time for task cached data, we run more often the task to update the data
UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME = getattr(settings, "UREPORT_ASYNC_FETCHED_DATA_CACHE_TIME", 60 * 60 * 24 * 15)

# time to cache data we fetch directly from the api not with a task
UREPORT_RUN_FETCHED_DATA_CACHE_TIME = getattr(settings, "UREPORT_RUN_FETCHED_DATA_CACHE_TIME", 60 * 10)

CACHE_POLL_RESULTS_KEY = "org:%d:poll:%d:results:%d"

CACHE_ORG_FLOWS_KEY = "org:%d:backend:%s:flows"

CACHE_ORG_REPORTER_GROUP_KEY = "org:%d:reporters:%s"

CACHE_ORG_FIELD_DATA_KEY = "org:%d:field:%s:segment:%s"

CACHE_ORG_GENDER_DATA_KEY = "org:%d:gender:%s"

CACHE_ORG_AGE_DATA_KEY = "org:%d:age:%s"

CACHE_ORG_REGISTRATION_DATA_KEY = "org:%d:registration:%s"

CACHE_ORG_OCCUPATION_DATA_KEY = "org:%d:occupation:%s"


@six.python_2_unicode_compatible
class PollCategory(SmartModel):
    """
    This is a dead class but here so we can perform our migration.
    """

    name = models.CharField(max_length=64, help_text=_("The name of this poll category"))
    org = models.ForeignKey(Org, on_delete=models.PROTECT, help_text=_("The organization this category applies to"))

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["name", "org"], name="polls_pollcategory_name_156693e034f96627_uniq")
        ]
        verbose_name_plural = _("Poll Categories")


@six.python_2_unicode_compatible
class Poll(SmartModel):
    """
    A poll represents a single Flow that has been brought in for
    display and sharing in the UReport platform.
    """

    ORG_MAIN_POLL_ID = "org:%d:main-poll-id"

    POLL_PULL_RESULTS_TASK_LOCK = "poll-pull-results-task-lock:%s:%s"

    POLL_REBUILD_COUNTS_LOCK = "poll-rebuild-counts-lock:org:%d:poll:%s"

    POLL_RESULTS_LAST_PULL_CACHE_KEY = "last:pull_results:reverse:org:%d:poll:%s"

    POLL_RESULTS_LAST_SYNC_TIME_CACHE_KEY = "last:sync_time:org:%d:poll:%s"

    POLL_RESULTS_MAX_SYNC_RUNS = 100_000

    POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_KEY = "last:poll_last_other_polls_sync:org:%d:poll:%s"

    POLL_RESULTS_LAST_OTHER_POLLS_SYNCED_CACHE_TIMEOUT = 60 * 60 * 24 * 2

    POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG = "poll-results-pull-after-delete-flag:%s:%s"

    POLL_SYNC_LOCK_TIMEOUT = 60 * 60 * 2

    published = models.BooleanField(
        default=True, help_text=_("Whether this poll should be visible/hidden on the public site")
    )

    flow_uuid = models.CharField(max_length=36, help_text=_("The Flow this Poll is based on"))

    poll_date = models.DateTimeField(
        help_text=_("The date to display for this poll. " "Leave empty to use flow creation date.")
    )

    flow_archived = models.BooleanField(
        default=False, help_text=_("Whether the flow for this poll is archived on RapidPro")
    )

    base_language = models.CharField(max_length=4, default="base", help_text=_("The base language of the flow to use"))

    runs_count = models.IntegerField(default=0, help_text=_("The number of polled reporters on this poll"))

    has_synced = models.BooleanField(
        default=False, help_text=_("Whether the poll has finished the initial results sync.")
    )

    stopped_syncing = models.BooleanField(
        default=False, help_text=_("Whether the poll should stop regenerating stats.")
    )

    title = models.CharField(max_length=255, help_text=_("The title for this Poll"))
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="polls", help_text=_("The category this Poll belongs to")
    )
    is_featured = models.BooleanField(
        default=False, help_text=_("Whether this poll should be featured on the homepage")
    )
    category_image = models.ForeignKey(
        CategoryImage,
        on_delete=models.PROTECT,
        null=True,
        help_text=_("The splash category image to display for the poll (optional)"),
    )
    org = models.ForeignKey(
        Org, on_delete=models.PROTECT, related_name="polls", help_text=_("The organization this poll is part of")
    )

    backend = models.ForeignKey(OrgBackend, on_delete=models.PROTECT, null=True)

    response_title = models.CharField(
        max_length=255, help_text=_("The title for this response story"), null=True, blank=True
    )

    response_author = models.CharField(
        max_length=255, help_text=_("The writer of the response story"), null=True, blank=True
    )

    response_content = models.TextField(help_text=_("The body of text for the story"), null=True, blank=True)

    tags = models.ManyToManyField(Tag, blank=True)

    def get_sync_progress(self):
        if not self.runs_count:
            return float(0)

        results_added = PollResult.objects.filter(flow=self.flow_uuid, org=self.org_id).values("ruleset").distinct()
        results_added = results_added.annotate(Count("id")).order_by("-id__count").first()
        pulled_runs = 0
        if results_added:
            pulled_runs = results_added.get("id__count", 0)

        return pulled_runs * 100 / float(self.runs_count)

    @classmethod
    def pull_results_from_archives(cls, poll_id):
        poll = Poll.objects.get(pk=poll_id)
        backend = poll.org.get_backend(backend_slug=poll.backend.slug)

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = backend.pull_results_from_archives(poll)

        if num_val_created + num_val_updated + num_path_created + num_path_updated != 0:
            poll.rebuild_poll_results_counts()

        Poll.objects.filter(org=poll.org_id, flow_uuid=poll.flow_uuid).update(has_synced=True)

        return num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored

    @classmethod
    def pull_results(cls, poll_id):
        from ureport.utils import json_date_to_datetime

        poll = Poll.objects.get(pk=poll_id)
        backend = poll.org.get_backend(backend_slug=poll.backend.slug)

        flow_date_json = poll.get_flow_date()
        now = timezone.now()

        has_archives_results = flow_date_json is None or (
            json_date_to_datetime(flow_date_json) + timedelta(days=90) < now
        )

        if has_archives_results and not poll.has_synced:
            from ureport.polls.tasks import pull_refresh_from_archives

            pull_refresh_from_archives.apply_async((poll.pk,), queue="sync")

        (
            num_val_created,
            num_val_updated,
            num_val_ignored,
            num_path_created,
            num_path_updated,
            num_path_ignored,
        ) = backend.pull_results(poll, None, None)

        if num_val_created + num_val_updated + num_path_created + num_path_updated != 0:
            poll.rebuild_poll_results_counts()

        Poll.objects.filter(org=poll.org_id, flow_uuid=poll.flow_uuid).update(has_synced=True)

        return num_val_created, num_val_updated, num_val_ignored, num_path_created, num_path_updated, num_path_ignored

    def get_pull_cached_params(self):
        latest_synced_obj_time = cache.get(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.org.pk, self.flow_uuid), None)

        pull_after_delete = cache.get(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.org.pk, self.pk), None)

        return latest_synced_obj_time, pull_after_delete

    def delete_poll_stats(self):
        from ureport.stats.models import PollStats
        from ureport.utils import chunk_list

        if self.stopped_syncing:
            logger.error("Poll cannot delete stats for poll #%d on org #%d" % (self.pk, self.org_id), exc_info=True)
            return

        flow_result_ids = self.questions.all().values_list("flow_result_id", flat=True)

        poll_stats_ids = PollStats.objects.filter(org_id=self.org_id, flow_result_id__in=flow_result_ids)
        poll_stats_ids = poll_stats_ids.values_list("pk", flat=True)

        poll_stats_ids_count = len(poll_stats_ids)

        for batch in chunk_list(poll_stats_ids, 1000):
            PollStats.objects.filter(pk__in=batch).delete()

        logger.info("Deleted %d poll stats for poll #%d on org #%d" % (poll_stats_ids_count, self.pk, self.org_id))

    def delete_poll_results(self):
        from ureport.utils import chunk_list

        results_ids = PollResult.objects.filter(org_id=self.org_id, flow=self.flow_uuid).values_list("pk", flat=True)

        results_ids_count = len(results_ids)

        for batch in chunk_list(results_ids, 1000):
            PollResult.objects.filter(pk__in=batch).delete()

        logger.info("Deleted %d poll results for poll #%d on org #%d" % (results_ids_count, self.pk, self.org_id))

        cache.delete(Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.org_id, self.pk))
        cache.delete(Poll.POLL_RESULTS_LAST_PULL_CACHE_KEY % (self.org.pk, self.flow_uuid))

    def update_questions_results_cache(self):
        for question in self.questions.all():
            question.calculate_polled()
            question.calculate_responded()
            question.calculate_results()
            question.calculate_results(segment=dict(location="State"))
            question.calculate_results(segment=dict(age="Age"))
            question.calculate_results(segment=dict(gender="Gender"))

        self.update_poll_participation_maps_cache()

    def update_questions_results_cache_task(self):
        from ureport.polls.tasks import update_questions_results_cache

        update_questions_results_cache.delay(self.pk)

    def update_question_word_clouds(self):
        for question in self.questions.all().select_related("flow_result"):
            question.generate_word_cloud()

    def update_poll_participation_maps_cache(self):
        top_question = self.get_questions().first()
        if not top_question:
            return

        org = self.org
        states = org.get_segment_org_boundaries({"location": "State"})
        for state in states:
            top_question.calculate_results(segment=dict(location="District", parent=state["osm_id"]))
            districts = org.get_segment_org_boundaries(dict(location="state", parent=state["osm_id"]))
            for district in districts:
                top_question.calculate_results(segment=dict(location="Ward", parent=district["osm_id"]))

    @classmethod
    def pull_poll_results_task(cls, poll):
        from ureport.polls.tasks import pull_refresh

        pull_refresh.apply_async((poll.pk,), queue="sync")

    def pull_refresh_task(self):
        from ureport.utils import datetime_to_json_date

        now = timezone.now()
        cache.set(
            Poll.POLL_PULL_ALL_RESULTS_AFTER_DELETE_FLAG % (self.org_id, self.pk),
            datetime_to_json_date(now.replace(tzinfo=tzone.utc)),
            None,
        )

        Poll.objects.filter(id=self.pk).update(stopped_syncing=False)
        Poll.pull_poll_results_task(self)

    def rebuild_poll_counts_cache(self):
        org_id = self.org_id
        flow = self.flow_uuid

        flow_polls = Poll.objects.filter(org_id=org_id, flow_uuid=flow)
        for flow_poll in flow_polls:
            if flow_poll.is_active and self.stopped_syncing:
                flow_poll.update_questions_results_cache()

            if not flow_poll.stopped_syncing:
                # update the word clouds for questions
                flow_poll.update_question_word_clouds()
                flow_poll.update_questions_results_cache()

    def rebuild_poll_results_counts(self):
        import time

        from ureport.locations.models import Boundary
        from ureport.stats.models import AgeSegment, GenderSegment, PollStats, SchemeSegment

        start = time.time()

        poll_id = self.pk
        org_id = self.org_id
        flow = self.flow_uuid
        poll_year = self.poll_date.year

        if self.stopped_syncing:
            flow_polls = Poll.objects.filter(org_id=org_id, flow_uuid=flow, stopped_syncing=True)
            for flow_poll in flow_polls:
                if flow_poll.is_active:
                    flow_poll.update_questions_results_cache()
                else:
                    logger.info(
                        "Skipping rebuilding results counts for inactive poll #%d on org #%d"
                        % (flow_poll.pk, flow_poll.org_id)
                    )

            logger.info("Poll stopped regenerating new stats for poll #%d on org #%d" % (self.pk, self.org_id))
            return

        r = get_valkey_connection()

        key = Poll.POLL_REBUILD_COUNTS_LOCK % (org_id, flow)

        if r.get(key):
            logger.info("Already rebuilding counts for poll #%d on org #%d" % (poll_id, org_id))

        else:
            with r.lock(key, timeout=Poll.POLL_SYNC_LOCK_TIMEOUT):
                poll_results = PollResult.objects.filter(org_id=org_id, flow=flow).iterator(chunk_size=1000)

                questions = self.questions.all().select_related("flow_result").prefetch_related("response_categories")
                questions_dict = dict()

                if not questions.exists():
                    logger.info("Poll cannot sync without questions for poll #%d on org #%d" % (poll_id, org_id))
                    return

                for qsn in questions:
                    categories = qsn.response_categories.all().select_related("flow_result_category")
                    categories_dict = {elt.flow_result_category.category.lower(): elt.id for elt in categories}
                    flow_categories_dict = {
                        elt.flow_result_category.category.lower(): elt.flow_result_category.id for elt in categories
                    }
                    questions_dict[qsn.flow_result.result_uuid] = dict(
                        id=qsn.id,
                        flow_result_id=qsn.flow_result_id,
                        categories=categories_dict,
                        flow_categories=flow_categories_dict,
                    )

                gender_dict = {elt.gender.lower(): elt.id for elt in GenderSegment.objects.all()}
                age_dict = {elt.min_age: elt.id for elt in AgeSegment.objects.all()}
                scheme_dict = {elt.scheme.lower(): elt.id for elt in SchemeSegment.objects.all()}

                boundaries = Boundary.objects.filter(org_id=org_id)
                location_dict = {elt.osm_id.upper(): elt.id for elt in boundaries}

                logger.info("Results query time for pair %s, %s took %ds" % (org_id, flow, time.time() - start))

                processed_results = 0
                stats_dict = defaultdict(int)

                for result in poll_results:
                    gen_stats = result.generate_poll_stats()
                    for dict_key in gen_stats.keys():
                        stats_dict[dict_key] += gen_stats[dict_key]

                    processed_results += 1

                    if processed_results % 50000 == 0:
                        logger.info(
                            "Rebuild counts progress... build counters dict for pair %s, %s, processed %d in %ds"
                            % (org_id, flow, processed_results, time.time() - start)
                        )

                logger.info(
                    "Rebuild counts progress... build counters dict for pair %s, %s, processed %d in %ds"
                    % (org_id, flow, processed_results, time.time() - start)
                )

                poll_stats_obj_to_insert = []
                for stat_tuple in stats_dict.keys():
                    org_id, ruleset, category, born, gender, state, district, ward, scheme, date = stat_tuple
                    count = stats_dict.get(stat_tuple)
                    stat_kwargs = dict(org_id=org_id, count=count, date=date)

                    if ruleset not in questions_dict:
                        continue

                    question_id = questions_dict[ruleset].get("id")
                    if not question_id:
                        continue

                    flow_result_id = questions_dict[ruleset].get("flow_result_id")
                    if not flow_result_id:
                        continue

                    flow_category_id = questions_dict[ruleset].get("flow_categories", dict()).get(category)

                    gender_id = None
                    if gender:
                        gender_id = gender_dict.get(gender, gender_dict.get("O"))

                    age_id = None
                    if born:
                        age_id = age_dict.get(AgeSegment.get_age_segment_min_age(max(poll_year - int(born), 0)))

                    scheme_id = None
                    if scheme:
                        scheme_id = scheme_dict.get(scheme, None)
                        if scheme_id is None:
                            scheme_obj, created_flag = SchemeSegment.objects.get_or_create(scheme=scheme.lower())
                            scheme_dict[scheme.lower()] = scheme_obj.id

                    location_id = None
                    if ward:
                        location_id = location_dict.get(ward)
                    elif district:
                        location_id = location_dict.get(district)
                    elif state:
                        location_id = location_dict.get(state)

                    if flow_result_id:
                        stat_kwargs["flow_result_id"] = flow_result_id

                    if flow_category_id:
                        stat_kwargs["flow_result_category_id"] = flow_category_id

                    if age_id:
                        stat_kwargs["age_segment_id"] = age_id
                    if gender_id:
                        stat_kwargs["gender_segment_id"] = gender_id
                    if scheme_id:
                        stat_kwargs["scheme_segment_id"] = scheme_id
                    if location_id:
                        stat_kwargs["location_id"] = location_id

                    poll_stats_obj_to_insert.append(PollStats(**stat_kwargs))

                # Delete existing counters and then create new counters
                self.delete_poll_stats()

                PollStats.objects.bulk_create(poll_stats_obj_to_insert, batch_size=1000)

                flow_polls = Poll.objects.filter(org_id=org_id, flow_uuid=flow, stopped_syncing=False)
                for flow_poll in flow_polls:
                    start_update_cache = time.time()

                    # update the word clouds for questions
                    flow_poll.update_question_word_clouds()

                    flow_poll.update_questions_results_cache()
                    logger.info(
                        "Calculated questions results and updated the cache for poll #%d on org #%d in %ds"
                        % (poll_id, org_id, time.time() - start_update_cache)
                    )

                    logger.info(
                        "Poll responses counts for poll #%d on org #%d: %s responses received out of %s participants polled"
                        % (poll_id, org_id, flow_poll.responded_runs(), flow_poll.runs())
                    )

    def get_question_uuids(self):
        question_uuids = FlowResult.objects.filter(org=self.org, flow_uuid=self.flow_uuid).values_list(
            "result_uuid", flat=True
        )
        return question_uuids

    @classmethod
    def get_public_polls(cls, org):
        categories = Category.objects.filter(org=org, is_active=True).only("id")
        return Poll.get_valid_polls(org).filter(published=True, category_id__in=categories)

    @classmethod
    def get_valid_polls(cls, org):
        return (
            Poll.objects.filter(org=org, is_active=True, has_synced=True)
            .exclude(flow_uuid="")
            .prefetch_related(
                Prefetch(
                    "questions",
                    to_attr="prefetched_questions",
                    queryset=PollQuestion.objects.filter(is_active=True)
                    .select_related("flow_result")
                    .prefetch_related(
                        Prefetch(
                            "response_categories",
                            queryset=PollResponseCategory.objects.filter(is_active=True)
                            .exclude(flow_result_category__category__icontains="no response")
                            .only("id", "question_id"),
                            to_attr="prefetched_response_categories",
                        )
                    )
                    .order_by("-priority", "id"),
                ),
                Prefetch("tags", queryset=Tag.objects.filter(is_active=True, org=org).only("name", "id")),
                Prefetch("category", queryset=Category.objects.filter(is_active=True, org=org).only("name")),
            )
        )

    @classmethod
    def get_main_poll(cls, org):
        cached_value = cache.get(Poll.ORG_MAIN_POLL_ID % org.id, None)
        main_poll = None
        if cached_value:
            main_poll = (
                Poll.objects.filter(is_active=True, published=True, id=cached_value, org=org)
                .prefetch_related(
                    Prefetch(
                        "questions",
                        to_attr="prefetched_questions",
                        queryset=PollQuestion.objects.filter(poll_id=cached_value, is_active=True)
                        .select_related("flow_result")
                        .prefetch_related(
                            Prefetch(
                                "response_categories",
                                queryset=PollResponseCategory.objects.filter(is_active=True)
                                .exclude(flow_result_category__category__icontains="no response")
                                .only("id", "question_id"),
                                to_attr="prefetched_response_categories",
                            )
                        )
                        .order_by("-priority", "id"),
                    ),
                    Prefetch("tags", queryset=Tag.objects.filter(is_active=True, org=org).only("name", "id")),
                    Prefetch("category", queryset=Category.objects.filter(is_active=True, org=org).only("name")),
                )
                .first()
            )

        if main_poll:
            return main_poll
        return Poll.find_main_poll(org)

    @classmethod
    def find_main_poll(cls, org):
        poll_with_questions = (
            PollQuestion.objects.filter(is_active=True, poll__org=org).only("poll_id").values_list("poll_id", flat=True)
        )

        polls = (
            Poll.get_public_polls(org=org).filter(pk__in=poll_with_questions, published=True).order_by("-created_on")
        )

        main_poll = polls.filter(is_featured=True).first()

        if not main_poll:
            main_poll = polls.first()

        if main_poll:
            cache.set(Poll.ORG_MAIN_POLL_ID % org.id, main_poll.pk, None)
        return main_poll

    @classmethod
    def get_other_polls(cls, org):
        main_poll = Poll.get_main_poll(org)

        exclude_polls = []
        if main_poll:
            exclude_polls.append(main_poll.pk)

        other_polls = (
            Poll.get_valid_polls(org=org)
            .exclude(pk__in=exclude_polls)
            .exclude(is_active=False)
            .exclude(flow_uuid="")
            .order_by("-created_on")
        )

        return other_polls

    @classmethod
    def get_recent_polls(cls, org):
        now = timezone.now()
        recent_window = now - timedelta(days=45)
        main_poll = Poll.get_main_poll(org)

        recent_other_polls = Poll.get_valid_polls(org)
        if main_poll:
            recent_other_polls = recent_other_polls.exclude(pk=main_poll.pk)
        recent_other_polls = recent_other_polls.exclude(created_on__lte=recent_window).order_by("-created_on")

        return recent_other_polls

    def get_flow(self):
        """
        Returns the underlying flow for this poll
        """
        flows_dict = self.org.get_flows(backend=self.backend)
        return flows_dict.get(self.flow_uuid, None)

    def get_flow_date(self):
        flow = self.get_flow()
        return flow.get("created_on", None) if flow else None

    def update_or_create_questions(self, user=None):
        if not user:
            user = get_user_model().objects.get(pk=-1)

        org = self.org
        backend = org.get_backend(backend_slug=self.backend.slug)

        backend.update_poll_questions(org, self, user)

    def response_percentage(self):
        """
        The response rate for this flow
        """
        top_question = self.get_top_question()
        if top_question:
            return top_question.get_response_percentage()
        return "---"

    def get_featured_responses(self):
        return self.featured_responses.filter(is_active=True).order_by("-created_on")

    def get_first_question(self):
        questions = self.get_questions()

        for question in questions:
            if not question.is_open_ended():
                return question

    def get_questions(self):
        if hasattr(self, "prefetched_questions"):
            return self.prefetched_questions

        return (
            self.questions.filter(is_active=True)
            .select_related("flow_result")
            .prefetch_related(
                Prefetch(
                    "response_categories",
                    queryset=PollResponseCategory.objects.filter(is_active=True)
                    .exclude(flow_result_category__category__icontains="no response")
                    .only("id", "question_id"),
                    to_attr="prefetched_response_categories",
                )
            )
            .order_by("-priority", "pk")
        )

    def get_top_question(self):
        questions = self.get_questions()
        if questions:
            return questions[0]
        return None

    def get_images(self):
        return self.images.filter(is_active=True).order_by("pk")

    def runs(self):
        top_question = self.get_top_question()
        if top_question:
            return top_question.get_polled()
        return "----"

    def responded_runs(self):
        top_question = self.get_top_question()
        if top_question:
            return top_question.get_responded()
        return "---"

    def get_featured_images(self):
        return self.images.filter(is_active=True).exclude(image="").order_by("-created_on")

    def get_category_image(self):
        if self.category_image:
            return self.category_image.image
        elif self.category.is_active:
            return self.category.get_first_image()

    @classmethod
    def update_or_create_questions_task(cls, records):
        from .tasks import update_or_create_questions

        record_ids = []

        for record in records:
            record_ids.append(record.id)

        if record_ids:
            update_or_create_questions.delay(record_ids)

    def __str__(self):
        return self.title

    class Meta:
        indexes = [
            models.Index(fields=["org", "published", "id"], name="polls_poll_org_pblshd_id_idx"),
        ]


@six.python_2_unicode_compatible
class PollImage(SmartModel):
    name = models.CharField(max_length=64, help_text=_("The name to describe this image"))

    poll = models.ForeignKey(
        Poll, on_delete=models.PROTECT, related_name="images", help_text=_("The poll to associate to")
    )

    image = models.ImageField(upload_to="polls", help_text=_("The image file to use"))

    def __str__(self):
        return "%s - %s" % (self.poll, self.name)


@six.python_2_unicode_compatible
class FeaturedResponse(SmartModel):
    """
    A highlighted response for a poll and location.
    """

    poll = models.ForeignKey(
        Poll, on_delete=models.PROTECT, related_name="featured_responses", help_text=_("The poll for this response")
    )

    location = models.CharField(max_length=255, help_text=_("The location for this response"))

    reporter = models.CharField(
        max_length=255, null=True, blank=True, help_text=_("The name of the sender of the message")
    )

    message = models.CharField(max_length=255, help_text=_("The featured response message"))

    def __str__(self):
        return "%s - %s - %s" % (self.poll, self.location, self.message)


@six.python_2_unicode_compatible
class PollQuestion(SmartModel):
    """
    Represents a single question that was asked in a poll, these questions tie 1-1 to
    the RuleSets in a flow.
    """

    POLL_QUESTION_RESPONDED_CACHE_KEY = "org:%d:poll:%d:question_responded:%d"
    POLL_QUESTION_POLLED_CACHE_KEY = "org:%d:poll:%d:question_polled:%d"
    POLL_QUESTION_RESULTS_CACHE_KEY = "org:%d:poll:%d:question_results:%d"
    POLL_QUESTION_RESULTS_CACHE_TIMEOUT = 60 * 12

    QUESTION_COLOR_CHOICES = (
        (None, "-----"),
        ("D1", _("Dark 1 background and White text")),
        ("L1", _("Light 1 background and Black text")),
        ("D2", _("Dark 2 background and White text")),
        ("D3", _("Dark 3 background and Black text")),
    )

    QUESTION_COLOR_CHOICE_BLOCK_CSS_CLASSES = {
        "D1": "bg-dark1 text-white",
        "L1": "bg-light1 text-black",
        "D2": "bg-dark2 text-white",
        "D3": "bg-dark3 text-black",
    }

    QUESTION_COLOR_CHOICE_BG_COLORS = {
        "D1": ("dark1_color", "#439932"),
        "L1": ("light1_color", "#FFD100"),
        "D2": ("dark2_color", "#1751af"),
        "D3": ("dark3_color", "#5eb3e0"),
    }

    QUESTION_COLOR_CHOICE_BORDER_COLORS = {
        "D1": "white",
        "L1": "black",
        "D2": "white",
        "D3": "white",
    }

    QUESTION_HIDDEN_CHARTS_CHOICES = (
        (None, _("Show Age, Gender and Location charts")),
        ("A", _("Hide Age chart ONLY")),
        ("G", _("Hide Gender chart ONLY")),
        ("L", _("Hide Location chart ONLY")),
        ("AG", _("Hide Age and Gender charts")),
        ("AL", _("Hide Age and Location charts")),
        ("GL", _("Hide Gender and Location charts")),
        ("AGL", _("Hide Age, Gender and Location charts")),
    )

    poll = models.ForeignKey(
        Poll, on_delete=models.PROTECT, related_name="questions", help_text=_("The poll this question is part of")
    )
    title = models.CharField(max_length=255, help_text=_("The title of this question"))

    # TODO: remove field
    ruleset_uuid = models.CharField(max_length=36, help_text=_("The RuleSet this question is based on"))

    # TODO: remove field
    ruleset_type = models.CharField(max_length=32, default="wait_message")

    # TODO: remove field
    ruleset_label = models.CharField(
        max_length=255, null=True, blank=True, help_text=_("The label of the ruleset on RapidPro")
    )

    priority = models.IntegerField(
        default=0, null=True, blank=True, help_text=_("The priority number for this question on the poll")
    )

    flow_result = models.ForeignKey(FlowResult, on_delete=models.PROTECT)

    color_choice = models.CharField(max_length=2, choices=QUESTION_COLOR_CHOICES, null=True, blank=True)

    hidden_charts = models.CharField(max_length=3, choices=QUESTION_HIDDEN_CHARTS_CHOICES, null=True, blank=True)

    def show_age(self):
        return self.hidden_charts is None or "A" not in self.hidden_charts

    def show_gender(self):
        return self.hidden_charts is None or "G" not in self.hidden_charts

    def show_locations(self):
        return self.hidden_charts is None or "L" not in self.hidden_charts

    def hide_all_chart_pills(self):
        return "AGL" == self.hidden_charts

    def get_last_pill(self):
        if self.hidden_charts is None or "L" not in self.hidden_charts:
            return "locations"
        if self.hidden_charts is None or "G" not in self.hidden_charts:
            return "gender"
        if self.hidden_charts is None or "A" not in self.hidden_charts:
            return "age"
        return "all"

    def get_color_choice_css(self):
        return self.QUESTION_COLOR_CHOICE_BLOCK_CSS_CLASSES.get(self.color_choice, "")

    def get_border_color_choice(self):
        return self.QUESTION_COLOR_CHOICE_BORDER_COLORS.get(self.color_choice, "")

    def get_bg_color_choice(self):
        org = self.poll.org
        color_tuple = self.QUESTION_COLOR_CHOICE_BG_COLORS.get(self.color_choice, ("", ""))
        return org.get_config(color_tuple[0]) or color_tuple[1]

    @classmethod
    def update_or_create(cls, user, poll, ruleset_label, uuid, ruleset_type):
        flow_result = FlowResult.update_or_create(poll.org, poll.flow_uuid, uuid, ruleset_label)
        question = cls.objects.filter(ruleset_uuid=uuid, poll=poll).first()

        if question:
            question.ruleset_type = ruleset_type
            question.ruleset_label = ruleset_label
            question.flow_result = flow_result
            question.save(update_fields=("ruleset_type", "ruleset_label", "flow_result"))
        else:
            question = PollQuestion.objects.create(
                poll=poll,
                ruleset_uuid=uuid,
                title=ruleset_label,
                ruleset_type=ruleset_type,
                ruleset_label=ruleset_label,
                flow_result=flow_result,
                is_active=False,
                created_by=user,
                modified_by=user,
            )
        return question

    def get_public_categories(self):
        return (
            self.response_categories.filter(is_active=True)
            .annotate(lower_category=Lower("category"))
            .exclude(lower_category__in=PollResponseCategory.IGNORED_CATEGORY_RULES)
            .select_related("flow_result_category")
            .order_by("pk")
        )

    def get_results(self, segment=None):
        key = PollQuestion.POLL_QUESTION_RESULTS_CACHE_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
        if segment:
            key += ":" + slugify(six.text_type(json.dumps(segment)))

        cached_value = cache.get(key, None)
        if cached_value:
            return cached_value["results"]

        if getattr(settings, "IS_PROD", False):
            if not segment:
                logger.error("Question get results without segment cache missed", exc_info=True, extra={"stack": True})
            else:
                logger.error("Question get results cache missed", exc_info=True, extra={"stack": True})

            if segment and "location" in segment and segment.get("location").lower() == "state":
                logger.error(
                    "Question get results with state segment cache missed", exc_info=True, extra={"stack": True}
                )

        return self.calculate_results(segment=segment)

    def generate_word_cloud(self):
        from ureport.stats.models import PollWordCloud

        org = self.poll.org
        open_ended = self.is_open_ended()

        if open_ended:
            custom_sql = """
                      SELECT w.label, count(*) AS count FROM (SELECT regexp_split_to_table(LOWER(text), E'[^[:alnum:]_]') AS label FROM polls_pollresult WHERE polls_pollresult.org_id = %d AND polls_pollresult.flow = '%s' AND polls_pollresult.ruleset = '%s' AND polls_pollresult.text IS NOT NULL AND polls_pollresult.text NOT ILIKE '%s') w group by w.label;
                      """ % (
                org.id,
                self.poll.flow_uuid,
                self.flow_result.result_uuid,
                "http%",
            )
            with connection.cursor() as cursor:
                cursor.execute(custom_sql)
                from ureport.utils import get_dict_from_cursor

                unclean_categories = get_dict_from_cursor(cursor)

            categories = {}
            for category in unclean_categories:
                categories[category["label"]] = int(category["count"])

            poll_word_cloud = PollWordCloud.get_question_poll_cloud(org, self)
            if not poll_word_cloud:
                poll_word_cloud = PollWordCloud.objects.create(org=org, flow_result=self.flow_result)

            poll_word_cloud.words = categories
            poll_word_cloud.save()

    def calculate_results(self, segment=None):
        from stop_words import safe_get_stop_words

        from ureport.stats.models import AgeSegment, GenderSegment, PollStats, PollWordCloud

        org = self.poll.org
        open_ended = self.is_open_ended()
        responded = self.calculate_responded()
        polled = self.calculate_polled()
        org_gender_labels = org.get_gender_labels()

        results = []

        if open_ended and not segment:
            poll_word_cloud = PollWordCloud.get_question_poll_cloud(org, self)

            unclean_categories = []
            if poll_word_cloud:
                unclean_categories = [dict(label=key, count=val) for key, val in poll_word_cloud.words.items()]

            ureport_languages = getattr(settings, "LANGUAGES", [("en", "English")])

            org_languages = [lang[1].lower() for lang in ureport_languages if lang[0] == org.language]

            if "english" not in org_languages:
                org_languages.append("english")

            ignore_words = [elt.strip().lower() for elt in org.get_config("common.ignore_words", "").split(",")]
            for lang in org_languages:
                ignore_words += safe_get_stop_words(lang)

            categories = []

            # sort by count, then alphabetically
            unclean_categories = sorted(unclean_categories, key=lambda c: (-c["count"], c["label"]))

            for category in unclean_categories:
                if len(category["label"]) > 1 and category["label"] not in ignore_words and len(categories) < 100:
                    categories.append(dict(label=strip_tags(category["label"]), count=int(category["count"])))

            results.append(dict(open_ended=open_ended, set=responded, unset=polled - responded, categories=categories))

        else:
            categories_qs = (
                self.response_categories.filter(is_active=True).select_related("flow_result_category").order_by("pk")
            )

            if segment:
                location_part = segment.get("location", "").lower()
                age_part = segment.get("age", "").lower()
                gender_part = segment.get("gender", "").lower()

                if location_part in ["state", "district", "ward"]:
                    location_boundaries = org.get_segment_org_boundaries(segment)

                    for boundary in location_boundaries:
                        categories = []
                        osm_id = boundary.get("osm_id").upper()

                        categories_results = (
                            PollStats.get_question_stats(org.id, self)
                            .filter(
                                Q(location__id=boundary["id"])
                                | Q(location__parent__id=boundary["id"])
                                | Q(location__parent__parent__id=boundary["id"])
                            )
                            .exclude(flow_result_category=None)
                            .values("flow_result_category__category")
                            .annotate(label=F("flow_result_category__category"), count=Sum("count"))
                            .values("label", "count")
                        )
                        categories_results_dict = {elt["label"].lower(): elt["count"] for elt in categories_results}

                        unset_count_stats = (
                            PollStats.get_question_stats(org.id, self)
                            .filter(flow_result_category=None)
                            .filter(
                                Q(location__id=boundary["id"])
                                | Q(location__parent__id=boundary["id"])
                                | Q(location__parent__parent__id=boundary["id"])
                            )
                            .aggregate(Sum("count"))
                        )
                        unset_count = unset_count_stats.get("count__sum", 0) or 0

                        for category_obj in categories_qs:
                            key = category_obj.flow_result_category.category.lower()
                            categorie_label = (
                                category_obj.category_displayed or category_obj.flow_result_category.category
                            )
                            if key not in PollResponseCategory.IGNORED_CATEGORY_RULES:
                                category_count = categories_results_dict.get(key, 0)
                                categories.append(dict(count=category_count, label=strip_tags(categorie_label)))

                        set_count = sum([elt["count"] for elt in categories])

                        results.append(
                            dict(
                                open_ended=open_ended,
                                set=set_count,
                                unset=unset_count,
                                boundary=osm_id,
                                label=strip_tags(boundary.get("name")),
                                categories=categories,
                            )
                        )
                elif age_part:
                    ages = AgeSegment.objects.all().values("id", "min_age", "max_age")
                    results = []
                    for age in ages:
                        if age["min_age"] == 0:
                            data_key = "0-14"
                        elif age["min_age"] == 15:
                            data_key = "15-19"
                        elif age["min_age"] == 20:
                            data_key = "20-24"
                        elif age["min_age"] == 25:
                            data_key = "25-30"
                        elif age["min_age"] == 31:
                            data_key = "31-34"
                        elif age["min_age"] == 35:
                            data_key = "35+"

                        categories_results = (
                            PollStats.get_question_stats(org.id, self)
                            .filter(age_segment_id=age["id"])
                            .exclude(flow_result_category=None)
                            .values("flow_result_category__category")
                            .annotate(label=F("flow_result_category__category"), count=Sum("count"))
                            .values("label", "count")
                        )
                        categories_results_dict = {elt["label"].lower(): elt["count"] for elt in categories_results}

                        unset_count_stats = (
                            PollStats.get_question_stats(org.id, self)
                            .filter(flow_result_category=None, age_segment_id=age["id"])
                            .aggregate(Sum("count"))
                        )
                        unset_count = unset_count_stats.get("count__sum", 0) or 0

                        categories = []
                        for category_obj in categories_qs:
                            key = category_obj.flow_result_category.category.lower()
                            categorie_label = (
                                category_obj.category_displayed or category_obj.flow_result_category.category
                            )
                            if key not in PollResponseCategory.IGNORED_CATEGORY_RULES:
                                category_count = categories_results_dict.get(key, 0)
                                categories.append(dict(count=category_count, label=strip_tags(categorie_label)))

                        set_count = sum([elt["count"] for elt in categories])

                        results.append(dict(set=set_count, unset=unset_count, label=data_key, categories=categories))

                    results = sorted(results, key=lambda i: i["label"])

                elif gender_part:
                    genders = GenderSegment.objects.all()
                    if not org.get_config("common.has_extra_gender"):
                        genders = genders.exclude(gender="O")

                    genders = genders.values("gender", "id")

                    results = []
                    for gender in genders:
                        categories_results = (
                            PollStats.get_question_stats(org.id, self)
                            .filter(gender_segment_id=gender["id"])
                            .exclude(flow_result_category=None)
                            .values("flow_result_category__category")
                            .annotate(label=F("flow_result_category__category"), count=Sum("count"))
                            .values("label", "count")
                        )
                        categories_results_dict = {elt["label"].lower(): elt["count"] for elt in categories_results}
                        categories = []

                        unset_count_stats = (
                            PollStats.get_question_stats(org.id, self)
                            .filter(flow_result_category=None, gender_segment_id=gender["id"])
                            .aggregate(Sum("count"))
                        )
                        unset_count = unset_count_stats.get("count__sum", 0) or 0

                        for category_obj in categories_qs:
                            key = category_obj.flow_result_category.category.lower()
                            categorie_label = (
                                category_obj.category_displayed or category_obj.flow_result_category.category
                            )
                            if key not in PollResponseCategory.IGNORED_CATEGORY_RULES:
                                category_count = categories_results_dict.get(key, 0)
                                categories.append(dict(count=category_count, label=strip_tags(categorie_label)))

                        set_count = sum([elt["count"] for elt in categories])
                        results.append(
                            dict(
                                set=set_count,
                                unset=unset_count,
                                label=org_gender_labels.get(gender["gender"]),
                                categories=categories,
                            )
                        )

            else:
                categories_results = (
                    PollStats.get_question_stats(org.id, self)
                    .exclude(flow_result_category=None)
                    .values("flow_result_category__category")
                    .annotate(label=F("flow_result_category__category"), count=Sum("count"))
                    .values("label", "count")
                )
                categories_results_dict = {elt["label"].lower(): elt["count"] for elt in categories_results}
                categories = []

                for category_obj in categories_qs:
                    key = category_obj.flow_result_category.category.lower()
                    categorie_label = category_obj.category_displayed or category_obj.flow_result_category.category
                    if key not in PollResponseCategory.IGNORED_CATEGORY_RULES:
                        category_count = categories_results_dict.get(key, 0)
                        categories.append(dict(count=category_count, label=strip_tags(categorie_label)))

                results.append(
                    dict(open_ended=open_ended, set=responded, unset=polled - responded, categories=categories)
                )

        key = PollQuestion.POLL_QUESTION_RESULTS_CACHE_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
        if segment:
            key += ":" + slugify(six.text_type(json.dumps(segment)))

        cache.set(key, {"results": results}, None)

        return results

    def get_total_summary_data(self):
        cached_results = self.get_results()
        if cached_results:
            return cached_results[0]
        return dict()

    def is_open_ended(self):
        if hasattr(self, "prefetched_response_categories"):
            return len(self.prefetched_response_categories) == 1

        return (
            self.response_categories.filter(is_active=True)
            .exclude(flow_result_category__category__icontains="no response")
            .count()
            == 1
        )

    def get_responded(self):
        key = PollQuestion.POLL_QUESTION_RESPONDED_CACHE_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
        cached_value = cache.get(key, None)
        if cached_value:
            return cached_value["results"]
        if getattr(settings, "IS_PROD", False):
            logger.error("Question get responded cache missed", exc_info=True, extra={"stack": True})

        return self.calculate_responded()

    def calculate_responded(self):
        from ureport.stats.models import PollStats

        key = PollQuestion.POLL_QUESTION_RESPONDED_CACHE_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
        responded_stats = (
            PollStats.get_question_stats(self.poll.org_id, question=self)
            .exclude(flow_result_category=None)
            .aggregate(Sum("count"))
        )
        results = responded_stats.get("count__sum", 0) or 0
        cache.set(key, {"results": results}, None)
        return results

    def get_polled(self):
        key = PollQuestion.POLL_QUESTION_POLLED_CACHE_KEY % (self.poll.org.pk, self.poll.pk, self.pk)
        cached_value = cache.get(key, None)
        if cached_value:
            return cached_value["results"]
        if getattr(settings, "IS_PROD", False):
            logger.error("Question get responded cache missed", exc_info=True, extra={"stack": True})

        return self.calculate_polled()

    def calculate_polled(self):
        from ureport.stats.models import PollStats

        key = PollQuestion.POLL_QUESTION_POLLED_CACHE_KEY % (self.poll.org.pk, self.poll.pk, self.pk)

        polled_stats = PollStats.get_question_stats(self.poll.org_id, question=self).aggregate(Sum("count"))
        results = polled_stats.get("count__sum", 0) or 0

        cache.set(key, {"results": results}, None)
        return results

    def get_response_percentage(self):
        polled = self.get_polled()
        responded = self.get_responded()
        if polled and responded:
            percentage = int(round((float(responded) * 100.0) / float(polled)))
            return "%s" % six.text_type(percentage) + "%"
        return "___"

    def get_gender_stats(self):
        return self.get_results(segment=dict(gender="gender"))

    def get_age_stats(self):
        return self.get_results(segment=dict(age="age"))

    def get_location_stats(self):
        return self.get_results(segment=dict(location="state"))

    def get_words(self):
        words = self.get_total_summary_data().get("categories", [])
        org = self.poll.org
        ignore_words = [elt.strip().lower() for elt in org.get_config("common.ignore_words", "").split(",")]

        return [elt for elt in words if elt["label"].lower() not in ignore_words]

    def __str__(self):
        return self.title

    class Meta:
        indexes = [
            models.Index(fields=["poll", "is_active", "flow_result"], name="polls_qstn_poll_actv_fl_rs_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["poll", "flow_result"], name="polls_pollquestion_poll_id_flow_result_id_608a2446_uniq"
            ),
            models.UniqueConstraint(
                fields=["poll", "ruleset_uuid"], name="polls_pollquestion_poll_id_4202706c8106f06_uniq"
            ),
        ]


class PollResponseCategory(models.Model):
    IGNORED_CATEGORY_RULES = ["other", "no response"]

    question = models.ForeignKey(PollQuestion, on_delete=models.PROTECT, related_name="response_categories")

    # TODO: remove field
    rule_uuid = models.CharField(max_length=36, help_text=_("The Rule this response category is based on"))

    # TODO: remove field
    category = models.TextField(null=True)

    category_displayed = models.TextField(null=True)

    is_active = models.BooleanField(default=True)

    flow_result_category = models.ForeignKey(FlowResultCategory, on_delete=models.PROTECT)

    @classmethod
    def update_or_create(cls, question, rule_uuid, category):
        flow_result_category = FlowResultCategory.update_or_create(question.flow_result, category)

        existing = cls.objects.filter(question=question)
        if rule_uuid is not None:
            existing = existing.filter(rule_uuid=rule_uuid)
        else:
            existing = existing.filter(category=category)
            rule_uuid = uuid.uuid4()

        if existing:
            existing.update(category=category, is_active=True, flow_result_category=flow_result_category)
        else:
            existing = cls.objects.create(
                question=question,
                rule_uuid=rule_uuid,
                category=category,
                category_displayed=category,
                flow_result_category=flow_result_category,
                is_active=True,
            )
        return existing

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["question", "rule_uuid"], name="polls_pollresponsecategory_question_id_3a161715511bd77d_uniq"
            ),
            models.UniqueConstraint(
                fields=["question", "flow_result_category"],
                name="polls_pollresponsecatego_question_id_flow_result__4db1cb7e_uniq",
            ),
        ]


class PollResult(models.Model):
    id = models.BigAutoField(auto_created=True, primary_key=True, verbose_name="ID")

    org = models.ForeignKey(Org, on_delete=models.PROTECT, related_name="poll_results", db_index=False)

    flow = models.CharField(max_length=36)

    ruleset = models.CharField(max_length=36)

    contact = models.CharField(max_length=36)

    date = models.DateTimeField(null=True)

    completed = models.BooleanField()

    category = models.CharField(max_length=255, null=True)

    text = models.TextField(null=True, max_length=1600)

    state = models.CharField(max_length=255, null=True)

    district = models.CharField(max_length=255, null=True)

    ward = models.CharField(max_length=255, null=True)

    gender = models.CharField(max_length=1, null=True)

    born = models.IntegerField(null=True)

    scheme = models.CharField(max_length=16, null=True)

    def get_result_tuple(self):
        if not self.org_id or not self.flow or not self.ruleset:
            return ()

        ruleset = ""
        category = ""
        state = ""
        district = ""
        ward = ""
        born = ""
        gender = ""
        scheme = ""
        text = ""
        date = None
        if self.date:
            date = self.date.replace(hour=0, minute=0, second=0, microsecond=0)

        if self.text and self.text != "None":
            text = self.text

        if self.ruleset:
            ruleset = self.ruleset.lower()

        if (
            self.category
            and self.category.lower() not in PollResponseCategory.IGNORED_CATEGORY_RULES
            or (
                self.category is not None
                and self.category.lower() not in PollResponseCategory.IGNORED_CATEGORY_RULES
                and text
            )
        ):
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

        if self.scheme:
            scheme = self.scheme.lower()

        return (self.org_id, ruleset, category, born, gender, state, district, ward, scheme, date)

    def generate_poll_stats(self):
        generated_stats = dict()

        result_tuple = self.get_result_tuple()
        if result_tuple:
            generated_stats[result_tuple] = 1

        return generated_stats

    class Meta:
        indexes = [
            models.Index(fields=["org", "flow"], name="polls_pollresult_org_flow_idx"),
            models.Index(fields=["org", "flow", "ruleset", "text"], name="polls_rslt_org_flw_rst_txt_idx"),
        ]
