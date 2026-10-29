# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand, CommandError

from ureport.polls.models import Poll
from ureport.polls.sync import queue_archives_repair


class Command(BaseCommand):
    help = "Re-pulls the archived results of the given polls, walking the archives once for all of them"

    def add_arguments(self, parser):
        parser.add_argument("poll_ids", nargs="+", type=int, metavar="POLL_ID")

    def handle(self, *args, **options):
        poll_ids = options["poll_ids"]
        polls = list(Poll.objects.filter(id__in=poll_ids).select_related("org", "backend"))

        missing = sorted(set(poll_ids) - {poll.id for poll in polls})
        if missing:
            raise CommandError("No polls with ids: %s" % ", ".join(str(poll_id) for poll_id in missing))

        jobs = queue_archives_repair(polls)
        if not jobs:
            self.stdout.write("Nothing queued: the polls no longer sync, or a batch already owns their flows")
            return

        for job in jobs:
            flows = job.cursor["flows"]
            self.stdout.write(
                "Queued archives batch job #%d on org #%d for %d flows" % (job.id, job.org_id, len(flows))
            )
