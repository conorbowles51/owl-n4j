"""Weighing a confirmed claim against the phones (lx-corrostatement D).

The result is ``fits``, ``contradicts`` or ``cant_tell``, from rules only. The window is the one the person
confirmed. The same records the engine reads (``store.records``: positions, messages, calls) are read for the window
and the same place test as ``signals.place_rows`` is used (a position counts as inside when its distance from the
place is within the place's radius plus the position's own). A claim that cannot be weighed says which field is missing
or what was searched and found empty. Nothing here is a model reading.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from services.corroborate import model as M

SCHEMA = "loupe.corroborate/1"
OUTSIDE_MARGIN_M = 100.0     # a position this far past the place's edge is clearly elsewhere
TOGETHER_M = 300.0
TOGETHER_MIN = 15
COMM_KINDS = ("message", "call", "email", "chat")
VERDICTS = {"fits": "Fits", "contradicts": "Contradicts", "cant_tell": "Can't tell"}
MAX_CITED = 12


def _dt(v):
    return M.as_utc(datetime.fromisoformat(str(v).replace("Z", "+00:00")))


def _local(t, zone):
    return t.astimezone(M.tz(zone)).strftime("%H:%M")


def run(store, claim, question: dict | None = None, started: float | None = None) -> dict[str, Any]:
    started = started or time.time()
    c = claim.confirmed or {}
    zone = store.zone()
    everyone = {p["key"]: p for p in store.people()}
    who = [w["key"] for w in c.get("who") or [] if w["key"] in everyone]
    what = c.get("what") or {}
    when, where = c.get("when"), c.get("where")
    missing = []
    if not who:
        missing.append("who")
    if not when:
        missing.append("when")
    if not what:
        missing.append("what")
    if what.get("action") == "presence" and not where:
        missing.append("where")
    counter = [k for k in (what.get("with") or []) if k in everyone] if what.get("action") in ("contact", "with") else []
    if what.get("action") in ("contact", "with") and not counter:
        missing.append("who they were with" if what["action"] == "with" else "who was contacted")
    out = {"schema": SCHEMA, "claim": {"id": str(claim.id), "sentence": claim.sentence,
                                       "confirmed_by": claim.confirmed_by_name, "chips": c, "edited": list(claim.edited or [])}}
    people = {k: everyone[k] for k in dict.fromkeys(who + counter)}
    if missing:
        return _result(out, store, people, "cant_tell", f"Can't tell: the claim does not say {', '.join(missing)}.",
                       [f"The claim has no {m}, so there is nothing to compare with the records." for m in missing],
                       [{"missing": m, "words": f"{m}: not stated (or not confirmed)."} for m in missing], {}, [], started, zone)
    lo, hi = _dt(when["start"]), _dt(when["end"])
    pad = timedelta(minutes=5)
    recs, _ = M.dedupe(store.records(list(people.values()), [(lo - pad, hi + pad)], list(everyone.values())))
    recs = [r for r in recs if lo - pad <= r["at"] <= hi + pad]
    kinds: dict[str, int] = {}
    for r in recs:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    action, neg = what["action"], bool(what.get("negated"))
    if action == "presence":
        verdict, reasons, gaps, cited = _presence(people, who, where, recs, lo, hi, zone, neg, store)
    elif action == "contact":
        verdict, reasons, gaps, cited = _contact(people, who[0], counter, recs, lo, hi, zone, neg, store)
    else:
        verdict, reasons, gaps, cited = _with(people, who[0], counter, recs, lo, hi, zone, neg)
    searched = {"records_read": kinds, "window": {"start": lo.isoformat(), "end": hi.isoformat(), "zone": zone,
                                                   "label": when.get("label")}, "people": len(people),
                "phones": [e for p in people.values() for e in p["phones"]]}
    head = {"fits": "Fits the records.", "contradicts": "Contradicts the records.",
            "cant_tell": "Can't tell: " + (gaps[0]["words"] if gaps else "the records do not settle it") }[verdict]
    return _result(out, store, people, verdict, head, reasons, gaps, searched, cited, started, zone)


def _result(out, store, people, verdict, sentence, reasons, gaps, searched, cited, started, zone):
    from services.corroborate.engine import _person
    level = {"key": "cant_tell" if verdict == "cant_tell" else f"claim_{verdict}", "name": VERDICTS[verdict],
             "rule": "claim", "reasons": reasons, "comparison": "", "separating_kinds": [], "repeated": False,
             "sentence": sentence, "verdict": verdict}
    out.update({"question": {"kind": "statement", "text": f"Does the claim fit the records? “{out['claim']['sentence']}”",
                             "chips": {"claim_id": out["claim"]["id"], "people": list(people)}},
                "level": level, "comparison": {"kind": None, "words": "", "zone": zone, "incident": [], "ordinary": []},
                "grid": [], "checks": [], "people": [_person(p) for p in people.values()], "not_in_pattern": [],
                "searched": searched, "gaps": gaps, "look_further": [], "unread": [], "notes": [],
                "case_facts_used": [], "cited": cited[:MAX_CITED], "seconds": round(time.time() - started, 2)})
    return out


def _inside(pos, where):
    d = M.haversine_m(where["lat"], where["lon"], pos["place"]["lat"], pos["place"]["lon"])
    edge = where["radius_m"] + (pos["place"].get("radius_m") or 0)
    return d <= edge, d - edge


def _presence(people, who, where, recs, lo, hi, zone, neg, store):
    reasons, gaps, cited, verdicts = [], [], [], []
    place = where.get("name") or "the place"
    for k in who:
        label = people[k]["label"]
        pos = sorted((r for r in recs if r["kind"] == "position" and r.get("owner") == k and r.get("place")),
                     key=lambda r: r["at"])
        if not people[k]["phones"]:
            gaps.append({"missing": f"a phone for {label}", "words": f"no phone of {label} is in the case."})
            verdicts.append("cant_tell")
            continue
        if not pos:
            active = sum(1 for r in recs if r.get("owner") == k)
            gaps.append({"missing": f"positions of {label}'s phone in the window",
                         "words": f"{label}'s phone holds no positions between {_local(lo, zone)} and {_local(hi, zone)}"
                                  + (f" ({active} other records in it, none with a position)." if active else
                                     " and no other records either.")})
            verdicts.append("cant_tell")
            continue
        ins, outs = [], []
        for r in pos:
            ok, over = _inside(r, where)
            (ins if ok else outs).append((r, over))
        far = [x for x in outs if x[1] > OUTSIDE_MARGIN_M]
        if ins and not far:
            v = "fits"
        elif far and not ins:
            v = "contradicts"
        elif ins and far:
            v = "cant_tell"
            gaps.append({"missing": "a single answer from the positions",
                         "words": f"{label}'s phone is inside {place} at {len(ins)} of {len(pos)} positions and clearly "
                                  f"elsewhere at {len(far)}: the positions disagree."})
        else:
            v = "cant_tell"
            gaps.append({"missing": "a clear position", "words": f"{label}'s {len(pos)} positions are outside {place} "
                         f"but within {int(OUTSIDE_MARGIN_M)} m of its edge, too close to call."})
        if neg and v in ("fits", "contradicts"):
            v = "contradicts" if v == "fits" else "fits"
        verdicts.append(v)
        first = pos[0]
        reasons.append(f"{label}'s phone gave {len(pos)} position{'' if len(pos) == 1 else 's'} between "
                       f"{_local(lo, zone)} and {_local(hi, zone)}: {len(ins)} inside {place}, {len(outs)} outside"
                       + (f"; the nearest outside is {int(min(o for _, o in outs) + where['radius_m'])} m from its centre" if outs else "")
                       + ".")
        cited += [{"ref": r["ref"], "at": r["at"].isoformat(), "person": label, "inside": ok_} for r, ok_ in
                  ((r, _inside(r, where)[0]) for r in pos[:6])]
    return _combine(verdicts), reasons, gaps, cited


def _combine(vs):
    if not vs or "cant_tell" in vs:
        return "cant_tell"
    return "contradicts" if "contradicts" in vs else "fits"


def _contact(people, a, others, recs, lo, hi, zone, neg, store):
    reasons, gaps, cited, verdicts = [], [], [], []
    for b in others:
        la, lb = people[a]["label"], people[b]["label"]
        hits = [r for r in recs if r["kind"] in COMM_KINDS and ((r.get("owner") == a and b in (r.get("parties") or ())) or
                                                                  (r.get("owner") == b and a in (r.get("parties") or ())))]
        if hits:
            v = "fits"
            reasons.append(f"{len(hits)} contact{'' if len(hits) == 1 else 's'} between {la} and {lb} in the window, the first at {_local(hits[0]['at'], zone)}.")
            cited += [{"ref": r["ref"], "at": r["at"].isoformat(), "kind": r["kind"]} for r in hits[:6]]
        else:
            # absence counts only when a phone of both sat in use around the window
            act = store.activity([people[a], people[b]], [(lo, hi)])
            near = {k: any(lo - timedelta(hours=1) <= t <= hi + timedelta(hours=1) for t in act.get(k, [])) for k in (a, b)}
            if all(near.values()):
                v = "contradicts"
                reasons.append(f"No call or message between {la} and {lb} in the window, though both phones hold records "
                               "within an hour of it.")
            else:
                v = "cant_tell"
                lacking = [people[k]["label"] for k in (a, b) if not near[k]]
                gaps.append({"missing": "phone records around the window", "words": f"no records of {', '.join(lacking)}'s phone "
                             "within an hour of the window, so a missing contact says nothing."})
        if neg and v in ("fits", "contradicts"):
            v = "contradicts" if v == "fits" else "fits"
        verdicts.append(v)
    return _combine(verdicts), reasons, gaps, cited


def _with(people, a, others, recs, lo, hi, zone, neg):
    reasons, gaps, cited, verdicts = [], [], [], []
    pa = sorted((r for r in recs if r["kind"] == "position" and r.get("owner") == a and r.get("place")), key=lambda r: r["at"])
    for b in others:
        la, lb = people[a]["label"], people[b]["label"]
        pb = [r for r in recs if r["kind"] == "position" and r.get("owner") == b and r.get("place")]
        if not pa or not pb:
            lacking = [people[k]["label"] for k, ps in ((a, pa), (b, pb)) if not ps]
            gaps.append({"missing": "positions in the window", "words": f"no positions of {', '.join(lacking)}'s phone in the window."})
            verdicts.append("cant_tell")
            continue
        pairs = [(x, y) for x in pa for y in pb if abs((x["at"] - y["at"]).total_seconds()) <= TOGETHER_MIN * 60 and
                 M.haversine_m(x["place"]["lat"], x["place"]["lon"], y["place"]["lat"], y["place"]["lon"]) <=
                 TOGETHER_M + (x["place"].get("radius_m") or 0) + (y["place"].get("radius_m") or 0)]
        v = "fits" if pairs else "contradicts"
        reasons.append(f"{la} and {lb} were within {int(TOGETHER_M)} m and {TOGETHER_MIN} minutes of each other at "
                       f"{len(pairs)} of {len(pa)} of {la}'s positions." if pairs else
                       f"{la}'s {len(pa)} positions and {lb}'s {len(pb)} are never within {int(TOGETHER_M)} m of each other "
                       f"inside {TOGETHER_MIN} minutes.")
        if pairs:
            cited += [{"ref": x["ref"], "at": x["at"].isoformat(), "person": la} for x, _ in pairs[:3]] + \
                     [{"ref": y["ref"], "at": y["at"].isoformat(), "person": lb} for _, y in pairs[:3]]
        if neg:
            v = "contradicts" if v == "fits" else "fits"
        verdicts.append(v)
    return _combine(verdicts), reasons, gaps, cited
