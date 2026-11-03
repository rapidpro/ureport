"""
Active users counted with HyperLogLog sketches in Valkey.

Each answer adds the contact to one sketch per segment for the month it was given in, e.g. act:12:2026-10:gender:F.
The active users of a month are then the distinct contacts across that month and the 11 before it - a PFCOUNT over
their sketches. Sketches count within a standard error of 0.81%, in at most 12KB each.

Valkey only holds the sketches being written to. The ones touched since the last checkpoint are tracked in a dirty
set, and the checkpoint adds a copy of their raw bytes to Postgres every night, so they can be restored from there and
topped up with the results since rather than rebuilt from every result. The copies of the last 30 days are all kept,
as a contact can't be taken back out of a sketch: sketches that went wrong are rolled back to a night before that.

Sketches have no expiry time, as Valkey is shared and its volatile-lru policy only evicts keys that have one. Those
past RETENTION_MONTHS are deleted with their checkpoints instead.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone as tzone

from django_valkey import get_valkey_connection

from django.db.models import Exists, OuterRef
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

# born years older than this are kept together in one sketch, which bounds the sketches the oldest age band unions
MIN_BORN = 1900
OLD_BORN_SEGMENT = "born:pre1900"

# born years below this are left out, as being over the oldest age band - most are contacts' ages typed in place of
# the year
MIN_OLD_BORN = 26

# how many commands are sent in one pipeline
PIPELINE_SIZE = 1000

# results read per query by the backfill and restore
RESULTS_BATCH_SIZE = 5000

# a restore replays results answered this long before its checkpoint was taken, to cover the ones that were saved
# before the checkpoint but only added to their sketches after it
REPLAY_OVERLAP = timedelta(days=1)

# how far back a restore can roll sketches back to
CHECKPOINT_HISTORY = timedelta(days=30)


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
    The month an answer counts in, which is the month of its UTC date
    """
    return month_start(result_date.astimezone(tzone.utc))


def result_segments(born, gender, state, scheme):
    """
    The segments an answer counts in. Ages are kept by the year the contact was born, so that a month's age bands can
    be taken at that month.
    """
    values = {"born": born, "gender": gender, "state": state, "scheme": scheme}
    segments = (_value_segment(kind, value) for kind, value in values.items())
    return ["all", *filter(None, segments)]


def _value_segment(kind, value):
    """
    The segment of a value of the given kind of segment, or None if it isn't one that's counted
    """
    if kind == "born":
        if value is None or value < MIN_OLD_BORN:
            return None
        return f"born:{value}" if value >= MIN_BORN else OLD_BORN_SEGMENT
    if not value:
        return None
    return f"{kind}:{value.lower() if kind == 'scheme' else value.upper()}"


def is_countable(result):
    """
    Whether a result makes its contact active
    """
    return bool(
        result.org_id and result.flow and result.ruleset and result.category is not None and result.date is not None
    )


def _add(r, contacts_by_key):
    """
    Adds contacts to sketches, by key, and marks those sketches dirty
    """
    pipe = r.pipeline(transaction=False)
    pending = 0
    for key, contacts in contacts_by_key.items():
        pipe.pfadd(key, *contacts)
        pending += 1
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
    Called as results are synced. Writes to the sketches are never allowed to fail the sync - whatever is lost is
    recovered by a restore or backfill.
    """
    try:
        add_results(results)
    except Exception:
        logger.error("Error adding results to active users sketches", exc_info=True)


def _countable_results(qs):
    """
    Those of the given results that make their contact active, the same condition as is_countable
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


def _backfill_results(org, since, until, batch_size, progress):
    """
    Adds an org's existing results, one poll at a time
    """
    from ureport.polls.models import Poll, PollResult

    after = datetime.combine(since, datetime.min.time(), tzinfo=tzone.utc)
    before = datetime.combine(until, datetime.min.time(), tzinfo=tzone.utc)

    added = 0
    flows = Poll.objects.filter(org=org).values_list("flow_uuid", flat=True).distinct().order_by("flow_uuid")
    for flow in flows:
        qs = PollResult.objects.filter(org=org, flow=flow, date__gte=after, date__lt=before)
        flow_added = _add_results_qs(qs, batch_size=batch_size)
        added += flow_added
        if progress:
            progress("results", f"flow {flow}", flow_added)

    return added


def backfill(org, since=None, until=None, batch_size=RESULTS_BATCH_SIZE, progress=None):
    """
    Fills an org's sketches with the results answered between the given months (inclusive), defaulting to every month
    still kept. It only adds to the sketches, so this is safe to run again, or alongside the sync. Returns the number of
    results added.
    """
    today = month_start(timezone.now())
    since = month_start(since) if since else add_months(today, 1 - RETENTION_MONTHS)
    until = add_months(month_start(until) if until else today, 1)

    results = _backfill_results(org, since, until, batch_size, progress)

    logger.info("Backfilled %d results for org #%d", results, org.id)
    return results


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
    first, last = month.year - max_age, month.year - min_age
    segments = [f"born:{born}" for born in range(max(first, MIN_BORN), last + 1)]

    # the band reaching back past the kept born years also takes the older ones
    if first < MIN_BORN <= last:
        segments.append(OLD_BORN_SEGMENT)
    return segments


def _segment_series(org, segment_slug):
    """
    The series a chart segment has, as (name, extra fields, segments of a month)
    """
    from .models import AgeSegment, GenderSegment, SchemeSegment

    if segment_slug == "all":
        return [(str(_("Active Users")), {}, lambda m: ["all"])]

    if segment_slug == "age":
        return [
            (
                AgeSegment.ACTIVITY_LABELS.get(a["min_age"]),
                {},
                lambda m, a=a: _born_segments(m, a["min_age"], a["max_age"]),
            )
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
    The months the active users charts cover
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
    The active users chart data of a segment, by time filter
    """
    translation.activate(org.language)

    series = get_series_counts(org, segment_slug, chart_months())
    output = {tf: [] for tf in time_filters}
    for name, extra, counts in series:
        for tf in time_filters:
            output[tf].append(dict(name=name, **extra, data=_time_filter_data(counts, tf)))
    return output


def _time_filter_data(counts, time_filter):
    """
    The counts of months as a chart's data for a time filter, each of its points showing the count of its month
    """
    from ureport.utils import get_time_filter_dates_map

    dates_map = get_time_filter_dates_map(time_filter=time_filter)

    by_key = defaultdict(int)
    for month, count in counts.items():
        by_key[dates_map.get(str(month))] += count

    return {key: by_key[key[:-2] + "01"] for key in set(dates_map.values())}


# ------------------------------------------------------------------------------
# Checkpoints
# ------------------------------------------------------------------------------


def checkpoint(batch_size=500):
    """
    Adds a copy of the raw bytes of every sketch touched since the last checkpoint. The dirty set is first moved
    aside, so that sketches touched while this runs are left for the next one, and only cleared a batch at a time once
    saved - an interrupted run is picked up by the next one, which then goes on to the sketches touched since too. A
    run that gets to the end is recorded, for a restore to replay the results since. Returns the number of sketches
    saved.
    """
    from ureport.polls.models import PollResult

    from .models import ActiveUsersCheckpointRun

    r = get_valkey_connection()

    # results after these are replayed on restore - see restore()
    taken_on = timezone.now()
    watermark = PollResult.objects.order_by("-id").values_list("id", flat=True).first() or 0

    # an interrupted run's sketches first, then everything touched before this run started
    saved = _save_checkpointing(r, taken_on, batch_size)
    if r.exists(DIRTY_KEY):
        r.rename(DIRTY_KEY, CHECKPOINTING_KEY)
        saved += _save_checkpointing(r, taken_on, batch_size)

    ActiveUsersCheckpointRun.objects.create(taken_on=taken_on, watermark=watermark, saved=saved)
    prune_checkpoints()

    logger.info("Checkpointed %d active users sketches", saved)
    return saved


def _save_checkpointing(r, taken_on, batch_size):
    """
    Saves the sketches in the checkpointing set, clearing them from it a batch at a time
    """
    from .models import ActiveUsersCheckpoint

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
            if value is None:  # deleted since
                continue
            org_id, month, _ = parse_key(key)
            checkpoints.append(
                ActiveUsersCheckpoint(org_id=org_id, key=key, month=month, value=value, taken_on=taken_on)
            )

        org_ids = set(_existing_org_ids({c.org_id for c in checkpoints}))
        checkpoints = [c for c in checkpoints if c.org_id in org_ids]

        ActiveUsersCheckpoint.objects.bulk_create(
            checkpoints, update_conflicts=True, unique_fields=["key", "taken_on"], update_fields=["value"]
        )
        r.srem(CHECKPOINTING_KEY, *keys)
        saved += len(checkpoints)

    r.delete(CHECKPOINTING_KEY)
    return saved


def _existing_org_ids(org_ids):
    from dash.orgs.models import Org

    return Org.objects.filter(id__in=org_ids).values_list("id", flat=True)


def prune_checkpoints():
    """
    Deletes sketches past their retention along with their checkpoints, and checkpoints older than the history that a
    later one as old replaces, an org at a time, and the records of runs older than the history but for the last two,
    which a restore as of its start replays from
    """
    from dash.orgs.models import Org

    from .models import ActiveUsersCheckpoint, ActiveUsersCheckpointRun

    r = get_valkey_connection()
    cutoff = add_months(month_start(timezone.now()), 1 - RETENTION_MONTHS)
    oldest = timezone.now() - CHECKPOINT_HISTORY
    replaced = ActiveUsersCheckpoint.objects.filter(
        key=OuterRef("key"), taken_on__gt=OuterRef("taken_on"), taken_on__lte=oldest
    )
    for org_id in Org.objects.values_list("id", flat=True):
        # sketches first, so that any left by an interrupted run still have the checkpoints that find them
        past = ActiveUsersCheckpoint.objects.filter(org_id=org_id, month__lt=cutoff)
        for keys in _chunks(list(past.order_by("key").values_list("key", flat=True).distinct()), PIPELINE_SIZE):
            r.delete(*keys)
        past.delete()

        ActiveUsersCheckpoint.objects.filter(org_id=org_id, taken_on__lte=oldest).filter(Exists(replaced)).delete()

    runs = ActiveUsersCheckpointRun.objects.filter(taken_on__lte=oldest).order_by("-id").values_list("id", flat=True)
    ActiveUsersCheckpointRun.objects.filter(id__in=list(runs[2:])).delete()


def restore(org, as_of=None, batch_size=500):
    """
    Restores an org's sketches from the latest checkpoint of each, then adds the results saved or answered since.
    Checkpoints are merged into whatever the sketches already hold rather than replacing it, and adding results
    already counted changes nothing, so this can't inflate counts however much it overlaps. Returns the number of
    sketches restored and the number of results replayed.

    The last completed run saved every sketch touched before it started. Results are replayed from the run before
    it rather than from it, so a result saved just before the last run started but only added to its sketches after
    is replayed too. Results of polls still syncing answered since just before the last run are replayed as well,
    which covers those whose answers changed in place since.

    Given as_of, a time within the history, the sketches are instead rolled back to it: they're deleted first, as
    merging into them wouldn't take anything out, checkpoints and runs after it are ignored, and once the results
    since are replayed those checkpoints are deleted so that a later restore doesn't bring them back.
    """
    from ureport.polls.models import Poll, PollResult

    from .models import ActiveUsersCheckpoint, ActiveUsersCheckpointRun

    r = get_valkey_connection()
    now = timezone.now()
    cutoff = add_months(month_start(now), 1 - RETENTION_MONTHS)
    rollback = as_of is not None
    as_of = as_of or now

    runs = list(ActiveUsersCheckpointRun.objects.filter(taken_on__lte=as_of).order_by("-id")[:2])
    if rollback:
        if as_of < now - CHECKPOINT_HISTORY:
            raise ValueError(f"Can only roll back {CHECKPOINT_HISTORY.days} days")
        if not runs:
            raise ValueError(f"No completed checkpoint as of {as_of}")
        _delete_sketches(org)

    # the latest checkpoint of each sketch - an empty one means it was deleted, see clear()
    checkpoints = (
        ActiveUsersCheckpoint.objects.filter(org=org, month__gte=cutoff, taken_on__lte=as_of)
        .order_by("key", "-taken_on")
        .distinct("key")
    )

    restored, last_key = 0, ""
    while True:
        batch = list(checkpoints.filter(key__gt=last_key)[:batch_size])
        if not batch:
            break

        pipe = r.pipeline(transaction=False)
        for c in batch:
            if not c.value:
                continue
            tmp_key = f"{c.key}:restoring"
            pipe.set(tmp_key, bytes(c.value), ex=60)
            pipe.pfmerge(c.key, c.key, tmp_key)
            pipe.delete(tmp_key)
            restored += 1
        pipe.execute()

        last_key = batch[-1].key

    # with no checkpoint run to replay from, everything still kept is replayed
    if not restored or not runs:
        replayed = backfill(org)
    else:
        after = datetime.combine(cutoff, datetime.min.time(), tzinfo=tzone.utc)
        watermark = runs[1].watermark if len(runs) > 1 else 0
        replayed = _add_results_qs(PollResult.objects.filter(org=org, id__gt=watermark, date__gte=after))

        since = runs[0].taken_on - REPLAY_OVERLAP
        flows = Poll.objects.filter(org=org, stopped_syncing=False).values_list("flow_uuid", flat=True).distinct()
        for flow in flows.order_by("flow_uuid"):
            replayed += _add_results_qs(PollResult.objects.filter(org=org, flow=flow, date__gte=since))

    if rollback:
        ActiveUsersCheckpoint.objects.filter(org=org, taken_on__gt=as_of).delete()

    logger.info("Restored %d active users sketches and replayed %d results for org #%d", restored, replayed, org.id)
    return restored, replayed


def clear(org):
    """
    Deletes an org's sketches, for a backfill to fill back. Each of its checkpoints gets a later empty one, so that a
    restore doesn't bring back sketches the backfill doesn't, while one to before now still can.
    """
    from .models import ActiveUsersCheckpoint

    taken_on = timezone.now()
    checkpoints = ActiveUsersCheckpoint.objects.filter(org=org).order_by("key", "-taken_on").distinct("key")
    ActiveUsersCheckpoint.objects.bulk_create(
        [
            ActiveUsersCheckpoint(org=org, key=key, month=month, value=b"", taken_on=taken_on)
            for key, month in checkpoints.values_list("key", "month")
        ],
        batch_size=PIPELINE_SIZE,
    )
    return _delete_sketches(org)


def _delete_sketches(org):
    r = get_valkey_connection()
    keys = list(r.scan_iter(match=f"{KEY_PREFIX}:{org.id}:*", count=1000))
    for chunk in _chunks(keys, PIPELINE_SIZE):
        r.delete(*chunk)
        r.srem(DIRTY_KEY, *chunk)
        r.srem(CHECKPOINTING_KEY, *chunk)
    return len(keys)


def remove_expiries():
    """
    Takes the expiry time off sketches that were given one before they stopped having them, leaving the temporary keys
    of a restore alone. Returns the number of sketches changed.
    """
    r = get_valkey_connection()
    keys = [k.decode() if isinstance(k, bytes) else k for k in r.scan_iter(match=f"{KEY_PREFIX}:*", count=1000)]

    changed = 0
    for chunk in _chunks([k for k in keys if not k.endswith(":restoring")], PIPELINE_SIZE):
        pipe = r.pipeline(transaction=False)
        for key in chunk:
            pipe.persist(key)
        changed += sum(pipe.execute())
    return changed


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]
