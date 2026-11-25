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
    items = [x for x in streams.participant_list(conn, sf)["items"]
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


PARTS = ("kinds", "people", "states")
STATES_NOTE = ("Copies on other phones are judged for messages and calls only: same kind, same minute and same text "
               "(a call, the same length).")


def facets(conn, f: TL.TimelineLensFilter, part: str | None = None) -> dict:
    """Every group, or one (``part``), so a screen can ask for each apart and show each as it arrives."""
    out = {"case_id": f.case_id}
    if part in (None, "kinds"):
        out["kinds"] = kind_counts(conn, f)
    if part in (None, "people"):
        people = people_counts(conn, f)
        out.update(people=people["people"], people_total=people["people_total"], people_applies=people["applies"])
    if part in (None, "states"):
        out.update(states=state_counts(conn, f), states_note=STATES_NOTE)
    return out
