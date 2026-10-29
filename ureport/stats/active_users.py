"""
Active users counted with HyperLogLog sketches in Valkey, alongside the contact activity tables.

Each answer adds the contact to one sketch per segment for the month it was given in, e.g. act:12:2026-10:gender:F.
The active users of a month are then the distinct contacts across that month and the 11 before it - a PFCOUNT over
their sketches - which is what the contact activity tables get by writing every answer forward into the next 12
months. Sketches count within a standard error of 0.81%, in at most 12KB each.

Valkey only holds the sketches being written to. The ones touched since the last checkpoint are tracked in a dirty
set, and the checkpoint copies their raw bytes into Postgres every night, so they can be restored from there and
topped up with the results since rather than rebuilt from every result.

The contact activity tables still feed the charts. An org only reads these when ACTIVE_USERS_HLL_READ or its
common.active_users_hll config is set, and compare() measures how far apart the two are.
"""

import logging
import statistics
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone as tzone

from django_valkey import get_valkey_connection

from django.conf import settings
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

KEY_PREFIX = "act"

# sketches touched since the last checkpoint, and the ones a checkpoint has taken over and is still saving
DIRTY_KEY = "act:dirty"
CHECKPOINTING_KEY = "act:dirty:checkpointing"

# a month's active users are the distinct contacts of it and the 11 months before it
WINDOW_MONTHS = 12

# the charts go back to the month a year ago, which itself unions the 11 months before it, so sketches are kept for
# that plus the current month and a month of slack
RETENTION_MONTHS = 25

# born years older than this aren't read - it bounds the sketches the oldest age band unions
MIN_BORN = 1900

# how many commands are sent in one pipeline
PIPELINE_SIZE = 1000

# results read per query by the backfill and restore
RESULTS_BATCH_SIZE = 5000

# a restore replays results answered this long before its checkpoint was taken, to cover the ones that were saved
# before the checkpoint but only added to their sketches after it
REPLAY_OVERLAP = timedelta(days=1)

COMPARE_SEGMENTS = ("all", "age", "gender", "location", "scheme")


def is_write_enabled():
    return getattr(settings, "ACTIVE_USERS_HLL_WRITE", True)


def is_read_enabled(org):
    return getattr(settings, "ACTIVE_USERS_HLL_READ", False) or bool(org.get_config("common.active_users_hll"))


def month_start(d):
    return date(d.year, d.month, 1)


def add_months(d, n):
    years, month = divmod(d.month - 1 + n, 12)
    return date(d.year + years, month + 1, 1)


def sketch_key(org_id, month, segment):
    return f"{KEY_PREFIX}:{org_id}:{month:%Y-%m}:{segment}"


def parse_key(key):
    """
    Splits a sketch key into its org id, month and segment
    """
    _, org_id, month, segment = key.split(":", 3)
    year, mon = month.split("-")
    return int(org_id), date(int(year), int(mon), 1), segment


def result_month(result_date):
    """
    The month an answer counts in, which like the contact activity trigger is the month of its UTC date
    """
    return month_start(result_date.astimezone(tzone.utc))


def result_segments(born, gender, state, scheme):
    """
    The segments an answer counts in, matching the values the contact activity counters are written and read with.
    Ages are kept by the year the contact was born, so that a month's age bands can be taken at that month just as
    the activity rows are - from the year of the month each row is for.
    """
    segments = ["all"]
    if born is not None:
        segments.append(f"born:{born}")
    if gender:
        segments.append(f"gender:{gender.upper()}")
    if state:
        segments.append(f"state:{state.upper()}")
    if scheme:
        segments.append(f"scheme:{scheme.lower()}")
    return segments


def is_countable(result):
    """
    Whether a result makes its contact active, the same condition the contact activity trigger has
    """
    return bool(
        result.org_id and result.flow and result.ruleset and result.category is not None and result.date is not None
    )


def _expire_at(month):
    return int(datetime.combine(add_months(month, RETENTION_MONTHS), datetime.min.time(), tzinfo=tzone.utc).timestamp())


def _add(r, contacts_by_key):
    """
    Adds contacts to sketches, by key, and marks those sketches dirty
    """
    pipe = r.pipeline(transaction=False)
    pending = 0
    for key, contacts in contacts_by_key.items():
        _, month, _ = parse_key(key)
        pipe.pfadd(key, *contacts)
        pipe.expireat(key, _expire_at(month))
        pending += 2
        if pending >= PIPELINE_SIZE:
            pipe.execute()
            pending = 0

    for keys in _chunks(list(contacts_by_key), PIPELINE_SIZE):
        pipe.sadd(DIRTY_KEY, *keys)
    pipe.execute()


def add_results(results):
    """
    Adds the contacts of the given poll results to the sketches of the months they answered in. Results that don't
    make their contact active are ignored, and adding a contact already counted changes nothing.
    """
    contacts_by_key = defaultdict(set)
    for result in results:
        if not is_countable(result):
            continue
        month = result_month(result.date)
        for segment in result_segments(result.born, result.gender, result.state, result.scheme):
            contacts_by_key[sketch_key(result.org_id, month, segment)].add(result.contact)

    if contacts_by_key:
        _add(get_valkey_connection(), contacts_by_key)

    return len(contacts_by_key)


def record_results(results):
    """
    Called as results are synced. Writes to the sketches are a side line for now, so they're never allowed to fail
    the sync - whatever is lost is recovered by a restore or backfill.
    """
    if not is_write_enabled():
        return

    try:
        add_results(results)
    except Exception:
        logger.error("Error adding results to active users sketches", exc_info=True)


def _countable_results(qs):
    """
    The fields of the given results needed to add them, for those that make their contact active
    """
    return qs.filter(category__isnull=False, date__isnull=False).exclude(flow="").exclude(ruleset="")


def _add_results_qs(qs, batch_size=RESULTS_BATCH_SIZE):
    """
    Adds the results of the given queryset, streamed and added a batch at a time
    """
    from ureport.polls.models import PollResult

    fields = ("org_id", "flow", "ruleset", "contact", "category", "date", "born", "gender", "state", "scheme")

    added, batch = 0, []
    for row in _countable_results(qs).values(*fields).iterator(chunk_size=batch_size):
        batch.append(PollResult(**row))
        if len(batch) >= batch_size:
            add_results(batch)
            added, batch = added + len(batch), []

    if batch:
        add_results(batch)
        added += len(batch)

    return added


def backfill(org, since=None, until=None, batch_size=RESULTS_BATCH_SIZE, progress=None):
    """
    Adds an org's existing results answered between the given months (inclusive) to the sketches, one poll at a time.
    Defaults to every month still kept. Safe to run again, or alongside the sync.
    """
    from ureport.polls.models import Poll, PollResult

    today = month_start(timezone.now())
    since = month_start(since) if since else add_months(today, 1 - RETENTION_MONTHS)
    until = add_months(month_start(until) if until else today, 1)

    after = datetime.combine(since, datetime.min.time(), tzinfo=tzone.utc)
    before = datetime.combine(until, datetime.min.time(), tzinfo=tzone.utc)

    added = 0
    flows = Poll.objects.filter(org=org).values_list("flow_uuid", flat=True).distinct().order_by("flow_uuid")
    for flow in flows:
        qs = PollResult.objects.filter(org=org, flow=flow, date__gte=after, date__lt=before)
        flow_added = _add_results_qs(qs, batch_size=batch_size)
        added += flow_added
        if progress:
            progress(flow, flow_added)

    return added


# ------------------------------------------------------------------------------
# Reading
# ------------------------------------------------------------------------------


def count(org, month, segments):
    """
    The distinct contacts active in the given month, i.e. in it or the 11 months before, in any of the given segments
    """
    return get_valkey_connection().pfcount(*_window_keys(org, month, segments))


def _window_keys(org, month, segments):
    return [sketch_key(org.id, add_months(month, -i), s) for i in range(WINDOW_MONTHS) for s in segments]


def _born_segments(month, min_age, max_age):
    """
    The born year segments of contacts in an age band in the given month
    """
    first = max(month.year - max_age, MIN_BORN)
    return [f"born:{born}" for born in range(first, month.year - min_age + 1)]


def _segment_series(org, segment_slug):
    """
    The series a chart segment has, as (name, extra fields, segments of a month) - mirroring the series the contact
    activity charts have
    """
    from .models import AgeSegment, GenderSegment, SchemeSegment

    if segment_slug == "all":
        return [(str(_("Active Users")), {}, lambda m: ["all"])]

    if segment_slug == "age":
        labels = {0: "0-14", 15: "15-19", 20: "20-24", 25: "25-30", 31: "31-34", 35: "35+"}
        return [
            (labels.get(a["min_age"]), {}, lambda m, a=a: _born_segments(m, a["min_age"], a["max_age"]))
            for a in AgeSegment.objects.all().values("min_age", "max_age")
        ]

    if segment_slug == "gender":
        labels = org.get_gender_labels()
        genders = GenderSegment.objects.all()
        if not org.get_config("common.has_extra_gender"):
            genders = genders.exclude(gender="O")
        return [
            (labels.get(g), {}, lambda m, g=g: [f"gender:{g.upper()}"])
            for g in genders.values_list("gender", flat=True)
        ]

    if segment_slug == "location":
        from ureport.locations.models import Boundary

        return [
            (name, {"osm_id": osm_id}, lambda m, o=osm_id: [f"state:{o.upper()}"])
            for osm_id, name in Boundary.get_org_top_level_boundaries_name(org).items()
        ]

    if segment_slug == "scheme":
        counts = org.get_org_contacts_counts()
        schemes = [k[7:] for k in counts if k.startswith("scheme:") and k[7:]]
        series = []
        for scheme in schemes:
            name = SchemeSegment.SCHEME_DISPLAY.get(scheme, scheme.upper())
            if name:
                series.append((name, {}, lambda m, s=scheme: [f"scheme:{s.lower()}"]))
        return series

    return []


def chart_months(now=None):
    """
    The months the active users charts cover, the same range the contact activity charts read
    """
    now = now or timezone.now()
    start = (now - timedelta(days=365)).replace(day=1).date()
    month, months = month_start(start), []
    while month <= now.date():
        months.append(month)
        month = add_months(month, 1)
    return months


def get_series_counts(org, segment_slug, months):
    """
    The active users of each series of a chart segment in each of the given months, as a list of
    (name, extra fields, {month: count})
    """
    series = _segment_series(org, segment_slug)
    pipe = get_valkey_connection().pipeline(transaction=False)
    for _name, _extra, segments_of in series:
        for month in months:
            keys = _window_keys(org, month, segments_of(month))
            if keys:
                pipe.pfcount(*keys)
            else:
                pipe.echo(0)
    results = iter(pipe.execute())

    return [(name, extra, {m: int(next(results)) for m in months}) for name, extra, _segs in series]


def get_activity(org, segment_slug, time_filters):
    """
    The active users chart data of a segment from the sketches, in the same shape the contact activity readers give
    """
    from .models import ContactActivity

    translation.activate(org.language)

    series = get_series_counts(org, segment_slug, chart_months())
    output = {tf: [] for tf in time_filters}
    for name, extra, counts in series:
        activities = [{"date": m, "count__sum": c} for m, c in counts.items()]
        for tf in time_filters:
            output[tf].append(dict(name=name, **extra, data=ContactActivity.get_activity_data(activities, tf)))
    return output


# ------------------------------------------------------------------------------
# Checkpoints
# ------------------------------------------------------------------------------


def checkpoint(batch_size=500):
    """
    Saves the raw bytes of every sketch touched since the last checkpoint. The dirty set is first moved aside, so
    that sketches touched while this runs are left for the next one, and only cleared a batch at a time once saved -
    an interrupted run is picked up by the next one. Returns the number of sketches saved.
    """
    from ureport.polls.models import PollResult

    from .models import ActiveUsersCheckpoint

    r = get_valkey_connection()

    if not r.exists(CHECKPOINTING_KEY):
        if not r.exists(DIRTY_KEY):
            return 0
        r.rename(DIRTY_KEY, CHECKPOINTING_KEY)

    # results after these are replayed on restore - see restore()
    taken_on = timezone.now()
    watermark = PollResult.objects.order_by("-id").values_list("id", flat=True).first() or 0

    saved = 0
    while True:
        keys = [k.decode() if isinstance(k, bytes) else k for k in r.srandmember(CHECKPOINTING_KEY, batch_size)]
        if not keys:
            break

        pipe = r.pipeline(transaction=False)
        for key in keys:
            pipe.get(key)
        values = pipe.execute()

        checkpoints = []
        for key, value in zip(keys, values):
            if value is None:  # expired since
                continue
            org_id, month, _ = parse_key(key)
            checkpoints.append(
                ActiveUsersCheckpoint(
                    org_id=org_id, key=key, month=month, value=value, taken_on=taken_on, watermark=watermark
                )
            )

        org_ids = set(_existing_org_ids({c.org_id for c in checkpoints}))
        checkpoints = [c for c in checkpoints if c.org_id in org_ids]

        ActiveUsersCheckpoint.objects.bulk_create(
            checkpoints,
            update_conflicts=True,
            unique_fields=["key"],
            update_fields=["value", "taken_on", "watermark"],
        )
        r.srem(CHECKPOINTING_KEY, *keys)
        saved += len(checkpoints)

    r.delete(CHECKPOINTING_KEY)
    prune_checkpoints()

    logger.info("Checkpointed %d active users sketches", saved)
    return saved


def _existing_org_ids(org_ids):
    from dash.orgs.models import Org

    return Org.objects.filter(id__in=org_ids).values_list("id", flat=True)


def prune_checkpoints():
    """
    Deletes checkpoints of sketches that have since expired, an org at a time
    """
    from dash.orgs.models import Org

    from .models import ActiveUsersCheckpoint

    cutoff = add_months(month_start(timezone.now()), 1 - RETENTION_MONTHS)
    for org_id in Org.objects.values_list("id", flat=True):
        ActiveUsersCheckpoint.objects.filter(org_id=org_id, month__lt=cutoff).delete()


def restore(org, batch_size=500):
    """
    Restores an org's sketches from their checkpoints, then adds the results saved or answered since. Checkpoints
    are merged into whatever the sketches already hold rather than replacing it, and adding results already counted
    changes nothing, so this can't inflate counts however much it overlaps. Returns the number of sketches restored
    and the number of results replayed.
    """
    from ureport.polls.models import Poll, PollResult

    from .models import ActiveUsersCheckpoint

    r = get_valkey_connection()
    cutoff = add_months(month_start(timezone.now()), 1 - RETENTION_MONTHS)
    checkpoints = ActiveUsersCheckpoint.objects.filter(org=org, month__gte=cutoff).order_by("id")

    restored, last_id = 0, 0
    taken_on, watermark = None, None
    while True:
        batch = list(checkpoints.filter(id__gt=last_id)[:batch_size])
        if not batch:
            break

        pipe = r.pipeline(transaction=False)
        for c in batch:
            tmp_key = f"{c.key}:restoring"
            pipe.set(tmp_key, bytes(c.value), ex=60)
            pipe.pfmerge(c.key, c.key, tmp_key)
            pipe.expireat(c.key, _expire_at(c.month))
            pipe.delete(tmp_key)
        pipe.execute()

        restored += len(batch)
        last_id = batch[-1].id
        taken_on = min([c.taken_on for c in batch] + ([taken_on] if taken_on else []))
        watermark = min([c.watermark for c in batch] + ([watermark] if watermark is not None else []))

    # with no checkpoint to restore, everything still kept is replayed
    if taken_on is None:
        return restored, backfill(org)

    # results saved after the checkpoint, and results of polls still syncing that were answered after it, which
    # covers the ones whose answers changed in place since
    replayed = _add_results_qs(PollResult.objects.filter(org=org, id__gt=watermark))

    since = taken_on - REPLAY_OVERLAP
    flows = Poll.objects.filter(org=org, stopped_syncing=False).values_list("flow_uuid", flat=True).distinct()
    for flow in flows.order_by("flow_uuid"):
        replayed += _add_results_qs(PollResult.objects.filter(org=org, flow=flow, date__gte=since))

    logger.info("Restored %d active users sketches and replayed %d results for org #%d", restored, replayed, org.id)
    return restored, replayed


def clear(org):
    """
    Deletes an org's sketches
    """
    r = get_valkey_connection()
    keys = list(r.scan_iter(match=f"{KEY_PREFIX}:{org.id}:*", count=1000))
    for chunk in _chunks(keys, PIPELINE_SIZE):
        r.delete(*chunk)
        r.srem(DIRTY_KEY, *chunk)
        r.srem(CHECKPOINTING_KEY, *chunk)
    return len(keys)


# ------------------------------------------------------------------------------
# Comparison
# ------------------------------------------------------------------------------


def _existing_activity(org, segment_slug, time_filters):
    from .models import ContactActivity

    readers = {
        "all": ContactActivity.get_activity,
        "age": ContactActivity.get_activity_age,
        "gender": ContactActivity.get_activity_gender,
        "location": ContactActivity.get_contact_activity_location,
        "scheme": ContactActivity.get_contact_activity_scheme,
    }
    return readers[segment_slug](org, time_filters)


def compare_org(org, segments=COMPARE_SEGMENTS):
    """
    Compares the active users of each month and series an org's charts show, as read from the contact activity
    counters and from the sketches. Returns a row for each, as a dict.
    """
    rows = []
    for segment_slug in segments:
        start = time.monotonic()
        existing = _existing_activity(org, segment_slug, [12])[12]
        existing_secs = time.monotonic() - start

        start = time.monotonic()
        hll = get_activity(org, segment_slug, [12])[12]
        hll_secs = time.monotonic() - start

        logger.debug(
            "Read %s active users of org #%d in %.3fs from counters, %.3fs from sketches",
            segment_slug,
            org.id,
            existing_secs,
            hll_secs,
        )

        for existing_series, hll_series in zip(existing, hll):
            for month, expected in sorted(existing_series["data"].items()):
                actual = hll_series["data"].get(month, 0)
                error = actual - expected
                rows.append(
                    dict(
                        org=org.id,
                        month=month[:7],
                        segment=segment_slug,
                        series=str(existing_series["name"]),
                        existing=expected,
                        hll=actual,
                        error=error,
                        rel_error=(error / expected) if expected else (0.0 if not actual else None),
                    )
                )
    return rows


def summarize(rows, min_count=100):
    """
    Summarizes the relative errors of comparison rows. Rows with fewer than min_count active users are left out of
    the error statistics, as a handful of contacts makes for large relative errors that mean nothing.
    """
    measured = [r for r in rows if r["existing"] >= min_count and r["rel_error"] is not None]
    errors = sorted(abs(r["rel_error"]) for r in measured)

    def percentile(p):
        return errors[min(len(errors) - 1, int(p * len(errors)))] if errors else None

    return dict(
        rows=len(rows),
        measured=len(measured),
        mean_abs_rel_error=statistics.fmean(errors) if errors else None,
        p50_abs_rel_error=percentile(0.5),
        p95_abs_rel_error=percentile(0.95),
        max_abs_rel_error=errors[-1] if errors else None,
        # the share of rows within 2 standard errors, which should be about 95%
        within_2se=(sum(1 for e in errors if e <= 0.0162) / len(errors)) if errors else None,
        existing_total=sum(r["existing"] for r in rows if r["segment"] == "all"),
        hll_total=sum(r["hll"] for r in rows if r["segment"] == "all"),
    )


def worst(rows, limit=20, min_count=100):
    """
    The rows furthest apart, by relative error where there are enough active users to measure it, else by absolute
    """
    return sorted(
        rows,
        key=lambda r: (
            r["existing"] >= min_count and r["rel_error"] is not None,
            abs(r["rel_error"]) if r["existing"] >= min_count and r["rel_error"] is not None else abs(r["error"]),
        ),
        reverse=True,
    )[:limit]


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]
