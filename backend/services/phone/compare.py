"""Compare two phones (07 J-16): how many messages and calls are on both, only on one, only on the other.

The same message on two phones is found by 05 section 5.3's keys, read from each record: the same platform family
(K1: ``sms`` for the phone's own messages, ``phone`` for cellular calls, else the app), the same text after the
search fold (K4: decorative letters, case and spacing folded; calls: durations within 2 seconds), and times within
120 seconds (K5, tau before a clock offset is known). Pairs are assigned one to one, closest in time first (5.3.4).
A text shorter than 10 characters or seen more than 3 times on either phone pairs only when the two sides'
directions are complementary (sent on one, received on the other), so common short replies do not pair unrelated
messages (5.3.3). Copies of one message on the same phone count once, as on screen. Records with no time are not
compared and are counted.

Decision: these keys stand until approach 12 / approach 5 ship their results (05 sections 5 and 15.3); J-16's
counts then read those results for the same pair and scope. Reverse when that result exists.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

KINDS = ("message", "call")
KEY_WORDS = ("Matched when the app family and the text agree and the times are within 2 minutes (calls: the "
             "duration within 2 seconds, or neither recorded); a message with no text matches at the same second; "
             "short or common texts also need one side sent and the other received. "
             "Copies on one phone count once.")
TAU_SECONDS = 120
CALL_SECONDS = 2
SMS_APPS = {"", "sms", "mms", "native messages", "ims service", "messages", "android calllog database"}
PHONE_APPS = {"", "phone", "native phone", "cellular"}


class NotFound(LookupError):
    pass


def compare(conn, case_id, a, b, person=None) -> dict:
    from services.phone import readings
    a, b, case_id = str(a), str(b), str(case_id)
    if a == b:
        raise ValueError("Choose two different phones.")
    found = {str(r[0]) for r in conn.execute(text(
        "SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active' AND id IN "
        "(CAST(:a AS uuid), CAST(:b AS uuid))"), {"c": case_id, "a": a, "b": b})}
    if found != {a, b}:
        raise NotFound("Both phones must be in this case.")
    labels = readings.phone_labels(conn, case_id)
    scope = ("AND EXISTS (SELECT 1 FROM pv_comm_party p WHERE p.event_uid = ev.event_uid AND p.identity_key = :who)"
             if person else "")
    p = {"c": case_id, "a": a, "b": b, "who": person}
    # a phone's period is all its messages and calls (what it covers), whoever is chosen; the undated count is
    # within the chosen scope
    periods = {str(r.extraction_id): r for r in conn.execute(text(
        "SELECT ev.extraction_id, min(ev.sort_instant) AS first, max(ev.sort_instant) AS last, "
        "count(*) FILTER (WHERE ev.sort_instant IS NULL " + scope + ") AS no_time FROM pv_comm_event ev WHERE "
        "ev.case_id = :c AND ev.extraction_id IN (CAST(:a AS uuid), CAST(:b AS uuid)) AND ev.kind IN ('message', "
        "'call') GROUP BY ev.extraction_id"), p)}
    p.update({"af": getattr(periods.get(a), "first", None), "al": getattr(periods.get(a), "last", None),
              "bf": getattr(periods.get(b), "first", None), "bl": getattr(periods.get(b), "last", None)})
    evs = conn.execute(text(
        "SELECT DISTINCT ON (ev.extraction_id, coalesce(ev.dup_group_uid, ev.event_uid::text)) ev.extraction_id, "
        "ev.kind, ev.app, ev.sort_instant AS at, ev.body, ev.call_duration_s AS d, ev.direction FROM pv_comm_event ev "
        "WHERE ev.case_id = :c AND ev.extraction_id IN (CAST(:a AS uuid), CAST(:b AS uuid)) AND ev.kind IN "
        "('message', 'call') AND ev.sort_instant IS NOT NULL " + scope + " ORDER BY ev.extraction_id, "
        "coalesce(ev.dup_group_uid, ev.event_uid::text), ev.sort_instant, ev.event_uid"), p).fetchall()
    kinds = {k: {"both": 0, "only_a": 0, "only_a_outside": 0, "only_b": 0, "only_b_outside": 0} for k in KINDS}
    matched = match(evs, a, b)
    for i, r in enumerate(evs):
        mine = str(r.extraction_id)
        if mine == a and i in matched:
            kinds[r.kind]["both"] += 1
        elif i not in matched:
            other = periods.get(b if mine == a else a)
            k = "only_a" if mine == a else "only_b"
            kinds[r.kind][k] += 1
            if other is None or other.first is None or r.at < other.first or r.at > other.last:
                kinds[r.kind][k + "_outside"] += 1

    def side(ext):
        r = periods.get(ext)
        iso = (lambda v: v.isoformat() if v is not None else None)
        return {"extraction_id": ext, "label": labels.get(ext, "A phone"), "first": iso(getattr(r, "first", None)),
                "last": iso(getattr(r, "last", None)), "no_time": int(getattr(r, "no_time", 0) or 0)}
    return {"case_id": case_id, "person": person, "a": side(a), "b": side(b), "kinds": kinds, "key": KEY_WORDS}


def family(kind, app) -> str:
    a = (app or "").strip().casefold()
    if kind == "call":
        return "phone" if a in PHONE_APPS else a
    return "sms" if a in SMS_APPS else ("imessage" if a == "imessage" else a)


def match(evs, a, b) -> set:
    """Indexes of ``evs`` paired one to one across phones ``a`` and ``b`` (05 section 5.3.4). Each group is
    sorted by time and only candidates inside the 120-second window are compared."""
    import bisect
    from collections import Counter, defaultdict

    from services.phone import fold as F
    keyed = []
    for i, r in enumerate(evs):
        side = 0 if str(r.extraction_id) == a else 1
        text = " ".join((F.fold(r.body or "") if r.kind == "message" else "").split())
        keyed.append((i, side, family(r.kind, r.app), text))
    seen = Counter((side, fam, t) for _, side, fam, t in keyed if t)
    groups = defaultdict(lambda: ([], []))
    for i, side, fam, t in keyed:
        groups[(evs[i].kind, fam, t)][side].append(i)
    cands = []
    for (kind, fam, t), (xs, ys) in groups.items():
        if not xs or not ys:
            continue
        # a message with no text (a picture or voice note) pairs only at the same second: app messages matched
        # across phones carry identical server times (05 section 1, X7)
        window = TAU_SECONDS if (kind == "call" or t) else 1
        weak = kind == "message" and t and (len(t) < 10 or seen[(0, fam, t)] > 3 or seen[(1, fam, t)] > 3)
        ys = sorted(ys, key=lambda y: evs[y].at)
        times = [evs[y].at for y in ys]
        for x in xs:
            rx = evs[x]
            lo = bisect.bisect_left(times, rx.at - timedelta(seconds=window))
            hi = bisect.bisect_right(times, rx.at + timedelta(seconds=window))
            for y in ys[lo:hi]:
                ry = evs[y]
                gap = abs((ry.at - rx.at).total_seconds())
                if not t and kind == "message" and gap >= 1:
                    continue
                if kind == "call" and not (rx.d is None and ry.d is None) and (
                        rx.d is None or ry.d is None or abs(rx.d - ry.d) > CALL_SECONDS):
                    continue
                if weak and {rx.direction, ry.direction} != {"incoming", "outgoing"}:
                    continue
                cands.append((gap, x, y))
    cands.sort()
    out = set()
    for gap, x, y in cands:
        if x not in out and y not in out:
            out.update((x, y))
    return out
