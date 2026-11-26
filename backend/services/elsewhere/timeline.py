"""The Timeline part: case timeline events in the subject's dates.

Two sources, as the Timeline page shows them: events read from the evidence into the case graph (their names and
summaries were written by Loupe's reading, so each item says "Read by Loupe · not confirmed" unless it is a ledger
row), and events a person added. Rules: the record itself on the timeline **agrees**; an event in the dates that
names the subject's people, firms, places or check numbers is a **possible match**; payments on the timeline are
left to the Financial part (counted, not listed twice); with none, **nothing found**
says the dates searched and how many events they hold.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from services.elsewhere import words as W
from services.elsewhere.subject import window

RECORD_DAYS = 7
MAX_EVENTS = 500
MAX_ITEMS = 8
LEDGER_TYPES = ("Transaction", "Payment")   # ledger rows on the timeline are read under Financial, not twice


def _needles(subject):
    out = [(n, W.name_tokens(n)) for n in subject.names() if W.strong_name(n)]
    out += [(t, W.name_tokens(t)) for t in subject.terms]
    out += [("check %s" % r if r.isdigit() else r, [r.lower()]) for r in subject.references]
    return [(shown, toks) for shown, toks in out if toks]


def _graph_events(case_id, lo, hi):
    from services.neo4j_service import neo4j_service
    page = neo4j_service.get_timeline_page(case_id=str(case_id), start_date=lo.isoformat(), end_date=hi.isoformat(),
                                           limit=MAX_EVENTS)
    return page.get("events") or [], bool(page.get("next_cursor"))


def _people_entries(conn, case_id, lo, hi):
    return conn.execute(text(
        "SELECT id::text AS id, source_kind, source_id::text AS source_id, event_snapshot FROM timeline_entries WHERE "
        "case_id = CAST(:c AS uuid) AND (event_snapshot ->> 'date') BETWEEN :lo AND :hi"),
        {"c": str(case_id), "lo": lo.isoformat(), "hi": hi.isoformat()}).fetchall()


def _record_entries(conn, case_id, records):
    if not records:
        return []
    from services.timeline_entries import phone_source_uuid
    ids = [str(phone_source_uuid(r.record_uid)) for r in records]
    return conn.execute(text(
        "SELECT id::text AS id, event_snapshot FROM timeline_entries WHERE case_id = CAST(:c AS uuid) AND "
        "source_kind = 'phone_record' AND source_id = ANY(CAST(:i AS uuid[]))"), {"c": str(case_id), "i": ids}
    ).fetchall()


def _hay(ev):
    conns = " ".join(str(c.get("name") or "") for c in (ev.get("connections") or []) if isinstance(c, dict))
    return " ".join(str(x) for x in (ev.get("name"), ev.get("summary"), conns) if x)


def part(conn, case_id, subject, zone, graph_events=_graph_events) -> dict:
    items = []
    for e in _record_entries(conn, case_id, subject.records):
        snap = e.event_snapshot or {}
        items.append(W.item(W.AGREES, "This record is on the case timeline, %s." % W.day_text(snap["date"])
                            if snap.get("date") else "This record is on the case timeline.",
                            "A person added it to the timeline.",
                            {"kind": "timeline_entry", "id": "timeline-entry:%s" % e.id,
                             "label": snap.get("name") or "Timeline entry"}, ["record"]))
    if subject.kind == "record":
        lo, hi = window(subject, RECORD_DAYS, RECORD_DAYS)
    else:
        lo, hi = window(subject, 0, 0)
    if lo is None:
        searched = "The timeline was not searched: no date was given."
        if not items:
            items.append(W.item(W.NOTHING, searched, "The timeline is searched by date.", None))
        return {"searched": searched, "items": items}
    needles = _needles(subject)
    events, clipped = graph_events(case_id, lo, hi)
    people = _people_entries(conn, case_id, lo, hi)
    total = len(events) + len(people)
    hits = []
    ledger = 0
    for ev in events:
        if ev.get("ledger_transaction_id") or ev.get("type") in LEDGER_TYPES:
            ledger += 1
            continue
        hay = set(W.words_of(_hay(ev)))
        named = [shown for shown, toks in needles if all(t in hay for t in toks)]
        if named:
            hits.append(("graph", ev, named))
    for e in people:
        snap = e.event_snapshot or {}
        hay = set(W.words_of(" ".join(str(snap.get(k) or "") for k in ("name", "summary", "notes"))))
        named = [shown for shown, toks in needles if all(t in hay for t in toks)]
        if named:
            hits.append(("person", dict(snap, key="timeline-entry:%s" % e.id), named))
    hits.sort(key=lambda h: str(h[1].get("date") or ""))
    for source, ev, named in hits[:MAX_ITEMS]:
        machine = source == "graph" and not ev.get("ledger_transaction_id")
        items.append(W.item(
            W.POSSIBLE, "%s: “%s” names %s." % (W.day_text(str(ev["date"])[:10]) if len(str(ev.get("date") or "")) >= 10
                                               else (ev.get("date") or "Undated"), ev.get("name") or "An event",
                                               W.join_words(named)),
            "On the case timeline in the dates searched; it names the same %s." % (
                "people" if any(W.strong_name(n) for n in named) else "names"),
            {"kind": "timeline_event", "id": ev.get("key"), "label": ev.get("name") or "Timeline event",
             "machine": machine}, ["name", "date"],
            machine_label="Read by Loupe · not confirmed" if machine else None))
    if len(hits) > MAX_ITEMS:
        items.append(W.item(W.POSSIBLE, "%s them %s." % (
            W.more(len(hits) - MAX_ITEMS, "timeline event", "names", "name"), W.span_text(lo, hi)), "Only the first %d are listed here." %
            MAX_ITEMS, {"kind": "screen", "screen": "timeline", "start": lo.isoformat(), "end": hi.isoformat()}, []))
    searched = "Searched the case timeline %s (%s)%s." % (
        W.span_text(lo, hi), W.plural(total, "event") if not clipped else "%s or more events" % "{:,}".format(total),
        ", for %s" % W.join_words([n for n, _ in needles]) if needles else "")
    if ledger:
        searched += " %s in these dates %s read under Financial." % (
            W.plural(ledger, "payment"), "is" if ledger == 1 else "are")
    if not hits and not items:
        what = (" names %s" % W.join_words([n for n, _ in needles])) if needles else ""
        items.append(W.item(W.NOTHING, "Nothing in the case timeline %s%s." % (W.span_text(lo, hi), what), searched,
                            {"kind": "screen", "screen": "timeline", "start": lo.isoformat(), "end": hi.isoformat()}))
    return {"searched": searched, "items": items}
