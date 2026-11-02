# -*- coding: utf-8 -*-

import logging
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from ureport.polls.models import Poll, PollQuestion, PollResult
from ureport.polls.sync import queue_full_repulls
from ureport.stats.models import PollStatsCounter

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Lists the flows that have both retired polls and polls still syncing them. A poll set up on a retired flow "
        "used to resume the flow's sync rather than pull all of its results again, leaving counts that miss the "
        "results the flow was retired with. With --zeroed, lists instead the retired flows that no poll syncs, whose "
        "results were deleted and whose counts are all zero, which a retirement on missing results may have left "
        "empty - including any that genuinely had no responses. With --poll, lists the flows of the given polls "
        "instead. With --check, asks the backend how many runs each flow has: a flow with none genuinely has no "
        "responses, while one with runs but no results stored may have lost them, or its contacts may never have "
        "answered, which only pulling it again settles. With --refresh, pulls all of each flow's results "
        "again, walking the archives once for all the flows of an org, after which a flow too old to keep syncing is "
        "retired again - with --check, only the flows the backend reports runs for."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", type=int, help="Only the flows of the org with this id")
        parser.add_argument(
            "--zeroed", action="store_true", help="List the retired flows whose counts are all zero instead"
        )
        parser.add_argument(
            "--poll", type=int, action="append", dest="poll_ids", metavar="ID", help="The flow of this poll instead"
        )
        parser.add_argument("--check", action="store_true", help="Report how many runs the backend has for each flow")
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Pull all of each flow's results again, with --check only those of the flows with runs",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Only this many flows, to spread the pulls over several runs - with --check and --refresh, this many "
            "of the flows with runs",
        )

    def handle(self, *args, **options):
        if options["poll_ids"]:
            polls = self.get_given_polls(options["poll_ids"])
        elif options["zeroed"]:
            polls = self.get_zeroed_polls()
        else:
            polls = self.get_reused_polls()

        if options["org"]:
            polls = polls.filter(org_id=options["org"])

        # the org and backend are what the check and the re-pull reach the backend with
        polls = polls.select_related("org", "backend")

        # with --check and --refresh the limit is on the flows pulled, as the flows without runs stay listed and would
        # otherwise fill every later run's limit
        pull_with_runs = options["check"] and options["refresh"]
        list_limit = None if pull_with_runs else options["limit"]

        # one poll per flow is enough to pull it again, as the re-pull covers every poll on it
        seen = set()
        flow_polls = []
        for poll in polls:
            if (poll.org_id, poll.flow_uuid) in seen:
                continue
            if list_limit is not None and len(seen) >= list_limit:
                break
            seen.add((poll.org_id, poll.flow_uuid))
            flow_polls.append(poll)

        flow_runs = self.fetch_flow_runs(flow_polls) if options["check"] else {}

        unpulled = 0
        for poll in flow_polls:
            line = "org #%d flow %s (poll #%d %s)" % (poll.org_id, poll.flow_uuid, poll.pk, poll.title)

            if options["check"]:
                runs = flow_runs[poll.pk]
                stored = PollResult.objects.filter(org_id=poll.org_id, flow=poll.flow_uuid).exists()
                line += ": %s, %s" % (self.describe_runs(runs), "results stored" if stored else "no results stored")

                # runs the backend has but none of which came back are the ones worth pulling again
                if self.has_runs(runs) and not stored:
                    unpulled += 1
                    line = self.style.WARNING(line)

            self.stdout.write(line)

        if options["check"]:
            self.stdout.write(
                "Found %d flows, %d with runs in the backend but no results stored" % (len(seen), unpulled)
            )

            # a flow the backend reports no runs for, or can't tell about, has nothing a pull would bring back
            flow_polls = [poll for poll in flow_polls if self.has_runs(flow_runs[poll.pk])]

            if pull_with_runs and options["limit"] is not None:
                flow_polls = flow_polls[: options["limit"]]

        if options["refresh"]:
            queue_full_repulls(flow_polls)
            self.stdout.write("Scheduled a full pull of %d flows" % len(flow_polls))
        elif not options["check"]:
            self.stdout.write("Found %d flows" % len(seen))

    def fetch_flow_runs(self, polls):
        """
        The runs the backend has for each poll's flow, by poll id: None if the backend can't tell, or couldn't be
        asked, and empty if it doesn't have the flow. One call per org and backend, for all of its flows.
        """
        flows = defaultdict(list)
        for poll in polls:
            flows[(poll.org, poll.backend.slug)].append(poll)

        flow_runs = {}
        for (org, backend_slug), org_polls in flows.items():
            try:
                backend = org.get_backend(backend_slug=backend_slug)
                runs = backend.fetch_flow_runs(org, [poll.flow_uuid for poll in org_polls])
            except Exception:
                logger.exception("Error fetching the flows of org #%d from %s", org.pk, backend_slug)
                self.stderr.write("Couldn't fetch the flows of org #%d from %s" % (org.pk, backend_slug))
                runs = None

            for poll in org_polls:
                flow_runs[poll.pk] = runs.get(poll.flow_uuid, {}) if runs is not None else None

        return flow_runs

    @staticmethod
    def has_runs(runs):
        return bool(runs and runs["runs"])

    @staticmethod
    def describe_runs(runs):
        if runs is None:
            return "runs unknown"
        if not runs:
            return "not found in the backend"
        if not runs["runs"]:
            return "no runs in the backend"
        return "%d runs in the backend (%d completed)" % (runs["runs"], runs["completed"])

    def get_given_polls(self, poll_ids):
        return (
            Poll.objects.filter(id__in=poll_ids, is_active=True)
            .exclude(flow_uuid="")
            .order_by("org_id", "flow_uuid", "-created_on")
        )

    def get_reused_polls(self):
        retired = Poll.objects.filter(org_id=OuterRef("org_id"), flow_uuid=OuterRef("flow_uuid"), stopped_syncing=True)

        return (
            Poll.objects.filter(is_active=True, stopped_syncing=False)
            .exclude(flow_uuid="")
            .filter(Exists(retired))
            .order_by("org_id", "flow_uuid", "-created_on")
        )

    def get_zeroed_polls(self):
        syncing = Poll.objects.filter(
            org_id=OuterRef("org_id"), flow_uuid=OuterRef("flow_uuid"), is_active=True, stopped_syncing=False
        )
        results = PollResult.objects.filter(org_id=OuterRef("org_id"), flow=OuterRef("flow_uuid"))
        questions = PollQuestion.objects.filter(poll__org_id=OuterRef("org_id"), poll__flow_uuid=OuterRef("flow_uuid"))

        # the counts are kept per flow result, so any question of any poll on the flow with a count means it has some
        counted_questions = questions.filter(
            Exists(
                PollStatsCounter.objects.filter(
                    org_id=OuterRef("poll__org_id"), flow_result_id=OuterRef("flow_result_id"), count__gt=0
                )
            )
        )

        # the poll pulled again is one that can sync, i.e. an active one, as get_job_poll requires
        return (
            Poll.objects.filter(is_active=True, stopped_syncing=True)
            .exclude(flow_uuid="")
            .filter(Exists(questions))
            .exclude(Exists(syncing))
            .exclude(Exists(results))
            .exclude(Exists(counted_questions))
            .order_by("org_id", "flow_uuid", "-created_on")
        )
