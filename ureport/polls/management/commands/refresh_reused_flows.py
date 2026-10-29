# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from ureport.polls.models import Poll, PollQuestion, PollResult
from ureport.stats.models import PollStatsCounter


class Command(BaseCommand):
    help = (
        "Lists the flows that have both retired polls and polls still syncing them. A poll set up on a retired flow "
        "used to resume the flow's sync rather than pull all of its results again, leaving counts that miss the "
        "results the flow was retired with. With --zeroed, lists instead the retired flows that no poll syncs, whose "
        "results were deleted and whose counts are all zero, which a retirement on missing results may have left "
        "empty - including any that genuinely had no responses. With --refresh, pulls all of each flow's results "
        "again, archives included, after which the flow is retired again."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", type=int, help="Only the flows of the org with this id")
        parser.add_argument(
            "--zeroed", action="store_true", help="List the retired flows whose counts are all zero instead"
        )
        parser.add_argument("--refresh", action="store_true", help="Pull all of each flow's results again")
        parser.add_argument("--limit", type=int, help="Only this many flows, to spread the pulls over several runs")

    def handle(self, *args, **options):
        polls = self.get_zeroed_polls() if options["zeroed"] else self.get_reused_polls()
        if options["org"]:
            polls = polls.filter(org_id=options["org"])

        # one poll per flow is enough to pull it again, as the re-pull covers every poll on it
        seen = set()
        for poll in polls:
            if (poll.org_id, poll.flow_uuid) in seen:
                continue
            if options["limit"] is not None and len(seen) >= options["limit"]:
                break
            seen.add((poll.org_id, poll.flow_uuid))

            self.stdout.write("org #%d flow %s (poll #%d %s)" % (poll.org_id, poll.flow_uuid, poll.pk, poll.title))

            if options["refresh"]:
                poll.pull_refresh_task()

        action = "Scheduled a full pull of" if options["refresh"] else "Found"
        self.stdout.write("%s %d flows" % (action, len(seen)))

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
