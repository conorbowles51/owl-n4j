"""The Phones page's filters (screen 1): exact counts for What, Who and State over every phone in scope.

Each group is counted with its own choice taken off, so its other values stay choosable: What is counted with every
kind of record on, Who without the people chosen, State without the state chosen. Every count is the length of the
list the value opens (the lens ``index`` total under the same filter), so a number never promises rows the list does
not hold.

- What: one count per kind of record (``timeline_lens.KIND_WORDS``), messages and calls first.
- Who: the people taking part in the messages and calls in scope, most first, without the owners of the phones in
  scope (each owner is on their phone's card). ``people_total`` is the whole number; ``people`` holds the first
  ``PEOPLE_SHOWN`` and the screen says how many more there are.
- State: deleted or in the trash (every kind), and for messages and calls whether a copy is on another phone in scope
  (``timeline_lens.COPY_ON_OTHER_PHONE_SQL``: same kind, same minute, same text; a call the same length).
"""
from __future__ import annotations

import copy
import threading

from sqlalchemy import text

from services.phone import streams
from services.phone import timeline_lens as TL

PEOPLE_SHOWN = 8
DELETED_STATES = ["Deleted", "Trash"]
STATE_WORDS = {"deleted": "Deleted or in trash", "one": TL.COPIES_WORDS["one"], "many": TL.COPIES_WORDS["many"]}
ALL_KINDS = list(TL.KIND_WORDS)


def _total(conn, f: TL.TimelineLensFilter) -> int:
    zone = streams.resolve_zone(conn, f)
    sql, p = TL._union(conn, f, zone)
    return int(conn.execute(text("WITH u AS (%s) SELECT count(*) FROM u" % sql), p).scalar() or 0)


def kind_counts(conn, f: TL.TimelineLensFilter) -> list:
    g = f.model_copy(update={"lens_kinds": ALL_KINDS, "lane_by": "kind"})
    zone = streams.resolve_zone(conn, g)
    sql, p = TL._union(conn, g, zone)
    counts = {r.lane: int(r.n) for r in conn.execute(text("WITH u AS (%s) SELECT lane, count(*) AS n FROM u GROUP BY 1"
                                                          % sql), p)}
    return [{"key": k, "label": TL.KIND_WORDS[k], "count": counts.get(k, 0), "on": k in f.lens_kinds}
            for k in ALL_KINDS]


def _owner_keys(conn, f) -> set:
    from services.phone import labels as L
    ctx = L.LabelContext(conn, f.case_id, f.names.mode)
    phones = set(f.phones) if f.phones else None
    return {k for e, o in ctx.owners.items() if phones is None or e in phones for k in o["keys"]}


def people_counts(conn, f: TL.TimelineLensFilter) -> dict:
    g = f.model_copy(update={"participants": [], "participant_mode": "any"})
    sf = TL._stream_filter(g)
    if sf is None:
        return {"people": [], "people_total": 0, "applies": False}
    owners = _owner_keys(conn, f)
    items = [x for x in streams.participant_list(conn, sf, labels_for=PEOPLE_SHOWN + len(owners))["items"]
             if x["label"]["identity_key"] and x["label"]["identity_key"] not in owners]
    out = []
    for x in items[:PEOPLE_SHOWN]:
        lab = x["label"]
        words = lab["name"] or (lab["identifier"] or {}).get("display") or "Someone not named"
        out.append({"key": lab["identity_key"], "label": words, "count": x["events"], "phones": x["phones"],
                    "on": lab["identity_key"] in f.participants})
    return {"people": out, "people_total": len(items), "applies": True}


def state_counts(conn, f: TL.TimelineLensFilter) -> list:
    base = f.model_copy(update={"copies_on": None, "deleted_states": []})
    deleted = _total(conn, base.model_copy(update={"deleted_states": list(DELETED_STATES)}))
    comm = TL._stream_filter(base) is not None
    out = [{"key": "deleted", "label": STATE_WORDS["deleted"], "count": deleted,
            "on": sorted(v for v in f.deleted_states if v) == sorted(DELETED_STATES)}]
    for k in ("one", "many"):
        out.append({"key": k, "label": STATE_WORDS[k],
                    "count": _total(conn, base.model_copy(update={"copies_on": k})) if comm else 0,
                    "on": f.copies_on == k, "applies": comm})
    return out


def phone_spans(conn, f: TL.TimelineLensFilter) -> list:
    """Each active phone's first and last day with an event time (communications and other records), in the
    screen's zone, for its card. Every phone of the case, on or off, so a phone switched off keeps its card."""
    from services.phone import time_display as T
    zone = streams.resolve_zone(conn, f)
    zn = "UTC" if T.is_utc(zone["name"]) else zone["name"]
    rows = conn.execute(text(
        "WITH x AS (SELECT extraction_id, sort_instant AS i FROM pv_comm_event WHERE case_id = :c AND sort_instant IS "
        "NOT NULL UNION ALL SELECT extraction_id, instant FROM pv_timeline_entry WHERE case_id = :c AND is_event_time "
        "AND instant IS NOT NULL) SELECT x.extraction_id::text AS e, (min(i) AT TIME ZONE :z)::date AS a, "
        "(max(i) AT TIME ZONE :z)::date AS b FROM x JOIN phone_extractions p ON p.id = x.extraction_id AND "
        "p.standing = 'active' GROUP BY 1"), {"c": f.case_id, "z": zn}).fetchall()
    return [{"extraction_id": r.e, "first_day": r.a.isoformat(), "last_day": r.b.isoformat()} for r in rows]


PARTS = ("kinds", "people", "states", "phones")
STATES_NOTE = ("Copies on other phones are judged for messages and calls only: same kind, same minute and same text "
               "(a call, the same length).")


# Each answer kept per process, keyed by the list's own snapshot token (``filters.snapshot``: the filter, every phone's
# generation and standing, phone decisions, the case zone) and the name sources of the Who labels, so the page asks
# the database again only when a count or a name could differ. Phone reference 1, live 26 Nov: What 19 s, Who 24-54 s,
# State 16 s on every visit (about a million records read each time).
_CACHE: dict = {}
_CACHE_LIMIT = 64
_lock = threading.Lock()
_NAME_READS = ("SELECT count(*), max(updated_at) FROM case_profiles WHERE case_id = :c",
               "SELECT count(*), max(updated_at) FROM phone_identities WHERE case_id = :c",
               "SELECT count(*), max(created_at) FROM workspace_entry_links WHERE case_id = :c",
               "SELECT count(*), max(created_at) FROM dossier_links WHERE case_id = :c",
               "SELECT count(*), max(created_at) FROM adjudications WHERE case_id = :c")


def answer_key(conn, f: TL.TimelineLensFilter, part: str | None) -> str:
    from services.phone import filters
    names = "" if part in ("kinds", "states", "phones") else repr(
        [tuple(conn.execute(text(q), {"c": f.case_id}).one()) for q in _NAME_READS])
    return filters.snapshot(conn, f, extra="facets|%s|%s" % (part, names))


def facets(conn, f: TL.TimelineLensFilter, part: str | None = None) -> dict:
    """Every group, or one (``part``), so a screen can ask for each apart and show each as it arrives. An answer is
    read again only when its key (``answer_key``) has changed."""
    key = answer_key(conn, f, part)
    with _lock:
        hit = _CACHE.get(key)
    if hit is not None:
        return copy.deepcopy(hit)
    out = _facets(conn, f, part)
    with _lock:
        while len(_CACHE) >= _CACHE_LIMIT:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = copy.deepcopy(out)
    return out


def _facets(conn, f: TL.TimelineLensFilter, part: str | None = None) -> dict:
    out = {"case_id": f.case_id}
    if part in (None, "kinds"):
        out["kinds"] = kind_counts(conn, f)
    if part in (None, "people"):
        people = people_counts(conn, f)
        out.update(people=people["people"], people_total=people["people_total"], people_applies=people["applies"])
    if part in (None, "states"):
        out.update(states=state_counts(conn, f), states_note=STATES_NOTE)
    if part in (None, "phones"):
        out["phones"] = phone_spans(conn, f)
    return out
