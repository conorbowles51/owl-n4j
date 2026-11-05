"""Phone money readings on the Case Timeline's money lane (05 section 4.4; 03 section 9).

A reading is what a phone's alert, text or message says about a payment. It is a p4 claim from approach 1, stored with
its run; correlation never promotes it. The lane shows the readings of the case's latest completed money run, on the
active phones the lens covers, each labelled p4 and "from the phone". It has its own request, so the lens's totals,
lanes and exports never hold a reading, and the base Timeline never waits for it. Counts here are numbers of readings:
this module never adds amounts, and it returns no sum (``test_phone_timeline_money``). A reading a person rejected
stays out of the counts, as 05 section 4.3 says; one with no time is counted apart, never placed on a day.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from services.phone import streams
from services.phone import time_display as T
from services.phone_analysis import framework as F

ITEMS_MAX = 500
LABEL = "Money: readings from the phone (p4)"
WORDS = ("Each mark is a reading of a phone's alert, text or message, not a payment in the records: p4, from the "
         "phone. Readings are never added to any total.")
NO_RUN_WORDS = "Phone money readings have not been run in this case."
STEP = {"hour": timedelta(hours=1), "day": timedelta(days=1), "week": timedelta(days=7)}


def _latest_run(conn, case_id):
    return conn.execute(text(
        "SELECT id, finished_at FROM phone_analysis_runs WHERE case_id = CAST(:c AS uuid) AND approach = "
        "'money_signals' AND status = 'completed' ORDER BY finished_at DESC NULLS LAST, id DESC LIMIT 1"),
        {"c": str(case_id)}).first()


def _readings(conn, case_id, phones, run_id):
    """Readings of the run on the active phones in scope, without the ones a person rejected."""
    rows = conn.execute(text(
        "SELECT r.id, r.run_id, r.result_key, r.period_start, r.measures, x.extraction_id, x.record_uid FROM "
        "phone_analysis_results r JOIN phone_analysis_result_records x ON x.result_id = r.id AND x.role = 'evidence' "
        "JOIN phone_extractions e ON e.id = x.extraction_id AND e.standing = 'active' WHERE r.run_id = :r AND "
        "r.case_id = :c AND r.kind = 'money_reading' AND (CAST(:p AS text[]) IS NULL OR x.extraction_id::text = "
        "ANY(CAST(:p AS text[]))) ORDER BY r.period_start NULLS LAST, r.id"),
        {"r": run_id, "c": str(case_id), "p": [str(x) for x in phones] if phones else None}).fetchall()
    decided = F._decisions_for(conn, case_id, [(r.result_key, r) for r in rows])
    rejected = sum(1 for r in rows if (decided.get(r.result_key) or [{}])[-1].get("decision") == "rejected")
    return [r for r in rows if (decided.get(r.result_key) or [{}])[-1].get("decision") != "rejected"], rejected


def _item(r) -> dict:
    m = r.measures
    institution = m.get("institution") or {}
    return {"result_id": str(r.id), "record_uid": str(r.record_uid), "instant": T.iso(r.period_start),
            "amount_text": m.get("amount_text"), "currency": m.get("currency"), "direction": m.get("direction"),
            "institution": institution.get("name"), "source": m.get("source"), "phone_label": m.get("phone_label"),
            "outcome": m.get("outcome"), "proof_class": "p4", "from_the_phone": True}


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def lane(conn, f, *, start: datetime, end: datetime, bucket: str) -> dict:
    """The lane's marks over a span, in the buckets of ``timeline_lens.buckets``: count of readings per bucket."""
    start, end = _utc(start), _utc(end)
    run = _latest_run(conn, f.case_id)
    out = {"case_id": str(f.case_id), "label": LABEL, "words": WORDS, "proof_class": "p4", "run": None, "buckets": [],
           "readings": 0, "no_time": 0, "rejected": 0, "absent_words": NO_RUN_WORDS}
    if run is None:
        return out
    rows, rejected = _readings(conn, f.case_id, f.phones, run.id)
    zone = streams.resolve_zone(conn, f)
    tz = T.tz(zone["name"])
    first = start.astimezone(tz).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    if bucket in ("day", "week"):
        first = first.replace(hour=0)
    if bucket == "week":
        first = first - timedelta(days=first.weekday())
    # every bucket is whole, as the lens's are: a mark's count equals the list it opens
    walls = [first]
    while (walls[-1] + STEP[bucket]).replace(tzinfo=tz) < end:
        walls.append(walls[-1] + STEP[bucket])
    b0 = first.replace(tzinfo=tz)
    b1 = (walls[-1] + STEP[bucket]).replace(tzinfo=tz)
    counts = {}
    for r in rows:
        if r.period_start is None or not b0 <= r.period_start < b1:
            continue
        wall = r.period_start.astimezone(tz).replace(tzinfo=None)
        at = first + STEP[bucket] * ((wall - first) // STEP[bucket])
        counts[at] = counts.get(at, 0) + 1
    out.update(run={"id": str(run.id), "finished_at": T.iso(run.finished_at)}, absent_words=None, rejected=rejected,
               readings=sum(counts.values()), no_time=sum(1 for r in rows if r.period_start is None),
               buckets=[{"start": w.replace(tzinfo=tz).astimezone(timezone.utc).isoformat(), "wall": w.isoformat(),
                         "end": (w + STEP[bucket]).replace(tzinfo=tz).astimezone(timezone.utc).isoformat(),
                         "count": n} for w, n in sorted(counts.items())])
    return out


def items(conn, f, *, start: datetime, end: datetime) -> dict:
    """The readings of one mark, each with its citation; the page states when it holds fewer than the total."""
    start, end = _utc(start), _utc(end)
    run = _latest_run(conn, f.case_id)
    if run is None:
        return {"total": 0, "items": [], "limit": ITEMS_MAX, "words": WORDS}
    rows, _ = _readings(conn, f.case_id, f.phones, run.id)
    shown = [r for r in rows if r.period_start is not None and start <= r.period_start < end]
    return {"total": len(shown), "items": [_item(r) for r in shown[:ITEMS_MAX]], "limit": ITEMS_MAX, "words": WORDS}
