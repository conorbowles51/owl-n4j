"""The Case Timeline phone lens (03 section 9): phone activity merged into the Timeline day by day, read from the
phone views through windows, never written as timeline nodes.

A lens entry is either a communication (one row per event, the same rows, copies and filter as Conversations, so
a total under a filter equals the Conversations total for the same filter and kinds, T-1) or another record's
event time from ``pv_timeline_entry`` (a location, a web visit, a device event...), one row per time value. A
communication's own records never appear twice: entries of a record that is, or belongs to, a communication are
left to the communication row.

Kinds of entry (``lens_kinds``): ``messages``, ``calls``, ``emails`` (communications), ``media``, ``locations``,
``web``, ``apps``, ``accounts``, ``device``, ``sensor``, ``other``. The default is messages, calls, emails, media
and locations; device events and sensor samples are off and their number is stated (T-7).

Lanes (``lane_by``): one per phone (default), per person (from the participant filter), per activity class or per
kind. ``buckets`` gives the counts per lane per hour or day for the Lanes view, with the periods where a phone has
no data marked ``no_data`` (from 04's hour states), distinct from a period with no matching entries (T-6).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import List, Literal

from pydantic import Field
from sqlalchemy import text

from services.phone import streams
from services.phone import time_display as T
from services.phone.filters import StreamFilter, snapshot

LensKind = Literal["messages", "calls", "emails", "media", "locations", "web", "apps", "accounts", "device", "sensor",
                   "other"]
COMM_GROUPS = {"messages": ["message", "chat_activity"], "calls": ["call", "voicemail"], "emails": ["email"]}
DEFAULT_KINDS = ["messages", "calls", "emails", "media", "locations"]
HIDDEN_BY_DEFAULT = ("device", "sensor")
KIND_WORDS = {"messages": "Messages", "calls": "Calls", "emails": "Emails", "media": "Photos and media",
              "locations": "Locations", "web": "Web and searches", "apps": "Apps", "accounts": "Accounts",
              "device": "Device activity", "sensor": "Sensor readings", "other": "Other records"}
# record types of the non-communication entries, by kind; anything not listed is "other"
MODEL_KINDS = {
    "locations": ("Location", "WirelessNetwork", "CellTower", "Journey", "LocationStay"),
    "media": ("Attachment", "FileDownload", "Photo", "Video", "Audio", "Recording", "VoiceMemo"),
    "web": ("VisitedPage", "SearchedItem", "WebBookmark", "Cookie"),
    "apps": ("InstalledApplication", "ApplicationUsage", "Notification", "AppsUsageLog"),
    "accounts": ("UserAccount", "Password", "Autofill", "User", "Contact"),
    "device": ("DeviceEvent", "PoweringEvent", "NetworkUsage", "DeviceConnectivity", "BluetoothDevice",
               "Log", "MobileCard"),
    "sensor": ("ActivitySensorData", "SensorReading", "HealthData"),
}
ACTIVITY_CLASSES = ("interaction", "device_state", "passive", "unknown")
CLASS_WORDS = {"interaction": "Someone using the phone", "device_state": "Device state", "passive": "Passive records",
               "unknown": "Class not known"}
WINDOW_MAX = 1000
CASE_EVENTS_LANE = {"key": "case_events", "label": "Case events"}


class TimelineLensFilter(StreamFilter):
    lens_kinds: List[LensKind] = Field(default_factory=lambda: list(DEFAULT_KINDS))
    model_types: List[str] = Field(default_factory=list)
    activity_classes: List[Literal["interaction", "device_state", "passive", "unknown"]] = Field(default_factory=list)
    lane_by: Literal["phone", "person", "activity_class", "kind"] = "phone"


def _kind_sql(col="t.model_type"):
    parts = ["WHEN %s = ANY(CAST(ARRAY[%s] AS text[])) THEN '%s'" % (col, ", ".join("'%s'" % m for m in models), k)
             for k, models in MODEL_KINDS.items()]
    return "CASE %s ELSE 'other' END" % " ".join(parts)


def _stream_filter(f: TimelineLensFilter) -> StreamFilter | None:
    """The Conversations filter behind the communication rows, or None when no communication kind is chosen."""
    chosen = [k for g in f.lens_kinds if g in COMM_GROUPS for k in COMM_GROUPS[g]]
    if f.kinds:
        chosen = [k for k in chosen if k in f.kinds]
    if not chosen or (f.activity_classes and "interaction" not in f.activity_classes) or f.model_types:
        return None
    body = f.model_dump(exclude={"lens_kinds", "model_types", "activity_classes", "lane_by"})
    body["kinds"] = chosen
    return StreamFilter.model_validate(body)


def _other_applies(f: TimelineLensFilter) -> bool:
    """Filters that only communications have (a conversation, a direction, an app, a badge, Between) leave the other
    entries out rather than pretend they matched."""
    fl = f.flags
    return not (f.threads or f.directions or f.apps or f.participant_mode in ("between", "sent_by", "sent_to")
                or any(v is not None for v in (fl.carved, fl.unreadable, fl.synced, fl.has_attachment)))


class _Other:
    """WHERE and parameters of the non-communication entries."""

    def __init__(self, conn, f: TimelineLensFilter, kinds):
        self.p = {"case": f.case_id, "kinds": list(kinds)}
        w = ["t.case_id = :case", "(%s) = ANY(CAST(:kinds AS text[]))" % _kind_sql(),
             "(t.is_event_time OR t.instant IS NULL)",
             "NOT EXISTS (SELECT 1 FROM pv_comm_event c WHERE c.record_uid = t.record_uid OR c.record_uid = "
             "t.root_record_uid)"]
        if f.phones:
            w.append("t.extraction_id = ANY(CAST(:phones AS uuid[]))")
            self.p["phones"] = f.phones
        if f.model_types:
            w.append("t.model_type = ANY(CAST(:models AS text[]))")
            self.p["models"] = f.model_types
        if f.activity_classes:
            w.append("coalesce(t.activity_class, 'unknown') = ANY(CAST(:classes AS text[]))")
            self.p["classes"] = list(f.activity_classes)
        if f.deleted_states:
            vals = [v for v in f.deleted_states if v is not None]
            parts = ["t.deleted_state = ANY(CAST(:del AS text[]))"] if vals else []
            self.p["del"] = vals
            if None in f.deleted_states:
                parts.append("t.deleted_state IS NULL")
            w.append("(%s)" % " OR ".join(parts))
        dated = []
        if f.from_instant:
            dated.append("t.instant >= :fi")
            self.p["fi"] = f.from_instant
        if f.to_instant:
            dated.append("t.instant <= :ti")
            self.p["ti"] = f.to_instant
        if dated:
            w.append("((%s)%s)" % (" AND ".join(dated), " OR t.instant IS NULL" if f.include_no_time else ""))
        elif not f.include_no_time:
            w.append("t.instant IS NOT NULL")
        if f.participants:
            keys = streams._person_keys(conn, f.case_id, f.participants) if f.expand_person_identities else \
                {k: [k] for k in f.participants}
            sets = [[k for k in keys[p] if k != streams.PHONE_OWNER] for p in f.participants]
            if f.participant_mode == "all":
                for i, s in enumerate(sets):
                    w.append("t.identity_keys && CAST(:pk%d AS text[])" % i)
                    self.p["pk%d" % i] = s
            else:
                w.append("t.identity_keys && CAST(:pk AS text[])")
                self.p["pk"] = sorted({k for s in sets for k in s})
        if f.text.query.strip():
            from services.phone import fold as F
            if f.text.exact_characters:
                w.append("EXISTS (SELECT 1 FROM pv_text x WHERE x.record_uid = t.record_uid AND position(:tq in "
                         "lower(x.value)) > 0)")
                self.p["tq"] = F.fold(f.text.query, exact=True)
            else:
                q = F.fold(f.text.query)
                w.append("EXISTS (SELECT 1 FROM pv_text x WHERE x.record_uid = t.record_uid AND x.value_folded LIKE "
                         ":tq)")
                self.p["tq"] = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        self.where = " AND ".join(w)


def _parts(conn, f: TimelineLensFilter):
    sf = _stream_filter(f)
    other_kinds = [k for k in f.lens_kinds if k not in COMM_GROUPS]
    other = _Other(conn, f, other_kinds) if other_kinds and _other_applies(f) else None
    return sf, other


def _lane_key_comm(f, q):
    if f.lane_by == "phone":
        return "ev.extraction_id::text"
    if f.lane_by == "activity_class":
        return "'interaction'"
    if f.lane_by == "kind":
        return ("CASE WHEN ev.kind IN ('call', 'voicemail') THEN 'calls' WHEN ev.kind = 'email' THEN 'emails' "
                "ELSE 'messages' END")
    # person: the first selected participant (in the order chosen) who takes part in the event
    keys = [k for k in f.participants if k != streams.PHONE_OWNER]
    if not keys:
        return "'everyone'"
    return ("coalesce((SELECT k FROM unnest(CAST(%s AS text[])) WITH ORDINALITY AS u(k, n) WHERE EXISTS (SELECT 1 "
            "FROM phone_participations p WHERE p.record_uid = ev.record_uid AND p.generation = ev.generation AND "
            "p.identity_key = u.k) ORDER BY n LIMIT 1), 'others')" % q._p(keys))


def _lane_key_other(f, other):
    if f.lane_by == "phone":
        return "t.extraction_id::text"
    if f.lane_by == "activity_class":
        return "coalesce(t.activity_class, 'unknown')"
    if f.lane_by == "kind":
        return _kind_sql()
    keys = [k for k in f.participants if k != streams.PHONE_OWNER]
    if not keys:
        return "'everyone'"
    other.p["lk"] = keys
    return ("coalesce((SELECT k FROM unnest(CAST(:lk AS text[])) WITH ORDINALITY AS u(k, n) WHERE u.k = "
            "ANY(t.identity_keys) ORDER BY n LIMIT 1), 'others')")


def _union(conn, f, zone, extra_comm=(), extra_other=(), cols=("uid", "src", "instant", "lane")):
    """SQL of the matching entries of both sources with a common shape, and its parameters."""
    sf, other = _parts(conn, f)
    sels, params = [], {}
    if sf is not None:
        q, _ = streams._query(conn, sf)
        lane = _lane_key_comm(f, q)
        inner = q.matched_sql(list(extra_comm))
        # the lane expression refers to ev: compute it inside the matched rows
        sels.append("SELECT m.event_uid AS uid, 'comm' AS src, m.sort_instant AS instant, m.lane FROM (%s) m WHERE %s"
                    % (inner.replace("SELECT ev.*,", "SELECT ev.*, %s AS lane," % lane, 1), streams._shown(sf)))
        params.update(q.params)
    if other is not None:
        lane = _lane_key_other(f, other)
        w = other.where + "".join(" AND " + x for x in extra_other)
        sels.append("SELECT t.entry_uid AS uid, 'other' AS src, t.instant, %s AS lane FROM pv_timeline_entry t WHERE %s"
                    % (lane, w))
        params.update(other.p)
    if not sels:
        sels.append("SELECT NULL::uuid AS uid, NULL::text AS src, NULL::timestamptz AS instant, NULL::text AS lane "
                    "WHERE false")
    return " UNION ALL ".join(sels), params


def _lane_labels(conn, f, keys) -> dict:
    if f.lane_by == "phone":
        from services.phone import readings
        names = readings.phone_labels(conn, f.case_id)
        return {k: names.get(k, "A phone") for k in keys}
    if f.lane_by == "activity_class":
        return {k: CLASS_WORDS.get(k, k) for k in keys}
    if f.lane_by == "kind":
        return {k: KIND_WORDS.get(k, k) for k in keys}
    from services.phone import labels as L
    ctx = L.LabelContext(conn, f.case_id, f.names.mode)
    ctx.load([k for k in keys if k not in ("others", "everyone")])
    out = {}
    for k in keys:
        if k == "others":
            out[k] = "Others"
        elif k == "everyone":
            out[k] = "Everyone"
        else:
            lab = ctx.label(None, identity_key=k)
            out[k] = lab["name"] or (lab["identifier"] or {}).get("display") or k
    return out


def hidden_counts(conn, f: TimelineLensFilter) -> dict:
    """The device events and sensor readings of the case's phones (in scope) that the lens is not showing (T-7)."""
    shown = set(f.lens_kinds)
    p = {"case": f.case_id, "phones": f.phones or None}
    rows = conn.execute(text(
        "SELECT %s AS k, count(*) FROM pv_timeline_entry t WHERE t.case_id = :case AND (t.is_event_time OR t.instant "
        "IS NULL) AND (CAST(:phones AS uuid[]) IS NULL OR t.extraction_id = ANY(CAST(:phones AS uuid[]))) AND %s IN "
        "('device', 'sensor') GROUP BY 1" % (_kind_sql(), _kind_sql())), p).fetchall()
    counts = {k: int(n) for k, n in rows if k not in shown}
    n = sum(counts.values())
    words = None
    if n:
        words = "%s device %s and sensor readings hidden." % ("{:,}".format(n), "event" if n == 1 else "events")
    return {"count": n, "by_kind": counts, "words": words}


def index(conn, f: TimelineLensFilter) -> dict:
    zone = streams.resolve_zone(conn, f)
    zn = "UTC" if T.is_utc(zone["name"]) else zone["name"]
    sql, p = _union(conn, f, zone)
    p["zone"] = zn
    rows = conn.execute(text(
        "WITH u AS (%s) SELECT CASE WHEN instant IS NULL THEN NULL ELSE (instant AT TIME ZONE :zone)::date END AS "
        "day, lane, src, count(*) AS n FROM u GROUP BY 1, 2, 3" % sql), p).fetchall()
    days, lanes, no_time, comm = {}, {}, 0, 0
    for r in rows:
        n = int(r.n)
        lanes[r.lane] = lanes.get(r.lane, 0) + n
        comm += n if r.src == "comm" else 0
        if r.day is None:
            no_time += n
            continue
        d = days.setdefault(r.day, {"count": 0, "by_lane": {}})
        d["count"] += n
        d["by_lane"][r.lane] = d["by_lane"].get(r.lane, 0) + n
    order = sorted(days, reverse=f.sort == "newest_first")
    labels = _lane_labels(conn, f, list(lanes))
    total = sum(lanes.values())
    out = streams.envelope(conn, f, counts={"entries": total, "events": total, "communications": comm,
                                            "other": total - comm, "no_time": no_time})
    out.update({
        "snapshot": snapshot(conn, f),
        "items": [{"day": d.isoformat(), "count": days[d]["count"], "by_lane": days[d]["by_lane"],
                   "offsets": T.day_offsets(d, zone["name"]), "header": T.format_day_header(d),
                   "zone_label": T.zone_label(d, zone["name"])} for d in order],
        "no_time_position": "first" if f.sort == "newest_first" else "last", "sort": f.sort,
        "no_time_count": no_time, "total": total,
        "lanes": sorted(({"key": k, "label": labels.get(k, k), "count": n} for k, n in lanes.items()),
                        key=lambda x: (x["label"] or "", x["key"])),
        "hidden": hidden_counts(conn, f), "full_load_rows": streams.FULL_LOAD_ROWS,
        "zone": {"name": zone["name"], "label": zone["display_name"], "basis": zone["basis"], "mode": zone["mode"],
                 "note": zone["note"]},
        "kinds": [{"key": k, "label": KIND_WORDS[k], "on": k in f.lens_kinds} for k in KIND_WORDS],
        "comm_filter_applies": _stream_filter(f) is not None, "other_filter_applies": _other_applies(f)})
    return out


def window(conn, f: TimelineLensFilter, *, snapshot_token, day, offset=0, limit=200) -> dict:
    if snapshot(conn, f) != snapshot_token:
        raise streams.StaleSnapshot()
    limit = max(1, min(int(limit), WINDOW_MAX))
    zone = streams.resolve_zone(conn, f)
    day_d = date.fromisoformat(day) if day else None
    if day_d is None:
        ec, eo = ["ev.sort_instant IS NULL"], ["t.instant IS NULL"]
        bounds = {}
    else:
        start, end = T.day_bounds(day_d, zone["name"])
        ec = ["ev.sort_instant >= CAST(:d0 AS timestamptz)", "ev.sort_instant < CAST(:d1 AS timestamptz)"]
        eo = ["t.instant >= CAST(:d0 AS timestamptz)", "t.instant < CAST(:d1 AS timestamptz)"]
        bounds = {"d0": start, "d1": end}
    sql, p = _union(conn, f, zone, ec, eo)
    p.update(bounds)
    d = "DESC" if f.sort == "newest_first" else "ASC"
    page = conn.execute(text("WITH u AS (%s) SELECT uid, src, lane FROM u ORDER BY instant %s, src, uid %s OFFSET %d "
                             "LIMIT %d" % (sql, d, d, max(0, int(offset)), limit)), p).fetchall()
    comm_ids = [r.uid for r in page if r.src == "comm"]
    other_ids = [r.uid for r in page if r.src == "other"]
    rows = {}
    sf = _stream_filter(f)
    if comm_ids and sf is not None:
        q, ctx = streams._query(conn, sf)
        q.params["ids"] = comm_ids
        found = conn.execute(text("WITH m AS (%s) SELECT * FROM m WHERE event_uid = ANY(CAST(:ids AS uuid[]))"
                                  % q.matched_sql()), q.params).fetchall()
        for r, built in zip(found, streams.build_rows(conn, ctx, found, zone["name"], sf)):
            rows[str(r.event_uid)] = dict(built, model_type=None, field_path=None, field_meaning=None,
                                          activity_class="interaction",
                                          lens_kind="calls" if built["kind"] in ("call", "voicemail") else
                                          "emails" if built["kind"] == "email" else "messages")
    if other_ids:
        from services.phone import readings
        names = readings.phone_labels(conn, f.case_id)
        for r in conn.execute(text(
                "SELECT t.*, %s AS lens_kind FROM pv_timeline_entry t WHERE t.case_id = :c AND t.entry_uid = "
                "ANY(CAST(:ids AS uuid[]))" % _kind_sql()), {"c": f.case_id, "ids": other_ids}):
            ext = str(r.extraction_id)
            # the StreamRow shape (03 4.5), so the one phone list shows, badges and copies it like a message
            rows[str(r.entry_uid)] = {
                "event_uid": str(r.entry_uid), "record_uid": str(r.record_uid), "kind": "record",
                "phone": {"extraction_id": ext, "label": names.get(ext, "A phone")}, "app": None, "thread": None,
                "direction": "none",
                "time": T.time_block(r.instant, zone["name"], offset_present=r.instant is not None,
                                     time_field=r.field_path),
                "from": None, "to": [], "body": r.summary,
                "subject": "%s: %s" % (KIND_WORDS.get(r.lens_kind, "Record"), r.model_type),
                "call": None, "attachments": [], "flags": ["deleted"] if r.deleted_state else [],
                "copies": {"count": 1, "record_uids": [str(r.record_uid)], "apps": []},
                "owner_read": {"date_read": None, "date_played": None},
                "interpretation_level": r.interpretation_level or "generic", "line": "",
                "model_type": r.model_type, "field_path": r.field_path, "field_meaning": r.field_meaning,
                "activity_class": r.activity_class or "unknown", "lens_kind": r.lens_kind}
    labels = _lane_labels(conn, f, sorted({r.lane for r in page}))
    items = []
    for r in page:
        x = rows.get(str(r.uid))
        if x is None:
            continue
        items.append(dict(x, entry_uid=str(r.uid), event_uid=str(r.uid), source=r.src, lane_key=r.lane,
                          lane_label=labels.get(r.lane)))
    return streams.envelope(conn, f, items=items)


def _no_data_hours(conn, ext, start, end) -> set:
    from services.pattern_of_life import availability
    try:
        # no hourly rollup built for this phone yet: no claim either way, never "No data" by default
        if not conn.execute(text("SELECT to_regclass('pol_hourly_rollup') IS NOT NULL")).scalar() or \
                not conn.execute(text("SELECT EXISTS (SELECT 1 FROM pol_hourly_rollup WHERE extraction_id = :e)"),
                                 {"e": ext}).scalar():
            return set()
        states = availability.hour_states(conn, ext, start, end)
    except Exception:  # noqa: BLE001 (04's tables not built for this phone: no claim either way)
        return set()
    return {s["hour_utc"] for s in states if s["state"] in ("no_data", "after_extraction", "powered_off")}


def buckets(conn, f: TimelineLensFilter, *, snapshot_token, start: datetime, end: datetime,
            bucket: Literal["hour", "day"]) -> dict:
    """Counts per lane per hour or day in the display zone. A phone lane's bucket is ``no_data`` when the phone holds
    no data for the whole bucket (04 hour states), which the screen draws as a hatched band, never as zero."""
    if snapshot(conn, f) != snapshot_token:
        raise streams.StaleSnapshot()
    if end <= start:
        raise ValueError("The end of the span must be after its start.")
    if bucket == "hour" and end - start > timedelta(days=7):
        raise ValueError("Hourly lanes cover at most 7 days; choose days for a longer span.")
    if bucket == "day" and end - start > timedelta(days=3700):
        raise ValueError("Daily lanes cover at most ten years.")
    zone = streams.resolve_zone(conn, f)
    zn = "UTC" if T.is_utc(zone["name"]) else zone["name"]
    tz = T.tz(zone["name"])
    step = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)
    first = start.astimezone(tz).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    if bucket == "day":
        first = first.replace(hour=0)
    walls = []
    w = first
    while w.replace(tzinfo=tz) < end:
        walls.append(w)
        w = w + step
    # every bucket is whole: rows are counted from the first bucket's start to the last bucket's end in the display
    # zone, so a day's mark equals the day's list
    b0 = walls[0].replace(tzinfo=tz).astimezone(timezone.utc)
    b1 = (walls[-1] + step).replace(tzinfo=tz).astimezone(timezone.utc)
    ec = ["ev.sort_instant >= CAST(:b0 AS timestamptz)", "ev.sort_instant < CAST(:b1 AS timestamptz)"]
    eo = ["t.instant >= CAST(:b0 AS timestamptz)", "t.instant < CAST(:b1 AS timestamptz)"]
    sql, p = _union(conn, f, zone, ec, eo)
    p.update({"b0": b0, "b1": b1, "zone": zn})
    rows = conn.execute(text(
        "WITH u AS (%s) SELECT lane, date_trunc('%s', instant AT TIME ZONE :zone) AS b, count(*) AS n FROM u GROUP BY "
        "1, 2" % (sql, bucket)), p).fetchall()
    counts = {}
    for r in rows:
        counts.setdefault(r.lane, {})[r.b] = int(r.n)
    lane_keys = sorted(counts)
    if f.lane_by == "phone":
        phones = f.phones or [str(e) for (e,) in conn.execute(text(
            "SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active'"), {"c": f.case_id})]
        lane_keys = sorted(set(lane_keys) | set(phones))
    labels = _lane_labels(conn, f, lane_keys)
    out = []
    for k in lane_keys:
        gaps = _no_data_hours(conn, k, b0, b1) if f.lane_by == "phone" else set()
        bs = []
        for wall in walls:
            s = wall.replace(tzinfo=tz).astimezone(timezone.utc)
            e = (wall + step).replace(tzinfo=tz).astimezone(timezone.utc)
            n = counts.get(k, {}).get(wall, 0)
            hours = []
            h = s.replace(minute=0, second=0, microsecond=0)
            while h < e:
                hours.append(h)
                h += timedelta(hours=1)
            no_data = bool(gaps) and n == 0 and all(h in gaps for h in hours)
            bs.append({"start": s.isoformat(), "wall": wall.isoformat(), "count": n, "no_data": no_data})
        out.append({"key": k, "label": labels.get(k, k), "buckets": bs})
    return {"case_id": f.case_id, "bucket": bucket, "zone": zone["name"], "lanes": out,
            "no_data_words": "No data", "empty_words": "No matching entries"}
