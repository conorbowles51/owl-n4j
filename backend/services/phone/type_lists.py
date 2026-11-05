"""The list for each record type (docs/cellebrite/03 section 7.5, test P-8).

``page`` lists the records of one type on the case's phones, one window at a time: keyset paging (a window never
re-reads the rows before it), the exact total for the filters (a count over the type's rows in the index, never over
the table), and the server's sort. The browser holds only the windows it scrolled to.

``placement`` chooses what the Phone summary counts: ``top`` the records standing on their own (the summary's Records
figure), ``nested`` the records held inside another record, ``all`` both. ``copies`` narrows to, or leaves out, the
copies from another source the report lists under ``RelatedModels`` (02 decision 39). A copy stays in every list that
has it, marked; it is never merged into its owner.

Columns come from the type's mapping, then from the field names the registry saw on these phones, most filled first.
Up to ``MAX_COLUMNS`` show; the response says how many more fields the record panel holds. Sensitive values are masked
here exactly as in the record panel (05 section 3.8), and a corrected value shows with its original beside it.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime

from sqlalchemy import text

from services.phone import body as B
from services.phone import ids, sensitive
from services.phone import time_display as T

PAGE = 200
MAX_PAGE = 500
MAX_COLUMNS = 8
CELL_CHILDREN = 3
SORTS = ("time", "report", "title", "deleted")
DELETED_STATES = ("Deleted", "Trash")
COPY_FLAG = "related_copy"
PLACEMENTS = ("all", "top", "nested")
RELATED_KIND = "RelatedModels"


class NotFound(LookupError):
    pass


class StaleWindow(RuntimeError):
    """The phone was read again since this list was opened: a later window would not continue the earlier ones."""


class BadCursor(ValueError):
    pass


def _phones(conn, case_id, extraction_ids):
    """The active phones in scope with their current generation; a phone of another case is not found (3.11)."""
    rows = conn.execute(text(
        "SELECT e.id, st.generation FROM phone_extractions e JOIN phone_interpretation_state st ON st.extraction_id = "
        "e.id WHERE e.case_id = :c AND e.standing = 'active' ORDER BY e.id"), {"c": str(case_id)}).fetchall()
    have = {str(r[0]): int(r[1]) for r in rows}
    if not extraction_ids:
        return have
    wanted = [str(e) for e in extraction_ids]
    if any(e not in have for e in wanted):
        raise NotFound("That phone is not in this case.")
    return {e: have[e] for e in sorted(set(wanted))}


def _where(phones, model_type, *, placement, deleted, copies, start, end):
    p = {"t": model_type}
    alts = []
    for i, (e, g) in enumerate(phones.items()):
        p["e%d" % i], p["g%d" % i] = e, g
        alts.append("(s.extraction_id = CAST(:e%d AS uuid) AND s.generation = :g%d)" % (i, i))
    w = ["(%s)" % " OR ".join(alts), "s.model_type = :t"]
    if placement == "top":
        w.append("s.is_top_level")
    elif placement == "nested":
        w.append("NOT s.is_top_level")
    if deleted == "only":
        w.append("s.deleted_state IN ('Deleted', 'Trash')")
    elif deleted == "hide":
        w.append("(s.deleted_state IS NULL OR s.deleted_state NOT IN ('Deleted', 'Trash'))")
    if copies == "only":
        w.append("'%s' = ANY(s.flags)" % COPY_FLAG)
    elif copies == "hide":
        w.append("NOT ('%s' = ANY(s.flags))" % COPY_FLAG)
    dated = list(w)
    if start is not None:
        dated.append("s.first_instant >= :start")
        p["start"] = start
    if end is not None:
        dated.append("s.first_instant < :end")
        p["end"] = end
    return " AND ".join(dated), " AND ".join(w), p


# ---- sort and cursor ------------------------------------------------------------------------------------------------

TAIL = ("s.extraction_id", "s.document_index", "s.ordinal")
KEY_SQL = {"time": "s.first_instant", "title": 'lower(s.title) COLLATE "C"',
           "deleted": "coalesce(s.deleted_state, '')"}


def _order(sort, direction):
    d = "ASC" if direction == "asc" else "DESC"
    tail = ", ".join("%s %s" % (c, d) for c in TAIL)
    if sort == "report":
        return tail
    return "%s %s NULLS LAST, %s" % (KEY_SQL[sort], d, tail)


def _after(sort, direction, cur, p):
    """The rows after the cursor in this order. A record with no time sorts last either way."""
    op = ">" if direction == "asc" else "<"
    p.update(ce=cur["e"], cd=cur["d"], co=cur["o"])
    tail = "(s.extraction_id, s.document_index, s.ordinal) %s (CAST(:ce AS uuid), :cd, :co)" % op
    if sort == "report":
        return tail
    key = cur.get("k")
    if key is None:  # already among the rows with no time
        return "s.first_instant IS NULL AND %s" % tail
    p["ck"] = key
    if sort == "time":
        return ("(s.first_instant IS NULL OR (s.first_instant, s.extraction_id, s.document_index, s.ordinal) %s "
                "(CAST(:ck AS timestamptz), CAST(:ce AS uuid), :cd, :co))" % op)
    return "(%s, s.extraction_id, s.document_index, s.ordinal) %s (CAST(:ck AS text) COLLATE \"C\", CAST(:ce AS uuid), " \
           ":cd, :co)" % (KEY_SQL[sort], op)


def _shape(phones, model_type, placement, deleted, copies, start, end, sort, direction):
    """What a cursor belongs to: the generations read and every choice that orders or narrows the list."""
    raw = json.dumps([sorted(phones.items()), model_type, placement, deleted, copies, str(start), str(end), sort,
                      direction], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _encode(shape, key, r):
    raw = json.dumps({"s": shape, "k": key, "e": str(r.extraction_id), "d": int(r.document_index), "o": int(r.ordinal)})
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode(cursor, shape):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        cur = json.loads(raw)
        cur = {"s": str(cur["s"]), "k": cur.get("k"), "e": str(cur["e"]), "d": int(cur["d"]), "o": int(cur["o"])}
    except (ValueError, KeyError, TypeError) as exc:
        raise BadCursor("That list position cannot be read.") from exc
    if cur["s"] != shape:
        raise StaleWindow("The list changed since it was opened.")
    return cur


# ---- columns --------------------------------------------------------------------------------------------------------

def columns(conn, phones, model_type):
    """(columns shown, how many more fields the type has). Fields a mapping names first, then the fields the registry
    saw on these phones, most filled first. The ``RelatedModels`` nesting is the copies, not a column."""
    from services.phone import coverage
    from services.phone.mappings import loader
    ext = list(phones)
    seen = {}
    for name, kind, recs in conn.execute(text(
            "SELECT f.field_name, f.field_kind, sum(o.record_count) FROM phone_schema_observations o JOIN "
            "phone_schema_fields f ON f.id = o.registry_id WHERE o.extraction_id = ANY(CAST(:e AS uuid[])) AND "
            "o.registry_table = 'fields' AND f.type_name = :t GROUP BY 1, 2"), {"e": ext, "t": model_type}):
        at = seen.setdefault(name, {"records": 0, "value": False, "child": False})
        at["records"] += int(recs)
        at["value"] = True
    for name, kind, recs in conn.execute(text(
            "SELECT n.field_name, n.field_kind, sum(o.record_count) FROM phone_schema_observations o JOIN "
            "phone_schema_nesting n ON n.id = o.registry_id WHERE o.extraction_id = ANY(CAST(:e AS uuid[])) AND "
            "o.registry_table = 'nesting' AND n.parent_type = :t AND n.field_kind <> :r GROUP BY 1, 2"),
            {"e": ext, "t": model_type, "r": RELATED_KIND}):
        at = seen.setdefault(name, {"records": 0, "value": False, "child": False})
        at["records"] += int(recs)
        at["child"] = True
    named = []
    for m in loader.loaded():
        if m.kind == "type":
            t, fields = coverage.named_fields(m)
            if t == model_type:
                named = [f for f in fields if f in seen]
                break
    rest = sorted((f for f in seen if f not in named), key=lambda f: (-seen[f]["records"], f))
    chosen = (named + rest)[:MAX_COLUMNS]
    out = [{"id": f, "header": f, "sensitive": sensitive.is_sensitive(model_type, f), "mapped": f in named}
           for f in chosen if f]
    return out, max(0, len(seen) - len(out))


def _cells(conn, rows, model_type, cols, zone):
    """Each row's value for each column, read from the captured body: the first value and how many more."""
    if not rows:
        return {}
    uids = [str(r.record_uid) for r in rows]
    wanted = {c["id"] for c in cols}
    keys = conn.execute(text(
        "SELECT r.extraction_id, r.document_index, r.ordinal, r.body FROM phone_records r JOIN unnest("
        "CAST(:e AS uuid[]), CAST(:d AS smallint[]), CAST(:o AS int[])) AS k(e, d, o) ON r.extraction_id = k.e AND "
        "r.document_index = k.d AND r.ordinal = k.o"),
        {"e": [str(r.extraction_id) for r in rows], "d": [int(r.document_index) for r in rows],
         "o": [int(r.ordinal) for r in rows]}).fetchall()
    bodies = {(str(r[0]), int(r[1]), int(r[2])): r[3] for r in keys}
    times = {}
    for t in conn.execute(text(
            "SELECT record_uid, field_path, value_index, instant, local_wall_time, instant_basis FROM pv_time WHERE "
            "record_uid = ANY(CAST(:u AS uuid[]))"), {"u": uids}):
        # a nested record's path carries its place in its parent; the cell is read by the field's own name
        times[(str(t.record_uid), t.field_path.rsplit(".", 1)[-1], t.value_index)] = t
    fixed = {}
    for c in conn.execute(text(
            "SELECT record_uid, field_path, value_index, machine_text, corrected_text FROM phone_value_corrections "
            "WHERE record_uid = ANY(CAST(:u AS uuid[])) AND superseded_by_id IS NULL AND corrected_text IS DISTINCT "
            "FROM machine_text"), {"u": uids}):
        fixed[(str(c.record_uid), c.field_path.rsplit(".", 1)[-1], c.value_index)] = c
    children, wanted_uids = {}, set()
    out = {}
    for r in rows:
        uid = str(r.record_uid)
        cells = {}
        body = bodies.get((str(r.extraction_id), int(r.document_index), int(r.ordinal)))
        for f in B.fields(body) if body else ():
            if f.name not in wanted or f.name in cells:
                continue
            vals = f.real_values
            if vals:
                v = vals[0]
                cell = {"text": v.text or "", "more": len(vals) - 1}
                t = times.get((uid, f.name, v.index))
                if sensitive.is_sensitive(model_type, f.name):
                    cell.update(text=sensitive.masked(model_type, f.name, v.text), masked=True)
                elif t is not None:
                    cell["text"] = T.format_decided(t.instant, zone, t.instant_basis) if t.instant else \
                        (T.format_wall(t.local_wall_time) if t.local_wall_time else T.NO_TIME)
                else:
                    c = fixed.get((uid, f.name, v.index))
                    if c is not None:
                        cell.update(text=c.corrected_text or "", original=c.machine_text)
                cells[f.name] = cell
            elif f.children:
                got = [str(ids.record_uid(r.extraction_id, r.document_index, o)) for o in f.children]
                children[(uid, f.name)] = got
                wanted_uids.update(got[:CELL_CHILDREN])
        out[uid] = cells
    if wanted_uids:
        titles = {str(u): (t, m) for u, t, m in conn.execute(text(
            "SELECT record_uid, title, model_type FROM pv_record WHERE record_uid = ANY(CAST(:u AS uuid[]))"),
            {"u": sorted(wanted_uids)})}
        for (uid, name), got in children.items():
            shown = [_bare_title(*titles[u]) for u in got[:CELL_CHILDREN] if u in titles]
            out[uid][name] = {"text": ", ".join(shown), "more": len(got) - len(shown)}
    return out


def _bare_title(title, model_type):
    """A record's title is ``<type> <first text>``; the column says the type already."""
    prefix = "%s " % model_type
    return title[len(prefix):] if title.startswith(prefix) else title


# ---- the window -----------------------------------------------------------------------------------------------------

def page(conn, case_id, model_type, *, extraction_ids=(), placement="all", deleted="any", copies="any", day_from=None,
         day_to=None, sort="time", direction="asc", cursor=None, limit=PAGE, zone="UTC") -> dict:
    phones = _phones(conn, case_id, extraction_ids)
    start = T.day_bounds(day_from, zone)[0] if day_from else None
    end = T.day_bounds(day_to, zone)[1] if day_to else None
    if not phones:
        return {"case_id": str(case_id), "model_type": model_type, "total": 0, "no_time": 0, "items": [], "next": None,
                "columns": [], "more_fields": 0, "zone": zone}
    where, undated, p = _where(phones, model_type, placement=placement, deleted=deleted, copies=copies, start=start,
                               end=end)
    limit = max(1, min(int(limit), MAX_PAGE))
    shape = _shape(phones, model_type, placement, deleted, copies, start, end, sort, direction)
    total = int(conn.execute(text("SELECT count(*) FROM phone_record_summaries s WHERE " + where), p).scalar() or 0)
    # a date filter leaves out records with no time: the count says so, so the list is never silently partial
    no_time = 0
    if start is not None or end is not None:
        no_time = int(conn.execute(text(
            "SELECT count(*) FROM phone_record_summaries s WHERE s.first_instant IS NULL AND " + undated), p).scalar() or 0)
    w = where
    args = dict(p)
    if cursor:
        w += " AND " + _after(sort, direction, _decode(cursor, shape), args)
    key = KEY_SQL.get(sort, "NULL")
    rows = conn.execute(text(
        "SELECT s.extraction_id, s.document_index, s.ordinal, s.record_uid, s.parent_record_uid, s.title, "
        "s.first_instant, s.deleted_state, s.interpretation_level, s.is_top_level, s.flags, s.source_index, "
        "%s AS sort_key FROM phone_record_summaries s WHERE %s ORDER BY %s LIMIT :lim"
        % (key, w, _order(sort, direction))), {**args, "lim": limit + 1}).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    cols, more_fields = columns(conn, phones, model_type)
    cells = _cells(conn, rows, model_type, cols, zone)
    uids = [str(r.record_uid) for r in rows]
    comms = {str(u) for (u,) in conn.execute(text(
        "SELECT record_uid FROM pv_comm_event WHERE record_uid = ANY(CAST(:u AS uuid[]))"), {"u": uids})} if uids else set()
    parents = sorted({str(r.parent_record_uid) for r in rows if r.parent_record_uid})
    owners = {str(u): {"record_uid": str(u), "model_type": m, "title": _bare_title(t, m)}
              for u, m, t in conn.execute(text(
                  "SELECT record_uid, model_type, title FROM pv_record WHERE record_uid = ANY(CAST(:u AS uuid[]))"),
                  {"u": parents})} if parents else {}
    items = [{
        "record_uid": str(r.record_uid), "extraction_id": str(r.extraction_id), "title": _bare_title(r.title, model_type),
        "time": T.format_full(r.first_instant, zone) if r.first_instant else None, "deleted_state": r.deleted_state,
        "interpretation_level": r.interpretation_level, "nested": not r.is_top_level,
        "copy": COPY_FLAG in (r.flags or []), "source_index": r.source_index,
        "owner": owners.get(str(r.parent_record_uid)) if r.parent_record_uid else None,
        "open_in": "conversations" if str(r.record_uid) in comms else "panel",
        "cells": cells.get(str(r.record_uid), {})} for r in rows]
    next_cursor = None
    if more:
        last = rows[-1]
        k = last.sort_key
        next_cursor = _encode(shape, k.isoformat() if isinstance(k, datetime) else k, last)
    return {"case_id": str(case_id), "model_type": model_type, "total": total, "no_time": no_time, "items": items,
            "next": next_cursor, "columns": cols, "more_fields": more_fields, "zone": zone,
            "placement": placement, "sort": sort, "direction": direction}
