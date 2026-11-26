"""Around a moment, on every phone in scope (phones redesign screen 4).

One window, one lane per phone: messages and calls, places, and use of the phone (the incident window's lanes,
``pattern_of_life.day.window``). Time a phone was not recording is drawn apart from quiet time: an hour is "not
recording" by the Timeline's own rule (``timeline_lens._no_data_hours``: after the extraction, powered off, or no data
and no record held). Every pair of phones in scope gets a together-and-apart strip from the Together pair rule
(``pattern_of_life.colocation.compute``, read-only, nothing stored), so the strip and the Together screen cannot
disagree. The records list holds each message or call once with every phone that holds it (Compare phones' pairing
rule, as on screen 3), every place point and every stretch of not recording; every item is returned.

Decisions (reverse by editing the named constant): ``MAX_WINDOW`` = 7 days (a lane drawn wider than a week cannot
show single records); ``STRIP_SLOTS`` = 12 slots per strip, as the design.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import text

from services.phone import person_across as PA
from services.phone import readings

MAX_WINDOW = timedelta(days=7)
STRIP_SLOTS = 12
DELETED = ("Deleted", "Trash")
TOGETHER_WORDS = ("Two phones are together when their places, with each place's accuracy, overlap within 5 minutes "
                  "(within 150 m counts as together; coarser places only as possibly together), and apart when they "
                  "are further apart than anyone could cover at 144 km/h in the time between.")
STRIP_WORDS = {"together": "Together (within 150 m)", "maybe": "Possibly together (the places are too coarse to say)",
               "apart": "Apart", "unknown": "Not known: no places to compare"}


def parse_instant(value: str, name: str) -> datetime:
    try:
        out = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise ValueError("'%s' is not a date and time." % name)
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)


def hm(t, a, b) -> str:
    """A time in the window's words: "13:05", "26 Mar 01:00" on another day, "the end of the window" at its end."""
    if t >= b:
        return "the end of the window"
    return t.strftime("%H:%M") if t.date() == a.date() else t.strftime("%-d %b %H:%M")


def _hour(t):
    return t.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def not_recording(conn, ext, a, b) -> list[dict]:
    """Stretches of ``[a, b)`` in which phone ``ext`` was not recording, merged from whole hours and clipped to the
    window."""
    from services.phone import timeline_lens
    hours = sorted(timeline_lens._no_data_hours(conn, ext, _hour(a), _hour(b) + timedelta(hours=1)))
    out = []
    for h in hours:
        s, e = max(h, a), min(h + timedelta(hours=1), b)
        if s >= e:
            continue
        if out and out[-1]["end"] >= s:
            out[-1]["end"] = max(out[-1]["end"], e)
        else:
            out.append({"start": s, "end": e})
    return out


def strip(episodes, a, b, slots=STRIP_SLOTS) -> list[dict]:
    """The window cut into ``slots`` equal slots, each ``together`` (a tight together episode overlaps it),
    ``maybe`` (only a broad one), ``apart`` (an apart episode and no together one) or ``unknown``."""
    step = (b - a) / slots
    out = []
    for i in range(slots):
        s, e = a + step * i, a + step * (i + 1)
        over = [x for x in episodes if x["start"] <= e and x["end"] >= s]
        if any(x["kind"] == "together" and x.get("breadth") == "tight" for x in over):
            st = "together"
        elif any(x["kind"] == "together" for x in over):
            st = "maybe"
        elif any(x["kind"] == "apart" for x in over):
            st = "apart"
        else:
            st = "unknown"
        out.append({"start": s.isoformat(), "end": e.isoformat(), "state": st})
    return out


def _pair_words(la, lb, episodes):
    tog = [x for x in episodes if x["kind"] == "together"]
    apart = [x for x in episodes if x["kind"] == "apart"]
    if not tog and not apart:
        return "%s and %s: no places close enough in time to compare." % (la, lb)
    parts = []
    if tog:
        parts.append("together %s" % ", ".join("%s to %s%s" % (x["start"].strftime("%H:%M"), x["end"].strftime("%H:%M"),
                                                              "" if x.get("breadth") == "tight" else " (broad)")
                                                for x in tog))
    if apart:
        parts.append("apart %s" % ", ".join("%s to %s" % (x["start"].strftime("%H:%M"), x["end"].strftime("%H:%M"))
                                             for x in apart))
    return "%s and %s: %s (UTC)." % (la, lb, "; ".join(parts))


def moment(conn, case_id, start: str, end: str, phones=None) -> dict:
    from services.pattern_of_life import colocation, day
    case_id = str(case_id)
    a, b = parse_instant(start, "from"), parse_instant(end, "to")
    if b <= a:
        raise ValueError("The end of the window must be after its start.")
    if b - a > MAX_WINDOW:
        raise ValueError("Choose a window of 7 days or less.")
    scope = PA.active_phones(conn, case_id, phones)
    labels = readings.phone_labels(conn, case_id)
    lab = (lambda e: labels.get(e, "A phone"))
    w = day.window(conn, scope, labels, a, b, include_passive=False, case_id=case_id)
    lanes = w["lanes"]
    from services.phone import labels as L
    ctx = L.LabelContext(conn, case_id, "phone")

    gaps = {e: not_recording(conn, e, a, b) for e in scope}
    phones_out = []
    for e in scope:
        comm = [x for x in lanes["communications"] if x["extraction_id"] == e]
        pl = [x for x in lanes["places"] if x["extraction_id"] == e]
        use = [x for x in lanes["interaction"] if x["extraction_id"] == e]
        phones_out.append({
            "extraction_id": e, "label": lab(e), "owner": PA._owner_name(ctx, e),
            "not_recording": [{"start": g["start"].isoformat(), "end": g["end"].isoformat()} for g in gaps[e]],
            "marks": sorted([{"kind": x["kind"] if x["kind"] in ("message", "call") else "message",
                              "at": x["at"].isoformat(), "record_uid": x["record_uid"]} for x in comm] +
                            [{"kind": "place", "at": x["at"].isoformat(), "record_uid": x["record_uid"]} for x in pl] +
                            [{"kind": "use", "at": x["at"].isoformat(), "record_uid": x["record_uid"]} for x in use],
                            key=lambda m: m["at"]),
            "counts": {"messages": sum(1 for x in comm if x["kind"] == "message"),
                       "calls": sum(1 for x in comm if x["kind"] == "call"), "places": len(pl), "use": len(use)}})

    pairs = []
    for (x, y), (_, counts, eps) in colocation.compute_pairs(conn, case_id, scope, a, b).items():
        pairs.append({"phones": [x, y], "strip": strip(eps, a, b),
                      "episodes": [{"kind": ep["kind"], "start": ep["start"].isoformat(), "end": ep["end"].isoformat(),
                                    "breadth": ep.get("breadth"), "items": ep["items"]} for ep in eps],
                      "compared": int(counts.get("pairs", 0)), "words": _pair_words(lab(x), lab(y), eps)})

    records = _records(conn, case_id, lanes, gaps, scope, lab, ctx, a, b)
    places = [{"extraction_id": x["extraction_id"], "at": x["at"].isoformat(), "lat": x["lat"], "lon": x["lon"],
               "radius_m": x["radius_m"], "record_uid": x["record_uid"]} for x in lanes["places"]
              if x["lat"] is not None and x["lon"] is not None]
    n_rec = sum(1 for r in records if r["kind"] != "not_recording")
    holding = len({e for r in records if r["kind"] != "not_recording" for e in r["on"]})
    gap_words = ["%s has none from %s to %s because it was not recording." % (
        lab(e), hm(g["start"], a, b), hm(g["end"], a, b)) for e in scope for g in gaps[e]]
    summary = "%d %s in this window on %d %s." % (n_rec, "record" if n_rec == 1 else "records", holding,
                                                  "phone" if holding == 1 else "phones")
    out = {"case_id": case_id, "from": a.isoformat(), "to": b.isoformat(), "zone": "UTC", "phones": phones_out,
           "pairs": pairs, "records": records, "places": places,
           "summary": " ".join([summary] + gap_words[:3] + (["%d more stretches of not recording are listed below."
                                                             % (len(gap_words) - 3)] if len(gap_words) > 3 else [])),
           "strip_words": STRIP_WORDS, "together_rule": TOGETHER_WORDS}
    out["next_steps"] = next_steps(out, lab, a, b)
    return out


def _records(conn, case_id, lanes, gaps, scope, lab, ctx, a, b) -> list[dict]:
    comm = lanes["communications"]
    body = {str(r.event_uid): r for r in conn.execute(text(
        "SELECT event_uid, body, call_duration_s, app, kind, direction FROM pv_comm_event WHERE event_uid = "
        "ANY(CAST(:u AS uuid[]))"), {"u": [x["id"] for x in comm]})} if comm else {}
    rows = [SimpleNamespace(extraction_id=x["extraction_id"], kind=x["kind"], app=x["source_app"],
                            sort_instant=x["at"], body=getattr(body.get(x["id"]), "body", None),
                            call_duration_s=getattr(body.get(x["id"]), "call_duration_s", None),
                            direction=x["direction"], event_uid=x["id"]) for x in comm]
    out = []
    for g in PA.contacts(rows, scope):
        first = comm[g[0]]
        on = sorted({comm[i]["extraction_id"] for i in g}, key=scope.index)
        names = [p.get("name") or p.get("identifier") for p in first["parties"] if p.get("name") or p.get("identifier")]
        owner = PA._owner_name(ctx, first["extraction_id"]) or lab(first["extraction_id"])
        who = ("%s → %s" % (owner, ", ".join(names) or "unknown") if first["direction"] == "outgoing" else
               "%s → %s" % (", ".join(names) or "unknown", owner) if first["direction"] == "incoming" else
               ", ".join([owner] + names))
        r = rows[g[0]]
        if first["kind"] == "call":
            d = r.call_duration_s
            txt = "Call%s" % (", %d min" % round(float(d) / 60) if d and float(d) >= 60 else
                              ", %d s" % float(d) if d else "")
        else:
            txt = r.body or "(no text)"
        deleted = sorted({comm[i]["extraction_id"] for i in g if comm[i]["deleted_state"] in DELETED}, key=scope.index)
        out.append({"kind": first["kind"], "at": first["at"].isoformat(), "on": on, "app": first["source_app"],
                    "who": who, "text": txt, "deleted_on": deleted,
                    "record_uids": [comm[i]["record_uid"] for i in g]})
    for x in lanes["places"]:
        acc = ", accuracy %d m" % round(x["radius_m"]) if x["radius_m"] is not None else ""
        out.append({"kind": "place", "at": x["at"].isoformat(), "on": [x["extraction_id"]], "app": x["source_app"],
                    "who": None, "text": "%.5f, %.5f%s" % (x["lat"], x["lon"], acc) if x["lat"] is not None else
                    "A place with no coordinates", "deleted_on": [], "record_uids": [x["record_uid"]] if
                    x["record_uid"] else []})
    for e in scope:
        for gp in gaps[e]:
            out.append({"kind": "not_recording", "at": gp["start"].isoformat(), "end": gp["end"].isoformat(),
                        "on": [e], "app": None, "who": None,
                        "text": "No records until %s: the phone was not recording" % hm(gp["end"], a, b),
                        "deleted_on": [], "record_uids": []})
    out.sort(key=lambda r: (r["at"], r["kind"] == "not_recording"))
    return out


def next_steps(out, lab, a, b) -> list[dict]:
    steps = []
    gaps = [(p, g) for p in out["phones"] for g in p["not_recording"]]
    if gaps:
        p, g = max(gaps, key=lambda pg: datetime.fromisoformat(pg[1]["end"]) - datetime.fromisoformat(pg[1]["start"]))
        who = p["owner"] or p["label"]
        g0, g1 = datetime.fromisoformat(g["start"]), datetime.fromisoformat(g["end"])
        steps.append({"code": "search_gap", "title": "Find where %s was from %s to %s" % (
            who, hm(g0, a, b), hm(g1, a, b)),
            "why": "%s was not recording then. The other phones and the payments in that time may place them."
            % p["label"], "action": "Search that time", "from": g["start"], "to": g["end"]})
    dels = [r for r in out["records"] if r["deleted_on"]]
    if dels:
        r = dels[0]
        steps.append({"code": "open_deleted", "title": "Read the deleted %s message in its thread" % r["at"][11:16],
                      "why": "Deleted on %s%s." % (" and ".join(map(lab, r["deleted_on"])),
                                                   ", and kept on %s" % " and ".join(
                                                       lab(e) for e in r["on"] if e not in r["deleted_on"])
                                                   if len(r["on"]) > len(r["deleted_on"]) else ""),
                      "action": "Open the thread", "record_uid": r["record_uids"][0]})
    tog = [p for p in out["pairs"] if any(e["kind"] == "together" for e in p["episodes"])]
    if tog:
        p = tog[0]
        steps.append({"code": "corroborate", "title": "Test whether %s and %s are together at other key times"
                      % tuple(lab(e) for e in p["phones"]), "why": p["words"], "action": "Corroborate",
                      "phones": p["phones"]})
    shared = [r for r in out["records"] if len(r["on"]) > 1]
    if shared:
        steps.append({"code": "compare", "title": "Compare what the phones hold for this window",
                      "why": "%d %s here %s on more than one phone." % (
                          len(shared), "record" if len(shared) == 1 else "records",
                          "is" if len(shared) == 1 else "are"), "action": "Open the list"})
    if b - a < timedelta(hours=24):
        d0 = a.replace(hour=0, minute=0, second=0, microsecond=0)
        steps.append({"code": "wider", "title": "Widen to the whole of %s" % d0.strftime("%-d %B %Y"),
                      "why": "See what led up to this window and what followed on all %d phones." % len(out["phones"]),
                      "action": "Show the whole day", "from": d0.isoformat(),
                      "to": (d0 + timedelta(days=1)).isoformat()})
    for i, s in enumerate(steps):
        s["rank"] = i + 1
    return steps
