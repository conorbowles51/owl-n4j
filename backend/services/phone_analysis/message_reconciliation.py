"""Approach 2: cross-phone message reconciliation (docs/cellebrite/05 section 5; unit 05-S5).

For every candidate pair of phones in the case (5.3.1), each message is matched to its copy on the other phone with
the keys of 5.3.2: K1 platform family, K2 complementary direction against 02's owner identities, K3 the sender on
one side is the other phone's owner's counterpart, K4 the normalised body (or the attachment MD5s), K5 time within
tau after the pair's clock offset. Tiers (5.3.3), greedy one-to-one assignment with ties left out (5.3.4), the
clock offset per pair, family and timestamp class (5.3.5) and the outcomes of 5.3.6.

The gate (5.6) passed on the server corpus: 814 matched_strong and 186 deleted on one side in the 10-report case.

Decisions (05 section 19, 19.S5-a to 19.S5-g):

- 19.S5-a A phone's owner identities are 02's owner (`identities.owner`: a recorded decision, else the computed
  owner) plus the owner accounts 02 lists (candidate kind `account`), each read through reviewed persons.
- 19.S5-b A match whose copies differ Intact against Deleted or Trash is one result, kind `deleted_one_side`;
  it is also recovered from the other side, so the intact copy carries the role `recovered_copy` and the result
  names the phone it is read from. No record is changed.
- 19.S5-c Drift uses the Theil-Sen slope with Sen's distribution-free 95 percent interval (Kendall's S variance)
  instead of 1,000 bootstrap resamples: the bootstrap costs 1,000 x n^2 slopes (about 250 million at the measured
  496 pairs) inside one run.
- 19.S5-d "Counterpart has no data for that app in that period" is read from the counterpart's own messages of
  that family: the message time lies before its first or after its last message of the family. 04's per-app
  band does not exist (as 19.S6-b).
- 19.S5-e `one_side_only` is computed only for messages between the two phones' owners (the sender is one
  phone's owner and the other phone's owner is a recipient or participant); a message to a third person is not
  expected on the other phone.
- 19.S5-f Copies of one message on one phone (02's duplicate group) count once: the first record of the group.
- 19.S5-g Reasons not computed yet: the counterpart's gap (approach 3 holes) and leaving a group before the time
  (ChatActivity parties are "participant named", 19.S7-b, so who left is not established).
"""
from __future__ import annotations

import bisect
import math
import statistics
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations

from sqlalchemy import text

from services.phone import identities
from services.phone.fold import STYLED, _WS, _strip_format
from services.phone_analysis import fields as FV

CODE = "message_reconciliation"
VERSION = "2.3"
PARAMETERS = {
    "tau_s": {"type": "number", "default": 120, "min": 1, "max": 3600,
              "label": "Seconds two copies may differ after the clock offset"},
    "offset_window_h": {"type": "number", "default": 24, "min": 1, "max": 72,
                        "label": "Hours searched to estimate a clock offset"},
}
KINDS = ("both_sides", "deleted_one_side", "one_side_only", "ambiguous_pair", "clock_offset")
SUPPORTS = ("content_equal", "attachment_equal", "time_agrees", "participants_agree", "reviewed_merge")
UNDERCUTS = ("identity_unreviewed", "server_stamped", "clock_offset_unknown", "multi_device_account",
             "edited_or_recalled", "media_recompressed", "counterpart_extraction_ended", "counterpart_app_no_data",
             "counterpart_owner_unknown")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [
    {"code": "messages", "label": "Messages with a time"},
    {"code": "owner", "label": "Known owner identities"},
]
DELETED = ("Deleted", "Trash")
MIN_BODY = 10
MAX_OCCURRENCES = 3
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def norm_body(body) -> str:
    """K4: NFKC, decorative letters folded (03's table), format and zero-width characters removed, casefold,
    whitespace collapsed and trimmed. Punctuation and emoji are kept."""
    s = unicodedata.normalize("NFKC", body or "")
    s = "".join(STYLED.get(c, c) for c in s)
    s = _strip_format(s).casefold()
    return _WS.sub(" ", s).strip()


def family(app, mtype) -> str:
    """K1: `sms` for Sms and Mms, `imessage`, else the app name casefolded."""
    if mtype in ("Sms", "Mms"):
        return "sms"
    if mtype == "IMessage":
        return "imessage"
    return (app or "").strip().casefold() or "unknown"


# ---- statistics -------------------------------------------------------------------------------------------------

def mad_spread(values) -> float:
    med = statistics.median(values)
    return 1.4826 * statistics.median(abs(v - med) for v in values)


DRIFT_MAX_READINGS = 2000


def theil_sen(xs, ys):
    """(slope, low, high): Theil-Sen slope and Sen's 95 percent interval (19.S5-c). Above DRIFT_MAX_READINGS
    readings a fixed-seed sample of that many is used, so the pairwise slopes stay under two million."""
    if len(xs) > DRIFT_MAX_READINGS:
        import random
        keep = sorted(random.Random(0).sample(range(len(xs)), DRIFT_MAX_READINGS))
        xs, ys = [xs[i] for i in keep], [ys[i] for i in keep]
    n = len(xs)
    slopes = sorted((ys[j] - ys[i]) / (xs[j] - xs[i]) for i in range(n) for j in range(i + 1, n) if xs[j] != xs[i])
    if not slopes:
        return None
    m = len(slopes)
    slope = statistics.median(slopes)
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    c = 1.959964 * math.sqrt(var_s)
    lo_i, hi_i = int(max(0, math.floor((m - c) / 2.0) - 1)), int(min(m - 1, math.ceil((m + c) / 2.0)))
    return slope, slopes[lo_i], slopes[hi_i]


# ---- reading ------------------------------------------------------------------------------------------------------

def _people(conn, case_id) -> dict:
    return {r[0]: (("person:%s" % r[1]) if r[1] else r[0]) for r in conn.execute(text(
        "SELECT identity_key, person_id FROM pv_identity WHERE case_id = :c"), {"c": str(case_id)})}


def _owners(conn, ext, people) -> dict:
    """{group: reviewed (bool)} for the phone's owner identities (19.S5-a)."""
    o = identities.owner(conn, ext)
    keys = set(o.get("owner_identity_keys") or [])
    keys |= {c["identity_key"] for c in o.get("candidates", ()) if c["candidate_kind"] == "account" and
             c.get("identity_key")}
    return {people.get(k, k): people.get(k, k) != k for k in keys if k}


def load_phone(conn, ext, people) -> dict:
    """Messages of one phone with what the keys need; one record per duplicate group (19.S5-f)."""
    types = {uid: (v["values"].get("Type") or [None])[0] for uid, v in
             FV.field_values(conn, ext, ("InstantMessage",), ("Type",)).items()}
    md5s = defaultdict(set)
    for r in conn.execute(text(
            "SELECT a.record_uid::text, f.md5 FROM pv_attachment_link a JOIN pv_file f ON f.file_uid = a.file_uid "
            "WHERE a.extraction_id = :e AND f.md5 IS NOT NULL"), {"e": ext}):
        md5s[r[0]].add(r[1])
    parts = defaultdict(lambda: {"sender": None, "sender_owner": False, "recipients": set()})
    for r in conn.execute(text(
            "SELECT e.record_uid::text AS uid, p.identity_key, p.role, p.implied_role, p.is_phone_owner FROM "
            "pv_comm_event e JOIN pv_comm_party p ON p.event_uid = e.event_uid WHERE e.extraction_id = :e AND e.kind = "
            "'message'"), {"e": ext}).mappings():
        g = people.get(r["identity_key"], r["identity_key"]) if r["identity_key"] else None
        is_sender = r["role"] == "sender" or (r["role"] == "owner_implicit" and r["implied_role"] == "sender")
        if is_sender:
            parts[r["uid"]]["sender"] = g or parts[r["uid"]]["sender"]
            parts[r["uid"]]["sender_owner"] = parts[r["uid"]]["sender_owner"] or bool(r["is_phone_owner"])
        elif g:
            parts[r["uid"]]["recipients"].add(g)
    threads = {r[0]: {people.get(k, k) for k in (r[1] or ())} for r in conn.execute(text(
        "SELECT thread_key, party_identity_keys FROM pv_thread WHERE extraction_id = :e"), {"e": ext})}
    msgs, seen_dup = [], set()
    for r in conn.execute(text(
            "SELECT record_uid::text AS uid, app, body, sort_instant, deleted_state, direction, thread_key, "
            "dup_group_uid FROM pv_comm_event WHERE extraction_id = :e AND kind = 'message' AND sort_instant IS NOT "
            "NULL ORDER BY sort_instant, record_uid"), {"e": ext}).mappings():
        if r["dup_group_uid"]:
            if r["dup_group_uid"] in seen_dup:
                continue
            seen_dup.add(r["dup_group_uid"])
        body = norm_body(r["body"])
        att = md5s.get(r["uid"])
        if body:
            key = "b:" + body
        elif att:
            key = "m:" + ",".join(sorted(att))
        else:
            continue
        p = parts.get(r["uid"]) or {"sender": None, "sender_owner": False, "recipients": set()}
        msgs.append({"uid": r["uid"], "key": key, "short": bool(body) and len(body) < MIN_BODY,
                     "family": family(r["app"], types.get(r["uid"])), "t": r["sort_instant"],
                     "deleted": r["deleted_state"] in DELETED, "direction": r["direction"],
                     "sender": p["sender"], "sender_owner": p["sender_owner"],
                     "recipients": frozenset(p["recipients"] | threads.get(r["thread_key"], set()))})
    occ = Counter(m["key"] for m in msgs)
    fam_range = {}
    for m in msgs:
        lo, hi = fam_range.get(m["family"], (m["t"], m["t"]))
        fam_range[m["family"]] = (min(lo, m["t"]), max(hi, m["t"]))
    return {"msgs": msgs, "occ": occ, "family_range": fam_range}


def coverage(conn, case_id) -> dict:
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        n = int(conn.execute(text("SELECT count(*) FROM pv_comm_event WHERE extraction_id = :e AND kind = 'message' "
                                  "AND sort_instant IS NOT NULL"), {"e": ext}).scalar() or 0)
        owner = identities.owner(conn, ext)
        known = bool(owner.get("owner_identity_keys"))
        phones[ext] = {"label": label, "signals": {
            "messages": {"carries_signal": n > 0, "records": n},
            "owner": {"carries_signal": known, "records": 1 if known else 0}}}
    return {"phones": phones, "signals": SIGNALS}


# ---- matching -----------------------------------------------------------------------------------------------------

def _sent_by_owner(m, owners) -> bool:
    return m["sender"] in owners if m["sender"] else (m["sender_owner"] and m["direction"] == "outgoing")


def keys(mx, my, ox, oy) -> dict:
    """K2 and K3 for two copies already equal on K1 and K4."""
    x_sent, y_sent = _sent_by_owner(mx, ox), _sent_by_owner(my, oy)
    k2 = x_sent != y_sent
    k3 = False
    if k2 and x_sent:
        k3 = my["sender"] is not None and my["sender"] in ox and bool(set(oy) & mx["recipients"])
    elif k2 and y_sent:
        k3 = mx["sender"] is not None and mx["sender"] in oy and bool(set(ox) & my["recipients"])
    return {"k2": k2, "k3": k3, "x_sent": x_sent, "y_sent": y_sent}


def opposite(mx, my) -> bool:
    """A sent copy against a received one. Two copies in the same known direction are one phone's message seen
    twice (two extractions of one device), never a sender's and a recipient's copy."""
    known = ("outgoing", "incoming")
    return not (mx["direction"] in known and my["direction"] in known and mx["direction"] == my["direction"])


def between_owners(m, own, other) -> bool:
    """19.S5-e: the message's sender is one owner and the other owner is a recipient or participant."""
    if _sent_by_owner(m, own):
        return bool(set(other) & m["recipients"])
    return m["sender"] is not None and m["sender"] in other


def match_pair(px, py, ox, oy, params) -> dict:
    """Candidates, offsets and assignment for one phone pair (5.3.3 to 5.3.5)."""
    tau, window = float(params["tau_s"]), float(params["offset_window_h"]) * 3600.0
    by_key = defaultdict(list)
    for j, m in enumerate(py["msgs"]):   # messages are in time order, so each list is too
        by_key[(m["family"], m["key"])].append(j)
    times = {k: [py["msgs"][j]["t"].timestamp() for j in js] for k, js in by_key.items()}
    near = []   # (i, j, dt, tier or None, k3)
    for i, mx in enumerate(px["msgs"]):
        k_ = (mx["family"], mx["key"])
        js = by_key.get(k_)
        if not js:
            continue
        tx = mx["t"].timestamp()
        lo, hi = bisect.bisect_left(times[k_], tx - window), bisect.bisect_right(times[k_], tx + window)
        for j in js[lo:hi]:
            my = py["msgs"][j]
            dt = my["t"].timestamp() - tx
            k = keys(mx, my, ox, oy)
            distinctive = not mx["short"] and px["occ"][mx["key"]] <= MAX_OCCURRENCES and \
                py["occ"][my["key"]] <= MAX_OCCURRENCES
            if k["k2"] and k["k3"]:
                tier = "matched_strong"
            elif distinctive and (mx["sender"] is None or my["sender"] is None) and opposite(mx, my):
                tier = "matched_content_time"
            else:
                tier = None
            if tier or k["k3"]:
                near.append((i, j, dt, tier, k["k3"] and distinctive))
    # 5.3.5: offsets per family and timestamp class from candidates with K3 (offset candidates and matches)
    offsets = {}
    # one offset reading per message and per copy: the nearest distinctive candidate with K3
    nearest = {}
    for i, j, dt, tier, k3d in sorted(near, key=lambda c: (abs(c[2]), c[0], c[1])):
        if k3d and i not in nearest and j not in {v[0] for v in nearest.values()}:
            nearest[i] = (j, dt)
    by_family = defaultdict(list)
    for i, (j, dt) in sorted(nearest.items()):
        by_family[px["msgs"][i]["family"]].append((i, dt))
    for fam, items in by_family.items():
        dts = [dt for _, dt in items]
        n = len(dts)
        cls = "server_stamped" if sum(1 for d in dts if abs(d) < 1) >= 0.9 * n else "device_stamped"
        entry = {"family": fam, "class": cls, "n": n, "offset_s": 0.0, "spread_s": None, "tau_s": tau}
        if cls == "device_stamped" and n >= 5:
            entry["offset_s"] = statistics.median(dts)
            entry["spread_s"] = mad_spread(dts)
            q = statistics.quantiles(dts, n=4) if n >= 2 else [dts[0]] * 3
            entry["iqr_s"] = [q[0], q[2]]
            entry["tau_s"] = min(max(tau, 3 * entry["spread_s"]), float(PARAMETERS["tau_s"]["max"]))
            xs = [px["msgs"][i]["t"].timestamp() / 86400.0 for i, _ in items]
            if n >= 20 and max(xs) - min(xs) >= 30:
                ts = theil_sen(xs, dts)
                if ts:
                    entry["drift_s_per_day"] = {"slope": ts[0], "low": ts[1], "high": ts[2]}
        elif cls == "device_stamped":
            entry["too_few"] = True
        offsets[fam] = entry
    cands = []
    for i, j, dt, tier, _ in near:
        if not tier:
            continue
        o = offsets.get(px["msgs"][i]["family"], {"offset_s": 0.0, "tau_s": tau})
        score = abs(dt - o["offset_s"])
        if score <= o["tau_s"]:
            cands.append((score, i, j, tier, dt))
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    used_x, used_y, matched, ambiguous = set(), set(), [], []
    k = 0
    while k < len(cands):
        g = k
        while g < len(cands) and cands[g][0] == cands[k][0]:
            g += 1
        group = [c for c in cands[k:g] if c[1] not in used_x and c[2] not in used_y]
        xs, ys = Counter(c[1] for c in group), Counter(c[2] for c in group)
        for c in group:
            if c[1] in used_x or c[2] in used_y:
                continue
            if xs[c[1]] > 1 or ys[c[2]] > 1:
                ties, seen_x, seen_y, grew = [c], {c[1]}, {c[2]}, True
                while grew:   # the whole connected set of equal-score candidates
                    grew = False
                    for d in group:
                        if d not in ties and (d[1] in seen_x or d[2] in seen_y):
                            ties.append(d)
                            seen_x.add(d[1])
                            seen_y.add(d[2])
                            grew = True
                for d in ties:
                    used_x.add(d[1])
                    used_y.add(d[2])
                ambiguous.append(ties)
                continue
            used_x.add(c[1])
            used_y.add(c[2])
            matched.append(c)
        k = g
    return {"matched": matched, "ambiguous": ambiguous, "offsets": offsets, "used_x": used_x, "used_y": used_y}


DEVICE_ITEMS = ("IMEI", "Serial", "Factory number", "DeviceInfoAndroidID", "DeviceInfoSerial")


def device_ids(conn, ext) -> set:
    """The report header's device identifiers (name, normalised value)."""
    items = identities.header_items(conn, ext)
    return {(n, "".join(ch for ch in v if ch.isalnum()).casefold()) for n in DEVICE_ITEMS for v in items.get(n, ())
            if v and v.strip()}


def same_device(a, b) -> bool:
    return bool(a & b)


def candidate_pair(px, py, ox, oy) -> bool:
    """5.3.1: an owner of one is a party on the other (X1), or the two share a party identity (X2)."""
    def parties(p):
        return {m["sender"] for m in p["msgs"] if m["sender"]} | {g for m in p["msgs"] for g in m["recipients"]}
    ax, ay = parties(px), parties(py)
    return bool(set(ox) & ay or set(oy) & ax or (ax - set(ox)) & (ay - set(oy)))


# ---- results ------------------------------------------------------------------------------------------------------

def _rec(ext, uid, role, field_path=None):
    return {"extraction_id": ext, "record_uid": uid, "field_path": field_path, "role": role}


def _match_result(x, y, labels, px, py, ox, oy, c, offsets):
    score, i, j, tier, dt = c
    mx, my = px["msgs"][i], py["msgs"][j]
    o = offsets.get(mx["family"])
    sender = my["sender"] if mx["sender"] is None else mx["sender"]
    reviewed = bool(sender) and str(sender).startswith("person:")   # K3's equality went through a reviewed person
    supports = [_d("attachment_equal" if mx["key"].startswith("m:") else "content_equal",
                   "The same attachment on both phones." if mx["key"].startswith("m:") else
                   "The same text on both phones."),
                _d("time_agrees", "The two copies are %.0f seconds apart%s." % (
                    score if o and o.get("offset_s") else abs(dt),
                    " after the pair's clock offset" if o and o.get("offset_s") else ""))]
    undercuts = []
    if tier == "matched_strong":
        supports.append(_d("participants_agree", "Sender and recipient agree with the two phones' owners."))
        if reviewed:
            supports.append(_d("reviewed_merge", "The owners' identities are joined by a reviewed decision."))
        else:
            undercuts.append(_d("identity_unreviewed", "The owners are matched on equal numbers or accounts, not on "
                                "a reviewed decision."))
    else:
        undercuts.append(_d("identity_unreviewed", "One copy does not name its sender, so only text and time "
                            "agree."))
    if o and o["class"] == "server_stamped":
        undercuts.append(_d("server_stamped", "The service set these times; they say nothing about either phone's "
                            "clock."))
    elif o and o.get("too_few"):
        undercuts.append(_d("clock_offset_unknown", "Too few pairs to estimate the clock offset."))
    undercuts.append(_d("multi_device_account", "A message sent from a linked computer or tablet shows on the phone "
                        "as sent from it."))
    deleted_one = mx["deleted"] != my["deleted"]
    measures = {"phones": [labels[x], labels[y]], "tier": tier, "family": mx["family"], "seconds_apart": dt,
                "seconds_after_offset": score,
                "offset_s": o["offset_s"] if o else 0.0, "timestamp_class": o["class"] if o else None,
                "deleted": [mx["deleted"], my["deleted"]]}
    records = [_rec(x, mx["uid"], "copy"), _rec(y, my["uid"], "copy")]
    if deleted_one:
        intact_ext = y if mx["deleted"] else x
        measures["recovered_from"] = labels[intact_ext]
        records = [_rec(x, mx["uid"], "recovered_copy" if intact_ext == x else "deleted_copy"),
                   _rec(y, my["uid"], "recovered_copy" if intact_ext == y else "deleted_copy")]
    t0, t1 = sorted((mx["t"], my["t"]))
    return {"kind": "deleted_one_side" if deleted_one else "both_sides", "strength": tier, "measures": measures,
            "directions": {"supports": supports, "undercuts": undercuts}, "period_start": t0, "period_end": t1,
            "records": records}


def _absent_reasons(m, py, start_y):
    reasons = []
    if start_y is not None and m["t"] > start_y:
        reasons.append(_d("counterpart_extraction_ended", "The other phone was extracted before this message."))
    rng = py["family_range"].get(m["family"])
    if rng is None or m["t"] < rng[0] or m["t"] > rng[1]:
        reasons.append(_d("counterpart_app_no_data", "The other phone holds no message of this app around this "
                          "time."))
    if m["key"].startswith("m:"):
        reasons.append(_d("media_recompressed", "Apps can recompress media, so the other copy's file may differ."))
    return reasons


def analyse(conn, case_id, params, ctx=None) -> tuple:
    params = {k: (params or {}).get(k, v["default"]) for k, v in PARAMETERS.items()}
    labels = FV.active_phones(conn, case_id)
    people = _people(conn, case_id)
    exts = sorted(labels, key=lambda e: (labels[e], e))
    data, owners, starts, devices = {}, {}, {}, {}
    counts = Counter()
    out = []
    for n, ext in enumerate(exts):
        if ctx is not None:
            ctx.progress(n, len(exts) * 2, labels[ext])
            if ctx.cancelled():
                return out, dict(counts)
        data[ext] = load_phone(conn, ext, people)
        owners[ext] = _owners(conn, ext, people)
        from services.pattern_of_life.availability import extraction_start
        starts[ext] = extraction_start(conn, ext)
        devices[ext] = device_ids(conn, ext)
    pairs = list(combinations(exts, 2))
    for n, (x, y) in enumerate(pairs):
        if ctx is not None:
            ctx.progress(len(exts) + n * len(exts) // max(1, len(pairs)), len(exts) * 2)
            if ctx.cancelled():
                break
        px, py, ox, oy = data[x], data[y], owners[x], owners[y]
        counts["phone_pairs"] += 1
        if same_device(devices[x], devices[y]):
            counts["pairs_one_device"] += 1   # 5.3.1: two extractions of one device are approach 12's
            continue
        if not candidate_pair(px, py, ox, oy):
            counts["pairs_no_shared_participants"] += 1
            continue
        counts["candidate_pairs"] += 1
        res = match_pair(px, py, ox, oy, params)
        for c in res["matched"]:
            r = _match_result(x, y, labels, px, py, ox, oy, c, res["offsets"])
            counts[r["kind"]] += 1
            if r["kind"] == "deleted_one_side" and c[3] == "matched_strong":
                counts["deleted_one_side_strong"] += 1
            counts[c[3]] += 1
            out.append(r)
        for ties in res["ambiguous"]:
            counts["ambiguous_pair"] += 1
            recs = []
            for _, i, j, _, _ in ties:
                for ext, p, idx in ((x, px, i), (y, py, j)):
                    rec = _rec(ext, p["msgs"][idx]["uid"], "candidate", "ambiguous")
                    if rec not in recs:
                        recs.append(rec)
            times = sorted(p["msgs"][idx]["t"] for _, i, j, _, _ in ties for p, idx in ((px, i), (py, j)))
            out.append({"kind": "ambiguous_pair", "strength": ties[0][3],
                        "measures": {"phones": [labels[x], labels[y]], "candidates": len(ties)},
                        "directions": {"supports": [_d("content_equal", "The same text on both phones.")],
                                       "undercuts": [_d("identity_unreviewed", "Two copies are equally close; "
                                                        "neither is chosen.")]},
                        "period_start": times[0], "period_end": times[-1], "records": recs})
        for fam, o in sorted(res["offsets"].items()):
            anchor = next((c for c in res["matched"] if px["msgs"][c[1]]["family"] == fam), None)
            if anchor is None:
                continue
            counts["clock_offsets"] += 1
            words = ("The service set these times; they say nothing about either phone's clock."
                     if o["class"] == "server_stamped" else
                     "Too few pairs to estimate the clock offset." if o.get("too_few") else
                     "%s's clock reads %.0f seconds %s %s's (spread %.0f s, %d pairs)." % (
                         labels[y], abs(o["offset_s"]), "ahead of" if o["offset_s"] >= 0 else "behind", labels[x],
                         o["spread_s"] or 0, o["n"]))
            out.append({"kind": "clock_offset", "strength": o["class"],
                        "measures": dict(o, phones=[labels[x], labels[y]], words=words),
                        "directions": {"supports": [_d("time_agrees", "%d matched or candidate pairs." % o["n"])],
                                       "undercuts": ([_d("server_stamped", words)] if o["class"] == "server_stamped"
                                                     else [_d("clock_offset_unknown", words)] if o.get("too_few")
                                                     else [])},
                        "period_start": None, "period_end": None,
                        "records": [_rec(x, px["msgs"][anchor[1]]["uid"], "anchor", "offset:%s:%s" % (fam, y)),
                                    _rec(y, py["msgs"][anchor[2]]["uid"], "anchor", "offset:%s:%s" % (fam, x))]})
        for side, (a, b, pa, pb, oa, ob, used) in enumerate(((x, y, px, py, ox, oy, res["used_x"]),
                                                              (y, x, py, px, oy, ox, res["used_y"]))):
            if not ob:
                continue
            for idx, m in enumerate(pa["msgs"]):
                if idx in used or not between_owners(m, oa, ob):
                    continue
                reasons = _absent_reasons(m, pb, starts[b])
                counts["one_side_only"] += 1
                out.append({"kind": "one_side_only", "strength": "explained" if reasons else "unexplained",
                            "measures": {"phones": [labels[a], labels[b]], "on": labels[a], "not_on": labels[b],
                                         "family": m["family"], "deleted": m["deleted"]},
                            "directions": {"supports": [], "undercuts": reasons},
                            "period_start": m["t"], "period_end": m["t"],
                            "records": [_rec(a, m["uid"], "message", "absent_on:%s" % b)]})
    if ctx is not None:
        ctx.progress(len(exts) * 2, len(exts) * 2)
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]

