"""Signals between people, instance by instance (lx-corroengine B, C): the rows of the comparison grid.

Each function reads plain records (``model``) and returns grid rows: ``{id, link_kind, label, people, cells:
{instance id: present | absent | no_data}, records: {instance id: [refs]}, times: {instance id: first instant},
weight, why_low}``. ``no_data`` means the records that would show the signal do not cover that instance (no phone
for either person then, no statement for that month); it counts neither way.

Copies count once: records arrive deduplicated (``model.dedupe``), so the same message held on two phones, or a
payment seen as a ledger row and as alerts on two phones, is one record with its copies listed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from itertools import combinations
from operator import itemgetter

from services.corroborate import model as M

RARE_PHRASE_MAX = 12      # a word run used in at most this many records of the case can be "the same rare words"
STOCK_PHRASE_MIN = 20     # used in this many or more, it is a stock phrase and is weighed low
MAX_REFS = 25             # records listed per cell; the count is always the whole number


HELD_LISTS = 8  # record lists whose sorted copy and time index are kept (the newest asked)
_HELD: list = []   # [(records list, its length, sorted copy, {kinds: index})], newest first


def _held(recs: list[dict]) -> tuple:
    """``(sorted copy, index memo)`` for ``recs``, sorted by time. A weighing buckets the same records once per kind of
    row and pair (Phone reference 1, 20 Nov: about 38 buckets of 160,000 records a weighing, 12 sorts), so the last
    few lists asked keep their sorted copy. The list itself is held, so its identity is never reused while kept."""
    for i, (held, n, pool, memo) in enumerate(_HELD):
        if held is recs and n == len(recs):
            if i:
                _HELD.insert(0, _HELD.pop(i))
            return pool, memo
    pool = sorted(recs, key=itemgetter("at"))
    _HELD.insert(0, (recs, len(recs), pool, {}))
    del _HELD[HELD_LISTS:]
    return pool, _HELD[0][3]


def _by_time(recs: list[dict]) -> list[dict]:
    return _held(recs)[0]


def _only(recs: list[dict], name: str, keep) -> list[dict]:
    """``[r for r in recs if keep(r)]``, made once per held list and ``name``: every pair's rows of one kind filter the
    same records, and the same list then shares one sorted copy and time index in ``bucket``. Callers never change
    it."""
    memo = _held(recs)[1]
    key = ("only", name)
    got = memo.get(key)
    if got is None:
        got = memo[key] = [r for r in recs if keep(r)]
    return got


def _index(recs: list[dict], kinds) -> tuple:
    """The time index ``bucket`` searches: the records of ``kinds`` in time order, the timed ones' positions and
    instants, and the day-only ones'. Built once per held list and kinds."""
    pool, memo = _held(recs)
    key = None if kinds is None else frozenset(kinds)
    if key in memo:
        return memo[key]
    # a stable sort then a filter: the order sorting the filter gives
    pool_k = pool if kinds is None else [r for r in pool if r["kind"] in kinds]
    # a timed record is inside when start <= at <= end: a slice of the timed records, no test per record. Only a
    # day-only record is tested (by its date), and the two are put back in the pool's order.
    timed = [k for k, r in enumerate(pool_k) if not r.get("day_only")]
    timed_at = [pool_k[k]["at"] for k in timed]
    days = [k for k, r in enumerate(pool_k) if r.get("day_only")]
    days_at = [pool_k[k]["at"] for k in days]
    memo[key] = (pool_k, timed, timed_at, days, days_at)
    return memo[key]


def bucket(recs: list[dict], instances: list[dict], kinds=None, *, money: bool = False) -> dict[str, list[dict]]:
    """{instance id: records inside it}, read once (records sorted by time, each instance found by bisection)."""
    from bisect import bisect_left, bisect_right
    from heapq import merge
    pool, timed, timed_at, days, days_at = _index(recs, kinds)
    out = {}
    for inst in instances:
        end = inst["money_end"] if money else inst["end"]
        lo, hi = inst["start"], end
        inside = timed[bisect_left(timed_at, lo):bisect_right(timed_at, hi)]
        if days:
            near = days[bisect_left(days_at, lo - timedelta(days=1)):bisect_right(days_at, hi + timedelta(days=1))]
            day_in = [k for k in near if M.in_window(pool[k], inst, money=money)]
            inside = list(merge(inside, day_in)) if day_in else inside
        out[inst["id"]] = [pool[k] for k in inside]
    return out


def _between(times: list, lo, hi) -> list:
    from bisect import bisect_left, bisect_right
    return times[bisect_left(times, lo):bisect_right(times, hi)]


def _covered(cov: dict, person: str, inst: dict, source: str = "phone") -> bool:
    for lo, hi in cov.get(person, {}).get(source, ()):
        if lo <= inst["end"] and hi >= inst["start"]:
            return True
    return False


def _label(people: dict, key: str) -> str:
    return people[key]["label"]


def _row(rid, kind, label, keys, instances, **extra) -> dict:
    return {"id": rid, "link_kind": kind, "label": label, "people": list(keys), "cells": {}, "records": {},
            "times": {}, "weight": "full", **extra}


def _set(row, inst, present: bool, refs=(), first=None, covered=True):
    if present:
        row["cells"][inst["id"]] = "present"
        row["records"][inst["id"]] = list(refs)[:MAX_REFS]
        row.setdefault("record_counts", {})[inst["id"]] = len(list(refs))
        if first is not None:
            row["times"][inst["id"]] = first
    else:
        row["cells"][inst["id"]] = "absent" if covered else "no_data"


def contact_rows(people: dict, recs: list[dict], instances: list[dict], cov: dict) -> list[dict]:
    """Direct contact (a call, message or e-mail with both people on it, in a chat or group they share) and contact
    through a third number (one contacts X, X contacts the other within RELAY_WINDOW)."""
    by_inst = bucket(recs, instances, M.CONTACT_KINDS)
    rows = []
    keys = sorted(people)
    for a, b in combinations(keys, 2):
        row = _row(f"contact:{a}:{b}", "contact", f"{_label(people, a)} and {_label(people, b)} in contact", (a, b),
                   instances)
        relay = _row(f"relay:{a}:{b}", "contact",
                     f"{_label(people, a)} and {_label(people, b)} in contact through a third number within "
                     f"{int(M.RELAY_WINDOW.total_seconds() // 60)} minutes", (a, b), instances)
        for inst in instances:
            inside = by_inst[inst["id"]]
            # ``bucket`` gives each instance's records in time order, so a filter keeps that order (no sort)
            hits = [r for r in inside if {a, b} <= ({r.get("owner")} | set(r.get("parties") or ()))]
            covered = _covered(cov, a, inst) or _covered(cov, b, inst)
            _set(row, inst, bool(hits), [r["ref"] for r in hits], hits[0]["at"] if hits else None, covered)
            chain = _relay(inside, a, b, set(keys))
            _set(relay, inst, bool(chain), chain[1] if chain else (), chain[0] if chain else None, covered)
        rows += [row, relay]
    return rows


def _relay(inside: list[dict], a: str, b: str, pattern: set[str]):
    """(first instant, refs) of a chain a -> X -> b (either direction) through a number that is neither of them."""
    def others(r, who):
        if r.get("owner") == who:
            return {v for v in (r.get("counterpart_values") or ()) if v} - {who}
        return set()
    by_time = inside  # in time order, as ``bucket`` gives them
    for i, r1 in enumerate(by_time):
        for src, dst in ((a, b), (b, a)):
            xs = others(r1, src)
            if not xs:
                continue
            for r2 in by_time[i + 1:]:
                if r2["at"] - r1["at"] > M.RELAY_WINDOW:
                    break
                if r2.get("owner") == dst and xs & set(r2.get("counterpart_values") or ()) and \
                        not ({src, dst} <= ({r2.get("owner")} | set(r2.get("parties") or ()))):
                    return r1["at"], [r1["ref"], r2["ref"]]
    return None


def together_rows(people: dict, recs: list[dict], instances: list[dict], cov: dict) -> list[dict]:
    """Two people's phones placed within each other's accuracy (plus TOGETHER_SLACK_M) inside TOGETHER_GAP. Only
    presence counts: a photo received from someone else places the photographer, not the phone (``media_position``)."""
    pos = _only(recs, "together", lambda r: r["kind"] == "position" and r.get("place") and
                (r["place"].get("radius_m") or 0) <= M.TOGETHER_MAX_RADIUS_M)
    by_inst = bucket(pos, instances)
    rows = []
    for a, b in combinations(sorted(people), 2):
        row = _row(f"together:{a}:{b}", "together", f"{_label(people, a)} and {_label(people, b)} in the same place",
                   (a, b), instances, precision_m=None)
        best = None
        for inst in instances:
            pa = [r for r in by_inst[inst["id"]] if r.get("owner") == a]
            pb = [r for r in by_inst[inst["id"]] if r.get("owner") == b]
            hits, first = [], None
            for x in pa:
                for y in pb:
                    if abs(x["at"] - y["at"]) > M.TOGETHER_GAP:
                        continue
                    ra, rb = x["place"].get("radius_m") or 0, y["place"].get("radius_m") or 0
                    d = M.haversine_m(x["place"]["lat"], x["place"]["lon"], y["place"]["lat"], y["place"]["lon"])
                    if d <= ra + rb + M.TOGETHER_SLACK_M:
                        hits += [x["ref"], y["ref"]]
                        first = min(first or x["at"], x["at"], y["at"])
                        best = max(best or 0, ra, rb)
            covered = bool(pa) and bool(pb)
            _set(row, inst, bool(hits), list(dict.fromkeys(hits)), first, covered)
        row["precision_m"] = best
        rows.append(row)
    return rows


def place_rows(people: dict, recs: list[dict], instances: list[dict], place: dict) -> list[dict]:
    """Each person's phone inside the place asked about (a Map area), on each instance. Only presence counts."""
    pos = [r for r in recs if r["kind"] == "position" and r.get("place")]
    by_inst = bucket(pos, instances)
    rows = []
    for p in sorted(people):
        row = _row(f"place:{p}", "together", f"{_label(people, p)} inside the area chosen", (p,), instances)
        for inst in instances:
            mine = [r for r in by_inst[inst["id"]] if r.get("owner") == p]
            hits = [r for r in mine if M.haversine_m(place["lat"], place["lon"], r["place"]["lat"], r["place"]["lon"])
                    <= place["radius_m"] + (r["place"].get("radius_m") or 0)]
            _set(row, inst, bool(hits), [r["ref"] for r in hits], min((r["at"] for r in hits), default=None), bool(mine))
        rows.append(row)
    return rows


def money_rows(people: dict, recs: list[dict], instances: list[dict], cov: dict) -> list[dict]:
    """Money between two people inside the instance or up to MONEY_SPREAD after it: a ledger payment, or a payment
    alert on a phone (one payment seen both ways counts once). Cash deposits just under $10,000 by one person are a
    row of their own (structuring)."""
    money = _only(recs, "money", lambda r: r["kind"] in M.MONEY_KINDS)
    by_inst = bucket(money, instances, money=True)
    rows = []
    for a, b in combinations(sorted(people), 2):
        for payer, payee in ((a, b), (b, a)):
            hits_any = [r for r in money if r.get("owner") == payer and payee in (r.get("parties") or ())]
            if not hits_any:
                continue
            amounts = sorted({r.get("amount_minor") for r in hits_any if r.get("amount_minor")})
            amount_words = M.fmt_money(amounts[0]) if len(amounts) == 1 else "money"
            row = _row(f"money:{payer}:{payee}", "money",
                       f"{amount_words} from {_label(people, payer)} to {_label(people, payee)}", (payer, payee),
                       instances)
            for inst in instances:
                ids = {id(x) for x in by_inst[inst["id"]]}
                hits = sorted((r for r in hits_any if id(r) in ids), key=lambda r: r["at"])
                covered = any(_covered(cov, p, inst, "ledger") or _covered(cov, p, inst, "alerts") for p in (payer, payee))
                _set(row, inst, bool(hits), [c for r in hits for c in r.get("copies", [r["ref"]])],
                     hits[0]["at"] if hits else None, covered)
            rows.append(row)
    for p in sorted(people):
        deps = [r for r in money if r.get("owner") == p and r.get("cash_deposit") and
                M.STRUCTURING_FROM_MINOR <= abs(r.get("amount_minor") or 0) < M.STRUCTURING_BELOW_MINOR]
        if not deps:
            continue
        row = _row(f"structuring:{p}", "money", f"cash deposit just under $10,000 by {_label(people, p)}", (p,),
                   instances)
        for inst in instances:
            ids = {id(x) for x in by_inst[inst["id"]]}
            hits = [r for r in deps if id(r) in ids]
            covered = _covered(cov, p, inst, "ledger") or _covered(cov, p, inst, "alerts")
            _set(row, inst, bool(hits), [c for r in hits for c in r.get("copies", [r["ref"]])],
                 min((r["at"] for r in hits), default=None), covered)
        rows.append(row)
    return rows


def access_rows(people: dict, recs: list[dict], instances: list[dict], cov: dict) -> list[dict]:
    """Rows of a document (a badge or gate log, an invoice, a report) dated inside the instance and naming the
    person. A document covers the days from its first dated row to its last."""
    docs = [r for r in recs if r["kind"] == "doc_row"]
    rows = []
    for p in sorted(people):
        mine = [r for r in docs if p in (r.get("parties") or ())]
        for source in sorted({r.get("source") or "" for r in mine}):
            these = [r for r in mine if (r.get("source") or "") == source]
            title = these[0].get("source_label") or "a document"
            row = _row(f"access:{p}:{source}", "access", f"{_label(people, p)} named in {title}", (p,), instances)
            by_inst = bucket(these, instances)
            for inst in instances:
                hits = by_inst[inst["id"]]  # in time order, as ``bucket`` gives them
                covered = _covered(cov, f"doc:{source}", inst, "doc")
                _set(row, inst, bool(hits), [r["ref"] for r in hits], hits[0]["at"] if hits else None, covered)
            rows.append(row)
    return rows


def deletion_rows(people: dict, recs: list[dict], instances: list[dict]) -> list[dict]:
    """A message or call one person's phone deleted while another person's phone kept its copy (the copies folded by
    ``model.dedupe``), inside the instance: one row per pair, since the deletion is between the two of them.
    Deleting is an act, so it is compared with the ordinary days like any other signal, and kept apart from how
    often the two are in contact."""
    rows = []
    deleted = _only(recs, "deleted", lambda r: r.get("deleted_by") and r["kind"] in M.CONTACT_KINDS)
    for p in sorted(people):
        for q in sorted(people):
            if q == p:
                continue
            mine = [r for r in deleted if p in r["deleted_by"] and q in (r.get("kept_by") or ())]
            if not mine:
                continue
            row = _row(f"deleted:{p}:{q}", "absence",
                       f"{_label(people, p)}'s phone deleted a message {_label(people, q)}'s phone kept", (p, q),
                       instances)
            by_inst = bucket(mine, instances)
            for inst in instances:
                hits = by_inst[inst["id"]]  # in time order, as ``bucket`` gives them
                _set(row, inst, bool(hits), [x for r in hits for x in r.get("copies") or [r["ref"]]],
                     hits[0]["at"] if hits else None)
            rows.append(row)
    return rows


def absence_rows(people: dict, activity: dict, instances: list[dict], cov: dict) -> list[dict]:
    """A phone with nothing at all (no message, call, position, network or app record) for SILENCE_MIN or longer
    inside the hours asked about, while it holds records before and after them. ``activity`` is
    ``{person: [instants]}`` read for the phones' every record kind."""
    rows = []
    for p in sorted(people):
        times = sorted(activity.get(p) or ())
        if not times:
            continue
        row = _row(f"absence:{p}", "absence", f"{_label(people, p)}'s phone silent for "
                   f"{int(M.SILENCE_MIN.total_seconds() // 3600)} hours or more", (p,), instances, gaps={})
        for inst in instances:
            before = [t for t in _between(times, inst["start"] - timedelta(hours=24), inst["start"]) if t < inst["start"]]
            after = [t for t in _between(times, inst["end"], inst["end"] + timedelta(hours=24)) if t > inst["end"]]
            inside = _between(times, inst["start"], inst["end"])
            if not before or not after:
                _set(row, inst, False, covered=False)
                continue
            marks = [before[-1]] + inside + [after[0]]
            gap = max(((b - a, a, b) for a, b in zip(marks, marks[1:])), key=lambda g: g[0])
            lo, hi = max(gap[1], inst["start"]), min(gap[2], inst["end"])
            silent = hi - lo >= M.SILENCE_MIN
            if silent:
                row["gaps"][inst["id"]] = {"from": M.iso(gap[1]), "to": M.iso(gap[2])}
            _set(row, inst, silent, [], lo if silent else None, True)
        rows.append(row)
    return rows


def content_rows(people: dict, recs: list[dict], instances: list[dict], phrase_counts: dict) -> list[dict]:
    """The same words in records of two different people (not copies of one record) inside an instance. A word run
    used in RARE_PHRASE_MAX records of the case or fewer counts; one used STOCK_PHRASE_MIN times or more is a stock
    phrase and is weighed low (``checks`` reports it)."""
    comms = _only(recs, "comms", lambda r: r["kind"] in M.CONTACT_KINDS and r.get("body") and r.get("sender"))
    found: dict[str, dict] = {}
    by_inst = bucket(comms, instances)
    for inst in instances:
        inside = by_inst[inst["id"]]
        by_phrase: dict[str, list[dict]] = defaultdict(list)
        for r in inside:
            for ph in M.phrase_tuple(r["body"]):
                by_phrase[ph].append(r)
        for ph, rs in by_phrase.items():
            senders = {r["sender"] for r in rs}
            if len(senders) < 2 or not senders <= set(people):
                continue
            n = phrase_counts.get(ph)
            if n is None or RARE_PHRASE_MAX < n < STOCK_PHRASE_MIN:
                continue
            row = found.setdefault(ph, _row(f"content:{ph}", "shared_content",
                                            f"the same words “{ph}” from {' and '.join(_label(people, s) for s in sorted(senders))}",
                                            sorted(senders), instances, phrase=ph, case_count=n))
            row["cells"][inst["id"]] = "present"
            row["records"][inst["id"]] = [r["ref"] for r in rs][:MAX_REFS]
            row["times"][inst["id"]] = min(r["at"] for r in rs)
            if n >= STOCK_PHRASE_MIN:
                row["weight"], row["why_low"] = "low", f"a stock phrase, in {n:,} records of the case"
    for row in found.values():
        for inst in instances:
            row["cells"].setdefault(inst["id"], "absent")
    rows = list(found.values())
    # keep the rarer phrases first, and only the three most telling of one pair, so the grid stays readable; the
    # rest are counted on the first row
    rows.sort(key=lambda r: (r["case_count"], r["phrase"]))
    kept, extra = [], defaultdict(int)
    for r in rows:
        pair = tuple(r["people"])
        if sum(1 for k in kept if tuple(k["people"]) == pair) >= 3:
            extra[pair] += 1
            continue
        kept.append(r)
    for r in kept:
        if extra.get(tuple(r["people"])):
            r["more_phrases"] = extra[tuple(r["people"])]
    return kept


def activity_row(people: dict, activity: dict, instances: list[dict], window=timedelta(minutes=30)) -> dict | None:
    """Every person's phone active within one stretch of ``window`` inside the instance (a burst). This only says the
    phones were busy at once; it is never contact between them."""
    keys = sorted(people)
    if len(keys) < 2 or any(not activity.get(k) for k in keys):
        return None
    row = _row("activity:all", "activity", f"all {len(keys)} phones active within the same "
               f"{int(window.total_seconds() // 60)} minutes", keys, instances, context=True)
    # each list sorted once, not once per instance; a burst found by bisection, not every pair (Phone reference 1,
    # 18 Nov: this row was 83% of a lead finder weighing)
    from bisect import bisect_left
    times = {k: sorted(activity[k]) for k in keys}
    for inst in instances:
        per = {k: _between(times[k], inst["start"], inst["end"]) for k in keys}
        if any(not v for v in per.values()):
            covered = all(_between(times[k], inst["start"] - timedelta(hours=24),
                                   inst["end"] + timedelta(hours=24)) for k in keys)
            _set(row, inst, False, covered=covered)
            continue
        hit = None
        for t in sorted(x for v in per.values() for x in v):
            if all((i := bisect_left(v, t)) < len(v) and v[i] <= t + window for v in per.values()):
                hit = t
                break
        _set(row, inst, hit is not None, [], hit, True)
    return row


def sequence_row(rows: list[dict], instances: list[dict], minimum: int = 3) -> dict | None:
    """The same order of three or more signals in each of several incidents: A before B before C. Present in an
    instance whose signals fall in that order; absent where at least two of them are present out of order."""
    incidents = [i for i in instances if i["side"] == "incident"]
    if len(incidents) < 2:
        return None
    timed = [r for r in rows if r["link_kind"] not in ("activity",) and r.get("weight") == "full" and
             sum(1 for i in incidents if r["cells"].get(i["id"]) == "present" and r["times"].get(i["id"])) >= 2]
    if len(timed) < minimum:
        return None

    def order(inst):
        got = [(r["times"][inst["id"]], r["id"]) for r in timed if r["cells"].get(inst["id"]) == "present" and
               r["times"].get(inst["id"])]
        return [rid for _, rid in sorted(got)]
    orders = {i["id"]: order(i) for i in incidents}
    common = None
    for o in orders.values():
        if len(o) >= minimum:
            common = o if common is None else [x for x in common if x in o]
    if not common or len(common) < minimum:
        return None
    labels = {r["id"]: r["label"] for r in timed}
    row = _row("sequence:" + ">".join(common), "sequence",
               "the same order each time: " + ", then ".join(labels[x] for x in common), [], instances,
               order=common)
    for inst in instances:
        o = [x for x in order(inst) if x in common]
        if len(o) >= minimum and o == [x for x in common if x in o] and len(o) == len(common):
            _set(row, inst, True, [], None)
        else:
            _set(row, inst, False, covered=len(o) >= 2 or inst["side"] == "ordinary")
    return row


def statement_rows(people: dict, recs: list[dict], activity: dict, instances: list[dict], doc_points: list[dict],
                   zone: str, slack=timedelta(minutes=15)) -> list[dict]:
    """A document's or statement's dated lines against the phones: for each person it names, is their phone active
    within ``slack`` of the times it gives? On ordinary instances the same times of day are tested, so a phone that is
    always busy at that hour does not count as agreement."""
    tzz = M.tz(zone)
    rows = []
    for p in sorted(people):
        mine = [d for d in doc_points if p in (d.get("people") or ())]
        if not mine or not activity.get(p):
            continue
        tods = sorted({(d["at"].astimezone(tzz).hour, d["at"].astimezone(tzz).minute) for d in mine})
        times = sorted(activity[p])
        row = _row(f"statement:{p}", "statement", f"{_label(people, p)}'s phone active at the times the document gives",
                   (p,), instances)
        for inst in instances:
            start_local = inst["start"].astimezone(tzz)
            targets = []
            for h, m in tods:
                t = start_local.replace(hour=h, minute=m, second=0, microsecond=0)
                if t < start_local:
                    t += timedelta(days=1)
                if t.astimezone(M.timezone.utc) <= inst["end"]:
                    targets.append(t.astimezone(M.timezone.utc))
            if not targets:
                _set(row, inst, False, covered=False)
                continue
            hit = [t for t in targets if _between(times, t - slack, t + slack)]
            covered = bool(_between(times, inst["start"] - timedelta(hours=24), inst["end"] + timedelta(hours=24)))
            _set(row, inst, len(hit) == len(targets), [d["ref"] for d in mine][:MAX_REFS] if inst["side"] == "incident"
                 else [], min(hit) if hit else None, covered)
        rows.append(row)
    return rows
