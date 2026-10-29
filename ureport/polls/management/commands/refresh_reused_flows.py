# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from ureport.polls.models import Poll


class Command(BaseCommand):
    help = (
        "Lists the flows that have both retired polls and polls still syncing them. A poll set up on a retired flow "
        "used to resume the flow's sync rather than pull all of its results again, leaving counts that miss the "
        "results the flow was retired with. With --refresh, pulls all of each flow's results again."
    )

    def add_arguments(self, parser):
        parser.add_argument("--org", type=int, help="Only the flows of the org with this id")
        parser.add_argument("--refresh", action="store_true", help="Pull all of each flow's results again")

    def handle(self, *args, **options):
        retired = Poll.objects.filter(org_id=OuterRef("org_id"), flow_uuid=OuterRef("flow_uuid"), stopped_syncing=True)

        syncing = (
            Poll.objects.filter(is_active=True, stopped_syncing=False)
            .exclude(flow_uuid="")
            .filter(Exists(retired))
            .order_by("org_id", "flow_uuid", "-created_on")
        )
        if options["org"]:
            syncing = syncing.filter(org_id=options["org"])

        # one poll per flow is enough to pull it again, as the re-pull covers every poll on it
        seen = set()
        for poll in syncing:
            if (poll.org_id, poll.flow_uuid) in seen:
                continue
            seen.add((poll.org_id, poll.flow_uuid))

            self.stdout.write("org #%d flow %s (poll #%d %s)" % (poll.org_id, poll.flow_uuid, poll.pk, poll.title))

            if options["refresh"]:
                poll.pull_refresh_task()

        action = "Scheduled a full pull of" if options["refresh"] else "Found"
        self.stdout.write("%s %d flows" % (action, len(seen)))
