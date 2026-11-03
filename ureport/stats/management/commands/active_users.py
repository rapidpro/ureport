import logging
from datetime import date, datetime, time, timezone

from django.core.management.base import BaseCommand, CommandError

from dash.orgs.models import Org
from ureport.stats import active_users

logger = logging.getLogger(__name__)


def parse_month(value):
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        raise CommandError(f"Invalid month {value}, expected YYYY-MM")


def parse_day(value):
    try:
        return datetime.combine(date.fromisoformat(value), time.max, tzinfo=timezone.utc)
    except ValueError:
        raise CommandError(f"Invalid day {value}, expected YYYY-MM-DD")


class Command(BaseCommand):
    help = (
        "Backfills, checkpoints and restores the active users counted by HyperLogLog sketches. A backfill fills an "
        "org's sketches from its results - it only adds to the sketches, so it can be run again."
    )

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        backfill = sub.add_parser("backfill", help="Fill the sketches from the results")
        backfill.add_argument("--org", type=int, action="append", dest="orgs", help="Org id, all active by default")
        backfill.add_argument("--since", type=parse_month, help="First month to add (YYYY-MM), all kept by default")
        backfill.add_argument("--until", type=parse_month, help="Last month to add (YYYY-MM), this month by default")
        backfill.add_argument(
            "--clear", action="store_true", help="Delete the org's sketches first, losing results since deleted"
        )
        backfill.add_argument("--from-org", type=int, help="Start at this org id, e.g. to resume an earlier run")
        backfill.add_argument("--limit", type=int, help="Backfill at most this many orgs")

        sub.add_parser("checkpoint", help="Save the sketches touched since the last checkpoint")
        sub.add_parser("remove-expiries", help="Take the expiry time off sketches that still have one")

        restore = sub.add_parser("restore", help="Restore sketches from their checkpoints and replay results since")
        restore.add_argument("--org", type=int, action="append", dest="orgs", help="Org id, all active by default")
        restore.add_argument(
            "--as-of",
            type=parse_day,
            help="Roll the sketches back to their checkpoints of this day (YYYY-MM-DD, UTC), dropping any since",
        )

    def handle(self, *args, action, **options):
        getattr(self, f"handle_{action.replace('-', '_')}")(**options)

    def get_orgs(self, org_ids):
        orgs = Org.objects.filter(is_active=True).order_by("id")
        if org_ids:
            orgs = Org.objects.filter(id__in=org_ids).order_by("id")
        return list(orgs)

    def handle_backfill(self, orgs, since, until, clear, from_org, limit, **options):
        todo = [o for o in self.get_orgs(orgs) if from_org is None or o.id >= from_org]
        if limit is not None:
            todo, rest = todo[:limit], todo[limit:]
        else:
            rest = []

        # a backfill only adds to the sketches, so an org that fails is logged and left to be run again
        failed = []
        for org in todo:
            try:
                if clear:
                    self.stdout.write(f"Deleted {active_users.clear(org)} sketches of org #{org.id}")

                results = active_users.backfill(
                    org,
                    since=since,
                    until=until,
                    progress=lambda source, part, n: n and self.stdout.write(f"  org #{org.id} {part}: {n} {source}"),
                )
            except Exception as e:
                logger.exception("Error backfilling active users of org #%d", org.id)
                self.stderr.write(f"org #{org.id} ({org.name}) failed: {e}")
                failed.append(org)
                continue

            self.stdout.write(f"org #{org.id} ({org.name}): {results} results")

        if rest:
            self.stdout.write(f"Stopped after {len(todo)} orgs, {len(rest)} left - resume with --from-org {rest[0].id}")

        if failed:
            ids = " ".join(f"--org {o.id}" for o in failed)
            raise CommandError(f"{len(failed)} orgs failed, run them again with: {ids}")

    def handle_checkpoint(self, **options):
        self.stdout.write(f"Checkpointed {active_users.checkpoint()} sketches")

    def handle_remove_expiries(self, **options):
        self.stdout.write(f"Removed the expiry of {active_users.remove_expiries()} sketches")

    def handle_restore(self, orgs, as_of, **options):
        for org in self.get_orgs(orgs):
            try:
                restored, replayed = active_users.restore(org, as_of=as_of)
            except ValueError as e:
                raise CommandError(str(e))
            self.stdout.write(f"Restored {restored} sketches of org #{org.id} and replayed {replayed} results")
