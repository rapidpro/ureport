import csv
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from dash.orgs.models import Org
from ureport.stats import active_users


def parse_month(value):
    try:
        year, month = value.split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        raise CommandError(f"Invalid month {value}, expected YYYY-MM")


class Command(BaseCommand):
    help = (
        "Seeds, backfills, compares, checkpoints and restores the active users counted by HyperLogLog sketches. To "
        "fill the sketches of an org, seed them from its contact activities first, then backfill from its results - "
        "both only add to the sketches, so either can be run again."
    )

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        seed = sub.add_parser("seed", help="Seed the sketches from the contact activities, before any backfill")
        seed.add_argument("--org", type=int, action="append", dest="orgs", help="Org id, all active by default")
        seed.add_argument(
            "--prefix-length",
            type=int,
            default=active_users.SEED_PREFIX_LENGTH,
            choices=range(0, 4),
            help="Read the activities of contacts in 16^N ranges of uuids at a time",
        )

        backfill = sub.add_parser("backfill", help="Add existing poll results to the sketches, after any seed")
        backfill.add_argument("--org", type=int, action="append", dest="orgs", help="Org id, all active by default")
        backfill.add_argument("--since", type=parse_month, help="First month to add (YYYY-MM), all kept by default")
        backfill.add_argument("--until", type=parse_month, help="Last month to add (YYYY-MM), this month by default")
        backfill.add_argument("--clear", action="store_true", help="Delete the org's sketches first")

        compare = sub.add_parser("compare", help="Compare the sketches with the contact activity counters")
        compare.add_argument("--org", type=int, action="append", dest="orgs", help="Org id, all active by default")
        compare.add_argument(
            "--segment", action="append", dest="segments", choices=active_users.COMPARE_SEGMENTS, help="Chart segment"
        )
        compare.add_argument("--worst", type=int, default=20, help="How many of the furthest apart rows to show")
        compare.add_argument("--min-count", type=int, default=100, help="Smallest count measured for relative error")
        compare.add_argument("--csv", dest="csv_path", help="Write every row to this CSV file")

        sub.add_parser("checkpoint", help="Save the sketches touched since the last checkpoint")

        restore = sub.add_parser("restore", help="Restore sketches from their checkpoints and replay results since")
        restore.add_argument("--org", type=int, action="append", dest="orgs", help="Org id, all active by default")

    def handle(self, *args, action, **options):
        getattr(self, f"handle_{action}")(**options)

    def get_orgs(self, org_ids):
        orgs = Org.objects.filter(is_active=True).order_by("id")
        if org_ids:
            orgs = Org.objects.filter(id__in=org_ids).order_by("id")
        return list(orgs)

    def handle_seed(self, orgs, prefix_length, **options):
        for org in self.get_orgs(orgs):
            added = active_users.seed(
                org,
                prefix_length=prefix_length,
                progress=lambda start, end, n: (
                    n and self.stdout.write(f"  org #{org.id} [{start}, {end}): {n} answers")
                ),
            )
            self.stdout.write(f"Seeded {added} answers of org #{org.id} ({org.name})")

    def handle_backfill(self, orgs, since, until, clear, **options):
        for org in self.get_orgs(orgs):
            if clear:
                self.stdout.write(f"Deleted {active_users.clear(org)} sketches of org #{org.id}")

            added = active_users.backfill(
                org,
                since=since,
                until=until,
                progress=lambda flow, n: self.stdout.write(f"  org #{org.id} flow {flow}: {n} results", ending="\n"),
            )
            self.stdout.write(f"Added {added} results of org #{org.id} ({org.name})")

    def handle_compare(self, orgs, segments, worst, min_count, csv_path, **options):
        segments = segments or active_users.COMPARE_SEGMENTS
        all_rows = []
        for org in self.get_orgs(orgs):
            rows = active_users.compare_org(org, segments=segments)
            all_rows.extend(rows)
            self.write_summary(f"org #{org.id} ({org.name})", active_users.summarize(rows, min_count=min_count))

        self.write_summary("all orgs", active_users.summarize(all_rows, min_count=min_count))

        self.stdout.write(f"\nWorst {worst}:")
        self.write_rows(active_users.worst(all_rows, limit=worst, min_count=min_count))

        if csv_path:
            self.write_csv(csv_path, all_rows)
            self.stdout.write(f"\nWrote {len(all_rows)} rows to {csv_path}")

    def handle_checkpoint(self, **options):
        self.stdout.write(f"Checkpointed {active_users.checkpoint()} sketches")

    def handle_restore(self, orgs, **options):
        for org in self.get_orgs(orgs):
            restored, replayed = active_users.restore(org)
            self.stdout.write(f"Restored {restored} sketches of org #{org.id} and replayed {replayed} results")

    def write_summary(self, label, summary):
        def pct(v):
            return "-" if v is None else f"{v * 100:.2f}%"

        self.stdout.write(
            f"{label}: {summary['rows']} rows, {summary['measured']} measured, "
            f"mean {pct(summary['mean_abs_rel_error'])}, p50 {pct(summary['p50_abs_rel_error'])}, "
            f"p95 {pct(summary['p95_abs_rel_error'])}, max {pct(summary['max_abs_rel_error'])}, "
            f"within 2SE {pct(summary['within_2se'])}"
        )

    def write_rows(self, rows):
        self.stdout.write(
            f"{'org':>5} {'month':<8} {'segment':<9} {'series':<20} {'existing':>10} {'hll':>10} {'error':>8} {'rel':>8}"
        )
        for r in rows:
            rel = "-" if r["rel_error"] is None else f"{r['rel_error'] * 100:.2f}%"
            self.stdout.write(
                f"{r['org']:>5} {r['month']:<8} {r['segment']:<9} {r['series'][:20]:<20} "
                f"{r['existing']:>10} {r['hll']:>10} {r['error']:>8} {rel:>8}"
            )

    def write_csv(self, path, rows):
        fields = ["org", "month", "segment", "series", "existing", "hll", "error", "rel_error"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
