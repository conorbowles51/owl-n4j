"""The one query for communication events (docs/cellebrite/03 sections 3.1, 4.5, 4.7; D-1, D-4).

Every screen that lists messages, calls, emails, voicemail or group activity (Conversations, the Timeline lens,
the Search pivot, Export, Graph edge detail, People counts) calls these functions with the same ``StreamFilter``;
no screen writes its own join, so the same question gives the same count everywhere (A3).

- ``index_comm_events``: the exact total under the filter, per-day counts in the display zone, the count with no
  time, the copies collapsed, and a snapshot token.
- ``window_comm_events``: rows of one day (or the no-time group) by offset within that day, against the same
  snapshot. The offset is bounded by one day's count, so deep scrolling never scans earlier days.
- ``locate_comm_event``: the day and offset of one event, so any screen can open a stream at it.

Rules carried here:

- **Rows without time are never dropped** (3.1 rule 5): they form the ``No time recorded`` group, counted in every
  total; newest first puts the group first.
- **Both sides of a call.** A party row with role ``owner_implicit`` (02 fills it when the record names no owner
  party) and a party marked as the phone's owner with no identifier both stand for the phone's owner, so a
  participant filter on the owner's number finds them (C-4; the cause of v1's one-call defect).
- **Copies** (3.4): with ``collapse_copies`` one row per ``dup_group_uid`` among the matching copies (the copy with
  the most fields filled, then the lowest record id), and ``copies`` lists every copy. ``Show every copy`` lists
  each record.
- Sort is by instant then ``event_uid`` (3.2), so equal times keep one order on every screen and reload.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import text

from services.phone import fold as F
from services.phone import labels as L
from services.phone import time_display as T
from services.phone.filters import StreamFilter, snapshot

WINDOW_MAX = 1000
FULL_LOAD_ROWS = 5000  # D-2, settled from 03 section 20.3: see 03 section 19
SENDER_SQL = "(p.role IN ('sender','caller','author','original_sender') OR p.implied_role IN ('sender','caller'))"
RECIPIENT_SQL = "(p.role IN ('recipient','cc','bcc','callee') OR p.implied_role IN ('recipient','callee'))"
PARTY_KEY_SQL = ("coalesce(p.identity_key, CASE WHEN p.role = 'owner_implicit' OR p.is_phone_owner IS TRUE "
                 "THEN ok.k END)")
CALL_STATUS = {"established": "answered", "missed": "missed", "rejected": "declined", "canceled": "cancelled",
               "cancelled": "cancelled", "busyline": "busy", "voicemail": "went to voicemail",
               "notestablishedunknownreason": "not connected", "unknown": "status not recorded"}
GROUP_CHAT_TYPES = ("Group", "Broadcast")
NO_THREAD_PREFIX = "none:"
NO_THREAD_TITLE = "Not in a conversation"


class StaleSnapshot(Exception):
    """A window asked for under a snapshot that no longer matches (3.1 rule 3): HTTP 409 ``stale_snapshot``."""


class NotInCase(LookupError):
    pass


# ---- zone ----------------------------------------------------------------------------------------------------------

def case_zone(conn, case_id) -> dict:
    """The case time zone (4.6): the setting; else the phones' device zone when they all share one; else UTC."""
    z = conn.execute(text("SELECT time_zone FROM case_display_settings WHERE case_id = :c"), {"c": case_id}).scalar()
    if z:
        return {"name": z, "basis": "case_setting", "note": None}
    zones = [r[0] for r in conn.execute(text(
        "SELECT device_zone FROM pv_extraction WHERE case_id = :c AND standing = 'active'"), {"c": case_id})]
    if zones and all(zones) and len(set(zones)) == 1:
        if T.valid_zone(zones[0]):
            return {"name": zones[0], "basis": "phones_device_zone", "note": None}
        return {"name": "UTC", "basis": "utc_default",
                "note": "The time zone in the report is not one Loupe recognises. Times are shown in UTC."}
    note = ("Phones in this case are in different or unknown time zones. Times are shown in UTC." if zones else None)
    return {"name": "UTC", "basis": "utc_default", "note": note}


def resolve_zone(conn, f: StreamFilter) -> dict:
    """The zone a list is shown in (3.2): phone, case or UTC, with its basis and any fallback stated."""
    mode = f.zone.mode
    if mode == "utc":
        out = {"name": "UTC", "basis": "chosen_utc", "note": None}
    elif mode == "phone":
        phone = f.zone.phone or (f.phones[0] if len(f.phones) == 1 else None)
        row = conn.execute(text(
            "SELECT device_zone, device_zone_basis FROM pv_extraction WHERE extraction_id = CAST(:e AS uuid) AND "
            "case_id = :c"), {"e": phone, "c": f.case_id}).first() if phone else None
        if row and row.device_zone:
            out = {"name": row.device_zone, "basis": row.device_zone_basis or "device_metadata", "note": None}
        else:
            out = case_zone(conn, f.case_id)
            out["note"] = "This phone's time zone is not stated in the report. Times are shown in the case time zone."
    else:
        out = case_zone(conn, f.case_id)
    if not T.valid_zone(out["name"]):
        # The report's zone text is kept as written when it is not a zone name (capture flag
        # device_zone_not_a_zone_name); the list is shown in UTC and says so, as thread documents do.
        out = {"name": "UTC", "basis": "utc_default",
               "note": "The time zone in the report is not one Loupe recognises. Times are shown in UTC."}
    out["mode"] = mode
    out["display_name"] = T.zone_name(out["name"])
    return out


# ---- the filter as SQL ---------------------------------------------------------------------------------------------

def _person_keys(conn, case_id, keys) -> dict:
    """``{key: [every key linked to the same person]}`` for ``expand_person_identities``."""
    out = {k: [k] for k in keys}
    for r in conn.execute(text(
            "SELECT a.identity_key AS k, array_agg(DISTINCT b.identity_key) AS ks FROM pv_identity a JOIN pv_identity b "
            "ON b.case_id = a.case_id AND b.person_id = a.person_id WHERE a.case_id = :c AND a.person_id IS NOT NULL "
            "AND a.identity_key = ANY(:k) GROUP BY a.identity_key"), {"c": case_id, "k": list(keys)}):
        out[r.k] = sorted(set(r.ks) | {r.k})
    return out


class Query:
    """The WHERE clause and parameters of one ``StreamFilter`` over ``phone_comm_events ev`` at the current generation
    of active phones (the rows ``pv_comm_event`` returns), with ``ok`` the owner key of each phone."""

    def __init__(self, conn, f: StreamFilter, owner_keys: dict):
        self.conn, self.f = conn, f
        self.params = {"case": f.case_id,
                       "oe": [e for e in owner_keys if owner_keys[e]],
                       "ok": [owner_keys[e][0] for e in owner_keys if owner_keys[e]]}
        self.where = ["ev.case_id = :case"]
        self._n = 0
        self._build()

    def _p(self, value):
        self._n += 1
        name = "p%d" % self._n
        self.params[name] = value
        return ":" + name

    FROM = ("phone_comm_events ev "
            "JOIN phone_interpretation_state st ON st.extraction_id = ev.extraction_id AND st.generation = ev.generation "
            "JOIN phone_extractions e ON e.id = ev.extraction_id AND e.standing = 'active' "
            "LEFT JOIN unnest(CAST(:oe AS uuid[]), CAST(:ok AS text[])) AS ok(e, k) ON ok.e = ev.extraction_id")

    def party(self, keys, side=None):
        cond = {"s": SENDER_SQL, "r": RECIPIENT_SQL, None: "true"}[side]
        return ("EXISTS (SELECT 1 FROM phone_participations p WHERE p.record_uid = ev.record_uid AND "
                "p.generation = ev.generation AND %s AND %s = ANY(CAST(%s AS text[])))" % (cond, PARTY_KEY_SQL,
                                                                                         self._p(list(keys))))

    def is_group(self):
        return ("(EXISTS (SELECT 1 FROM phone_threads t WHERE t.thread_key = ev.thread_key AND t.generation = "
                "ev.generation AND t.chat_type IN ('Group','Broadcast')) OR (SELECT count(DISTINCT %s) FROM "
                "phone_participations p WHERE p.record_uid = ev.record_uid AND p.generation = ev.generation) > 2)"
                % PARTY_KEY_SQL)

    def member(self, keys):
        return "(%s OR EXISTS (SELECT 1 FROM phone_threads t WHERE t.thread_key = ev.thread_key AND t.generation = " \
               "ev.generation AND t.party_identity_keys && CAST(%s AS text[])))" % (self.party(keys),
                                                                                   self._p(list(keys)))

    def _build(self):
        f, w = self.f, self.where
        if f.phones:
            w.append("ev.extraction_id = ANY(CAST(%s AS uuid[]))" % self._p(f.phones))
        if f.threads:
            # "none:<phone>" is the pseudo-thread of a phone's events that sit in no conversation (thread_list).
            keys = [t for t in f.threads if not t.startswith(NO_THREAD_PREFIX)]
            loose = [t[len(NO_THREAD_PREFIX):] for t in f.threads if t.startswith(NO_THREAD_PREFIX)]
            parts = []
            if keys:
                parts.append("ev.thread_key = ANY(CAST(%s AS text[]))" % self._p(keys))
            if loose:
                parts.append("(ev.thread_key IS NULL AND ev.extraction_id::text = ANY(CAST(%s AS text[])))"
                             % self._p(loose))
            w.append("(%s)" % " OR ".join(parts))
        if f.apps:
            w.append("ev.app = ANY(CAST(%s AS text[]))" % self._p(f.apps))
        if f.kinds:
            w.append("ev.kind = ANY(CAST(%s AS text[]))" % self._p(list(f.kinds)))
        if f.directions:
            w.append("ev.direction = ANY(CAST(%s AS text[]))" % self._p(list(f.directions)))
        if f.deleted_states:
            vals = [v for v in f.deleted_states if v is not None]
            parts = ["ev.deleted_state = ANY(CAST(%s AS text[]))" % self._p(vals)] if vals else []
            if None in f.deleted_states:
                parts.append("ev.deleted_state IS NULL")
            w.append("(%s)" % " OR ".join(parts))
        dated = []
        if f.from_instant:
            dated.append("ev.sort_instant >= %s" % self._p(f.from_instant))
        if f.to_instant:
            dated.append("ev.sort_instant <= %s" % self._p(f.to_instant))
        if dated:
            w.append("((%s)%s)" % (" AND ".join(dated), " OR ev.sort_instant IS NULL" if f.include_no_time else ""))
        elif not f.include_no_time:
            w.append("ev.sort_instant IS NOT NULL")
        self._flags()
        if f.text.query.strip():
            if f.text.exact_characters:
                q = F.fold(f.text.query, exact=True)
                cond = "position(%s in lower(t.effective_value)) > 0" % self._p(q)
            else:
                q = F.fold(f.text.query)
                cond = "t.value_folded LIKE %s" % self._p("%" + q.replace("\\", "\\\\").replace("%", "\\%")
                                                           .replace("_", "\\_") + "%")
            if q:
                w.append("EXISTS (SELECT 1 FROM phone_texts t WHERE t.extraction_id = ev.extraction_id AND "
                         "t.generation = ev.generation AND (t.record_uid = ev.record_uid OR t.record_uid IN (SELECT "
                         "s.record_uid FROM phone_record_summaries s WHERE s.parent_record_uid = ev.record_uid AND "
                         "s.generation = ev.generation)) AND %s)" % cond)
        self._participants()

    def _flags(self):
        fl, w = self.f.flags, self.where

        def tri(value, cond):
            if value is True:
                w.append(cond)
            elif value is False:
                w.append("NOT %s" % cond)

        tri(fl.carved, "false")  # no production marks carving yet (02 section 12.2: is_carved false)
        tri(fl.unreadable, "EXISTS (SELECT 1 FROM phone_record_summaries s WHERE s.parent_record_uid = ev.record_uid "
                           "AND s.generation = ev.generation AND s.model_type = 'ScrambledMessageData')")
        tri(fl.synced, "EXISTS (SELECT 1 FROM phone_record_summaries s WHERE s.record_uid = ev.record_uid AND "
                       "s.generation = ev.generation AND lower(coalesce(s.user_mapping, '')) LIKE 'sync%')")
        tri(fl.has_attachment, "EXISTS (SELECT 1 FROM phone_file_references r WHERE r.extraction_id = ev.extraction_id "
                               "AND r.document_index = ev.document_index AND (r.record_ordinal = ev.ordinal OR "
                               "r.record_ordinal IN (SELECT s.ordinal FROM phone_record_summaries s WHERE "
                               "s.parent_record_uid = ev.record_uid AND s.generation = ev.generation)))")

    def _participants(self):
        f = self.f
        if not f.participants:
            self.between_groups = None
            return
        expand = _person_keys(self.conn, f.case_id, f.participants) if f.expand_person_identities else \
            {k: [k] for k in f.participants}
        sets = [expand[k] for k in f.participants]
        mode, w = f.participant_mode, self.where
        self.between_groups = None
        if mode == "any":
            w.append(self.party(sorted({k for s in sets for k in s})))
        elif mode == "all":
            w.extend(self.party(s) for s in sets)
        elif mode == "sent_by":
            w.append(self.party(sets[0], "s"))
            if len(sets) == 2:
                w.append(self.party(sets[1], "r"))
        elif mode == "sent_to":
            w.append(self.party(sets[0], "r"))
            if len(sets) == 2:
                w.append(self.party(sets[1], "s"))
        else:  # between
            a, b = sets
            direct = "((%s AND %s) OR (%s AND %s))" % (self.party(a, "s"), self.party(b, "r"), self.party(b, "s"),
                                                       self.party(a, "r"))
            group = "((%s AND %s) OR (%s AND %s))" % (self.party(a, "s"), self.member(b), self.party(b, "s"),
                                                      self.member(a))
            if f.group_scope == "direct":
                self.between_index = len(w)
                w.append("(%s AND NOT %s)" % (direct, self.is_group()))
                self.between_groups = "(%s AND %s)" % (group, self.is_group())
            else:
                w.append("((%s AND NOT %s) OR (%s AND %s))" % (direct, self.is_group(), group, self.is_group()))

    def where_sql(self, extra=()):
        return " AND ".join(list(self.where) + list(extra))

    def matched_sql(self, extra=()):
        """Matching events with the copy rank and count (3.4)."""
        populated = ("(ev.body IS NOT NULL)::int + (ev.subject IS NOT NULL)::int + (ev.app IS NOT NULL)::int + "
                     "(ev.sort_instant IS NOT NULL)::int + (ev.thread_key IS NOT NULL)::int + "
                     "(ev.call_duration_s IS NOT NULL)::int + (ev.status IS NOT NULL)::int")
        grp = "coalesce(ev.extraction_id::text || ':' || ev.dup_group_uid, ev.event_uid::text)"
        return ("SELECT ev.*, row_number() OVER (PARTITION BY %s ORDER BY %s DESC, ev.record_uid) AS copy_rank, "
                "count(*) OVER (PARTITION BY %s) AS copy_count FROM %s WHERE %s"
                % (grp, populated, grp, self.FROM, self.where_sql(extra)))


def _query(conn, f, ctx=None):
    ctx = ctx or L.LabelContext(conn, f.case_id, f.names.mode)
    return Query(conn, f, {e: o["keys"] for e, o in ctx.owners.items()}), ctx


def _shown(f):
    return "copy_rank = 1" if f.collapse_copies else "true"


def limits_for(conn, f: StreamFilter) -> list:
    """A phone in scope that is still being read, failed or was only partly read (3.8, 4.2)."""
    rows = conn.execute(text(
        "SELECT extraction_id, state FROM pv_extraction WHERE case_id = :c AND standing = 'active' AND state <> "
        "'ingested'" + (" AND extraction_id = ANY(CAST(:p AS uuid[]))" if f.phones else "")),
        {"c": f.case_id, "p": f.phones}).fetchall()
    if not rows:
        return []
    from services.phone import readings
    names = readings.phone_labels(conn, f.case_id)
    out = []
    for ext, state in rows:
        label = names.get(str(ext), "A phone")
        msg = ("%s's report could only be partly read. Results from %s are incomplete. See Phone summary."
               % (label, label)) if state in ("partial", "failed") else \
            "%s is still being read. Results will be incomplete until it finishes." % label
        out.append({"kind": "phone_incomplete", "phone": str(ext), "state": state, "shown": None, "total": None,
                    "message": msg})
    return out


def shown_count(conn, f: StreamFilter) -> int:
    """How many rows the list under ``f`` shows (copies collapsed when the filter collapses them): the number a
    count elsewhere must equal when it links to that list."""
    q, _ = _query(conn, f)
    return int(conn.execute(text("WITH m AS (%s) SELECT count(*) FROM m WHERE %s" % (q.matched_sql(), _shown(f))),
                            q.params).scalar() or 0)


# ---- index ---------------------------------------------------------------------------------------------------------

def index_comm_events(conn, f: StreamFilter) -> dict:
    """Envelope (4.2) with ``items: [{day, count, offsets}]`` in the display zone, ``no_time_count``, ``zone`` and,
    for ``between`` under ``direct``, ``group_totals``."""
    q, _ = _query(conn, f)
    zone = resolve_zone(conn, f)
    q.params["zone"] = "UTC" if T.is_utc(zone["name"]) else zone["name"]
    rows = conn.execute(text(
        "WITH m AS (%s) SELECT CASE WHEN sort_instant IS NULL THEN NULL ELSE (sort_instant AT TIME ZONE :zone)::date "
        "END AS day, count(*) FILTER (WHERE %s) AS n, count(*) AS records FROM m GROUP BY 1"
        % (q.matched_sql(), _shown(f))), q.params).fetchall()
    days = sorted(((r.day, int(r.n)) for r in rows if r.day is not None and r.n), key=lambda x: x[0],
                  reverse=f.sort == "newest_first")
    no_time = sum(int(r.n) for r in rows if r.day is None)
    events = sum(int(r.n) for r in rows)
    records = sum(int(r.records) for r in rows)
    out = envelope(conn, f, counts={"events": events, "records": records, "collapsed_copies": records - events,
                                    "no_time": no_time},
                   items=[{"day": d.isoformat(), "count": n, "offsets": T.day_offsets(d, zone["name"]),
                           "header": T.format_day_header(d), "zone_label": T.zone_label(d, zone["name"])}
                          for d, n in days])
    out["no_time_count"] = no_time
    out["zone"] = {"name": zone["name"], "label": zone["display_name"], "basis": zone["basis"], "mode": zone["mode"],
                   "note": zone["note"]}
    out["full_load_rows"] = FULL_LOAD_ROWS
    out["no_time_position"] = "first" if f.sort == "newest_first" else "last"
    out["sort"] = f.sort
    if q.between_groups:
        g = conn.execute(text("SELECT count(*) AS events, count(DISTINCT ev.thread_key) AS threads FROM %s WHERE %s"
                              % (q.FROM, " AND ".join([w for i, w in enumerate(q.where) if i != q.between_index] +
                                                       [q.between_groups]))), q.params).first()
        out["group_totals"] = {"threads": int(g.threads), "events": int(g.events)}
    return out


def envelope(conn, f, *, counts=None, items=(), limits=None) -> dict:
    lim = limits_for(conn, f) if limits is None else limits
    return {"case_id": f.case_id, "snapshot": snapshot(conn, f), "complete": not lim, "limits": lim,
            "counts": counts or {}, "items": list(items)}


# ---- window --------------------------------------------------------------------------------------------------------

def _day_cond(q, f, zone, day):
    if day is None:
        return ["ev.sort_instant IS NULL"]
    start, end = T.day_bounds(day, zone)
    return ["ev.sort_instant >= %s" % q._p(start), "ev.sort_instant < %s" % q._p(end)]


def _order(f, day):
    if day is None:
        return "event_uid"
    d = "DESC" if f.sort == "newest_first" else "ASC"
    return "sort_instant %s, event_uid %s" % (d, d)


def window_comm_events(conn, f: StreamFilter, *, snapshot_token, day, offset=0, limit=200) -> dict:
    if snapshot(conn, f) != snapshot_token:
        raise StaleSnapshot()
    limit = max(1, min(int(limit), WINDOW_MAX))
    q, ctx = _query(conn, f)
    zone = resolve_zone(conn, f)
    day_d = date.fromisoformat(day) if day else None
    # Copies are ranked inside the day: under rule v1 every copy of a group has the same instant, so a group never
    # spans two days and the ranks equal those the index counted (3.4; tested by the window sums).
    rows = conn.execute(text(
        "WITH m AS (%s) SELECT * FROM m WHERE %s ORDER BY %s OFFSET %d LIMIT %d"
        % (q.matched_sql(_day_cond(q, f, zone["name"], day_d)), _shown(f), _order(f, day_d), max(0, int(offset)),
           limit)), q.params).fetchall()
    items = build_rows(conn, ctx, rows, zone["name"], f)
    return envelope(conn, f, items=items)


def locate_comm_event(conn, f: StreamFilter, *, snapshot_token, event_uid) -> dict:
    if snapshot(conn, f) != snapshot_token:
        raise StaleSnapshot()
    q, _ = _query(conn, f)
    zone = resolve_zone(conn, f)
    q.params["target"] = event_uid
    row = conn.execute(text("WITH m AS (%s) SELECT sort_instant, event_uid, extraction_id, dup_group_uid, %s AS shown "
                            "FROM m WHERE event_uid = CAST(:target AS uuid)" % (q.matched_sql(), _shown(f))),
                       q.params).first()
    if row is None:
        raise NotInCase("event not in this result")
    if not row.shown:
        # A collapsed copy: the list shows its group's displayed copy, so that is where the reader lands (3.4).
        q.params.update(ge=row.extraction_id, gd=row.dup_group_uid)
        row = conn.execute(text("WITH m AS (%s) SELECT sort_instant, event_uid FROM m WHERE copy_rank = 1 AND "
                                "extraction_id = :ge AND dup_group_uid = :gd" % q.matched_sql()), q.params).first()
        q.params["target"] = row.event_uid
    day = T.day_of(row.sort_instant, zone["name"]) if row.sort_instant else None
    cmp = ">" if f.sort == "newest_first" else "<"
    before = ("(sort_instant, event_uid) %s (CAST(:ti AS timestamptz), CAST(:target AS uuid))" % cmp) if day else \
        "event_uid < CAST(:target AS uuid)"
    q.params["ti"] = row.sort_instant
    n = conn.execute(text("WITH m AS (%s) SELECT count(*) FROM m WHERE %s AND %s"
                          % (q.matched_sql(_day_cond(q, f, zone["name"], day)), _shown(f), before)),
                     q.params).scalar()
    return {"day": day.isoformat() if day else None, "offset": int(n)}


# ---- rows ----------------------------------------------------------------------------------------------------------

def call_words(row) -> str | None:
    if row.kind != "call":
        return None
    parts = ["Video call" if row.video else "Call"]
    if row.call_duration_s is not None:
        s = int(round(float(row.call_duration_s)))
        m, s = divmod(s, 60)
        parts.append(("%d min %d s" % (m, s)) if m else "%d s" % s)
    st = (row.call_status or "").replace(" ", "").lower()
    if st:
        parts.append(CALL_STATUS.get(st, row.call_status))
    return ", ".join(parts)


def build_rows(conn, ctx: L.LabelContext, rows, zone: str, f: StreamFilter) -> list:
    """``StreamRow`` (03 section 4.5) for each event row, with labels, attachments, copies and badges."""
    if not rows:
        return []
    uids = [r.record_uid for r in rows]
    parties = defaultdict(list)
    for p in conn.execute(text(
            "SELECT p.record_uid, p.identity_key, p.role, p.implied_role, p.role_in_record, p.name_in_record, "
            "p.identifier_raw, p.is_phone_owner, p.date_read, p.date_played, p.extraction_id FROM phone_participations p "
            "JOIN phone_interpretation_state st ON st.extraction_id = p.extraction_id AND st.generation = p.generation "
            "WHERE p.record_uid = ANY(:u) ORDER BY p.record_uid, p.ordinal, p.participation_uid"), {"u": uids}):
        parties[p.record_uid].append(p)
    ctx.load([p.identity_key for ps in parties.values() for p in ps])
    atts = defaultdict(list)
    for a in conn.execute(text(
            "SELECT coalesce(s.parent_record_uid, a.record_uid) AS owner_uid, a.record_uid, a.file_uid, a.mechanism, "
            "a.reference_text, a.resolved, f.local_path, f.category, f.verification FROM pv_attachment_link a "
            "LEFT JOIN (SELECT s.record_uid, s.parent_record_uid FROM phone_record_summaries s JOIN "
            "phone_interpretation_state st ON st.extraction_id = s.extraction_id AND st.generation = s.generation) s "
            "ON s.record_uid = a.record_uid AND s.record_uid <> ALL(:u) AND s.parent_record_uid = ANY(:u) "
            "LEFT JOIN pv_file f ON f.file_uid = a.file_uid "
            "WHERE a.record_uid = ANY(:u) OR a.record_uid IN (SELECT s2.record_uid FROM phone_record_summaries s2 JOIN "
            "phone_interpretation_state st2 ON st2.extraction_id = s2.extraction_id AND st2.generation = s2.generation "
            "WHERE s2.parent_record_uid = ANY(:u))"), {"u": uids}):
        path = a.local_path or a.reference_text or ""
        atts[a.owner_uid].append({"file_uid": str(a.file_uid) if a.file_uid else None,
                                  "filename": path.replace("\\", "/").rsplit("/", 1)[-1] or None,
                                  "category": a.category, "verification": a.verification if a.file_uid else
                                  ("missing" if not a.resolved else None), "mechanism": a.mechanism})
    copies = defaultdict(list)
    groups = sorted({(str(r.extraction_id), r.dup_group_uid) for r in rows if r.dup_group_uid})
    if groups:
        for c in conn.execute(text(
                "SELECT ev.extraction_id, ev.dup_group_uid, ev.record_uid, ev.app FROM pv_comm_event ev WHERE "
                "ev.case_id = :c AND (ev.extraction_id::text || ':' || ev.dup_group_uid) = ANY(:g) ORDER BY "
                "ev.record_uid"), {"c": f.case_id, "g": ["%s:%s" % g for g in groups]}):
            copies[(str(c.extraction_id), c.dup_group_uid)].append(c)
    titles = {t.thread_key: t.title_in_record for t in conn.execute(text(
        "SELECT thread_key, title_in_record FROM pv_thread WHERE case_id = :c AND thread_key = ANY(:k)"),
        {"c": f.case_id, "k": sorted({r.thread_key for r in rows if r.thread_key})})}
    out = []
    for r in rows:
        ext = str(r.extraction_id)
        ps = parties.get(r.record_uid, [])
        senders = [p for p in ps if p.role in L.SENDER_ROLES or p.implied_role in ("sender", "caller")]
        recips = [p for p in ps if p.role in L.RECIPIENT_ROLES or p.implied_role in ("recipient", "callee")]
        others = [p for p in ps if p not in senders and p not in recips]

        def lab(p):
            return ctx.label(ext, identity_key=p.identity_key, name_in_record=p.name_in_record,
                             identifier_raw=p.identifier_raw, is_phone_owner=p.is_phone_owner, role=p.role)

        frm = lab(senders[0]) if senders else None
        to = [lab(p) for p in recips] or ([lab(p) for p in others] if not senders else [])
        owner_p = next((p for p in ps if p.is_phone_owner or p.role == "owner_implicit"), None)
        group = copies.get((ext, r.dup_group_uid), []) if r.dup_group_uid else []
        flags = row_flags(r)
        row = {
            "event_uid": str(r.event_uid), "record_uid": str(r.record_uid), "kind": r.kind,
            "phone": {"extraction_id": ext, "label": ctx.phone_label(ext)}, "app": r.app,
            "thread": {"thread_key": r.thread_key, "title": titles.get(r.thread_key)} if r.thread_key else None,
            "direction": r.direction,
            "time": T.time_block(r.sort_instant, zone, offset_present=r.sort_instant is not None,
                                 time_field=r.time_field),
            "from": frm, "to": to, "body": r.body, "subject": r.subject,
            "call": {"duration_s": float(r.call_duration_s) if r.call_duration_s is not None else None,
                     "status": r.call_status, "video": r.video, "words": call_words(r)} if r.kind == "call" else None,
            "attachments": atts.get(r.record_uid, []),
            "flags": flags,
            "copies": {"count": int(r.copy_count) if f.collapse_copies else 1,
                       "record_uids": [str(c.record_uid) for c in group] or [str(r.record_uid)],
                       "apps": [c.app for c in group] if group else ([r.app] if r.app else [])},
            "owner_read": {"date_read": T.iso(owner_p.date_read) if owner_p and owner_p.date_read else None,
                           "date_played": T.iso(owner_p.date_played) if owner_p and owner_p.date_played else None},
            "interpretation_level": r.interpretation_level,
        }
        row["line"] = L.line_text(frm, to)
        out.append(row)
    return out


def row_flags(r) -> list:
    """Badge words (3.5) in priority order."""
    flags = []
    if r.interpretation_level == "applied_unconfirmed":
        flags.append("Mapped by the system, not yet confirmed")
    elif r.interpretation_level == "generic":
        flags.append("Generic reading")
    ds = (r.deleted_state or "").lower()
    if ds == "deleted":
        flags.append("Deleted")
    elif ds == "trash":
        flags.append("In trash")
    elif ds == "unknown":
        flags.append("Deletion state unknown")
    if r.sort_instant is None:
        flags.append(T.NO_TIME)
    return flags


# ---- threads -------------------------------------------------------------------------------------------------------

UNREADABLE_SQL = ("EXISTS (SELECT 1 FROM phone_record_summaries s WHERE s.parent_record_uid = m.record_uid AND "
                  "s.generation = m.generation AND s.model_type = 'ScrambledMessageData')")


def thread_list(conn, f: StreamFilter, *, sort: str = "recent") -> dict:
    """Every thread with events under the filter, in one response (03 section 6.3; C-5). ``threads`` in the filter is
    ignored. Each row: phone, app, chat type, title, the first five participants and their count, first and last
    instant, counts under the filter and in total, deleted count, whether any event is unreadable, and the review
    mark (07 section 6.1). A phone's events that sit in no conversation are one more row, "Not in a conversation",
    so the list always covers every matching event."""
    from services.phone import review_marks
    g = f.model_copy(update={"threads": []})
    q, ctx = _query(conn, g)
    zone = resolve_zone(conn, g)
    rows = conn.execute(text(
        "WITH m AS (%s) SELECT m.extraction_id, coalesce(m.thread_key, :none || m.extraction_id::text) AS tk, "
        "count(*) AS n, min(m.sort_instant) AS first_i, max(m.sort_instant) AS last_i, "
        "count(*) FILTER (WHERE lower(coalesce(m.deleted_state, '')) IN ('deleted','trash')) AS deleted, "
        "count(*) FILTER (WHERE %s) AS unreadable, max(m.app) AS app FROM (SELECT m.*, row_number() OVER ("
        "PARTITION BY coalesce(m.extraction_id::text || ':' || m.dup_group_uid, m.event_uid::text), m.thread_key "
        "ORDER BY m.copy_rank) AS thread_rank FROM m) m WHERE %s "
        "GROUP BY m.extraction_id, 2" % (q.matched_sql(), UNREADABLE_SQL,
                                        "thread_rank = 1" if g.collapse_copies else "true")),
        dict(q.params, none=NO_THREAD_PREFIX)).fetchall()
    meta = {t.thread_key: t for t in conn.execute(text(
        "SELECT thread_key, extraction_id, app, thread_kind, chat_type, title_in_record, event_count, "
        "party_identity_keys FROM pv_thread WHERE case_id = :c" + (" AND extraction_id = ANY(CAST(:p AS uuid[]))"
                                                                  if f.phones else "")),
        {"c": f.case_id, "p": f.phones})}
    loose_totals = {str(r[0]): int(r[1]) for r in conn.execute(text(
        "SELECT ev.extraction_id, count(*) FROM phone_comm_events ev JOIN phone_interpretation_state st ON "
        "st.extraction_id = ev.extraction_id AND st.generation = ev.generation JOIN phone_extractions e ON "
        "e.id = ev.extraction_id AND e.standing = 'active' WHERE e.case_id = :c AND ev.thread_key IS NULL "
        "GROUP BY 1"), {"c": f.case_id})}
    total_threads = len(meta) + sum(1 for e in loose_totals if not f.phones or e in f.phones)
    keys = {k for t in meta.values() for k in (t.party_identity_keys or [])[:5]}
    ctx.load(keys)
    marks = review_marks.marks(conn, f.case_id)
    items = []
    for r in rows:
        ext = str(r.extraction_id)
        loose = r.tk.startswith(NO_THREAD_PREFIX)
        t = None if loose else meta.get(r.tk)
        members = list(t.party_identity_keys or []) if t else []
        labels = [ctx.label(ext, identity_key=k) for k in members[:5]]
        names = [lab["name"] or L.identifier_text(lab["identifier"]) or L.NO_NAME for lab in labels
                 if not lab["is_owner"]]
        if loose:
            title = NO_THREAD_TITLE
        else:
            title = (t.title_in_record if t and t.title_in_record else ", ".join(n for n in names if n)) or "(untitled)"
        total = loose_totals.get(ext, int(r.n)) if loose else (int(t.event_count) if t else int(r.n))
        mark = marks.get(r.tk)
        items.append({"thread_key": r.tk, "phone": {"extraction_id": ext, "label": ctx.phone_label(ext)},
                      "app": (t.app if t else None) or r.app, "chat_type": t.chat_type if t else None,
                      "thread_kind": t.thread_kind if t else ("none" if loose else None), "title": title,
                      "participants": labels, "participant_count": len(members),
                      "first_instant": T.iso(r.first_i), "last_instant": T.iso(r.last_i),
                      "last_full": T.format_full(r.last_i, zone["name"]) if r.last_i else T.NO_TIME,
                      "event_count": int(r.n), "event_count_total": total, "deleted_count": int(r.deleted),
                      "has_unreadable": int(r.unreadable) > 0,
                      "review": review_marks.review_words(mark, total) if mark else None})
    _sort_threads(items, sort)
    # Copies are shown once per thread, not once per case: a copy of a message in another thread (an SMS and its
    # app copy) still counts in its own thread, so no thread drops out of the list (review of 03-3).
    # A thread with messages added since its review is partly reviewed and counts as not yet reviewed (J-13b).
    reviewed = sum(1 for i in items if i["review"] and not i["review"]["added_since"])
    partly = sum(1 for i in items if i["review"] and i["review"]["added_since"])
    out = envelope(conn, g, items=items, counts={"threads": len(items), "threads_total": total_threads,
                                                 "reviewed": reviewed, "partly_reviewed": partly,
                                                 "not_reviewed": len(items) - reviewed})
    out["sort"] = sort
    return out


THREAD_SORTS = ("recent", "first", "volume", "unreviewed", "name")


def _sort_threads(items, sort):
    """6.5: last activity (default), first activity, message count, unreviewed first, name. Undated last."""
    if sort == "first":
        items.sort(key=lambda x: (x["first_instant"] is None, x["first_instant"] or ""))
    elif sort == "volume":
        items.sort(key=lambda x: (-x["event_count"], x["title"].lower()))
    elif sort == "name":
        items.sort(key=lambda x: (x["title"].lower(), x["thread_key"]))
    else:
        items.sort(key=lambda x: x["last_instant"] or "", reverse=True)
        items.sort(key=lambda x: x["last_instant"] is None)
        if sort == "unreviewed":
            items.sort(key=lambda x: not (x["review"] is None or x["review"]["added_since"] > 0))


def participant_list(conn, f: StreamFilter) -> dict:
    """People mode (6.3): every identity taking part in an event under the filter, complete in one call, with its
    event count, first and last instant, phones and apps. The owner side is the phone owner's key (D-31)."""
    q, ctx = _query(conn, f)
    rows = conn.execute(text(
        "WITH m AS (%s) SELECT k, count(DISTINCT m.event_uid) AS n, min(m.sort_instant) AS first_i, "
        "max(m.sort_instant) AS last_i, array_agg(DISTINCT m.extraction_id::text) AS phones, "
        "array_remove(array_agg(DISTINCT m.app), NULL) AS apps FROM ("
        "SELECT m.*, %s AS k FROM m JOIN phone_participations p ON "
        "p.record_uid = m.record_uid AND p.generation = m.generation LEFT JOIN unnest(CAST(:oe AS uuid[]), "
        "CAST(:ok AS text[])) AS ok(e, k) ON ok.e = m.extraction_id WHERE %s) m WHERE k IS NOT NULL GROUP BY k"
        % (q.matched_sql(), PARTY_KEY_SQL, _shown(f))), q.params).fetchall()
    ctx.load([r.k for r in rows])
    items = []
    for r in rows:
        ext = sorted(r.phones)[0]
        label = ctx.label(ext, identity_key=r.k)
        items.append({"label": label, "events": int(r.n), "first_instant": T.iso(r.first_i),
                      "last_instant": T.iso(r.last_i), "phones": sorted(ctx.phone_label(e) for e in r.phones),
                      "apps": sorted(r.apps or [])})
    items.sort(key=lambda x: (-x["events"], L.label_text(x["label"]).lower()))
    return envelope(conn, f, items=items, counts={"participants": len(items)})
