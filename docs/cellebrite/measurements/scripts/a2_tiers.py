"""Approach 2 gate (05 section 5.6, M-2b and M-2d by tier): cross-phone message matches with the keys of 05 5.3.2.

usage:
  python3 -I a2_tiers.py extract <corpus.json> <private_dir> <label>[,<label>...]
  python3 -I a2_tiers.py cross <corpus.json> <private_dir> <out.json> <case name>

extract streams one report and writes <private_dir>/<label>.a2.pkl (mode 0600): per message salted hashes of the
normalised body, sender and recipients, the chat's participants, the phone's owner identities, the time, the
deleted state and the platform family. No value leaves in clear. cross reads those files for every pair of reports
in one case and writes counts only.

Keys (05 5.3.2): K1 equal platform family; K2 complementary direction against each phone's owner identities; K3 the
sender on Y is X's owner and Y's owner is among m's recipients or chat participants (or the reverse); K4 equal
normalised body (NFKC, casefold, zero-width removed, whitespace collapsed); K5 abs(t_Y - t_X) <= 120 s. The clock
offset of 5.3.5 is not applied (offset 0): device-stamped pairs further apart than 120 s are not counted, so the
counts are a lower bound. Never keys: InstantMessage.Identifier, Chat.Id.

Tiers (5.3.3): matched_strong K1-K5; matched_content_time K1 K4 K5 with one side's sender identity missing (and the
body distinctive: at least 10 characters and at most 3 occurrences on each phone). Assignment (5.3.4): greedy by
abs(dt), one to one per phone pair and family; equal-score ties are left out and counted as ambiguous.
Owner identities: header MSISDN values and every party the report flags IsPhoneOwner (02's tier 1 and owner
parties), compared by a3_extract.id_key (digits, last 10, for phone-like values).
"""
import collections
import itertools
import json
import os
import pickle
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a3_extract import Salt, conv, fv, id_key, is_true, ln, parties, ts, walk  # noqa: E402

TAU = 120.0
ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
DELETED = ("Deleted", "Trash")


def norm_body(text):
    s = unicodedata.normalize("NFKC", text or "").casefold()
    s = ZERO_WIDTH.sub("", s)
    return " ".join(s.split())


def family(r):
    mtype = (fv(r, "Type") or "").strip()
    if mtype in ("Sms", "Mms"):
        return "sms"
    src = (fv(r, "Source") or fv(r, "SourceApplication") or "").strip().casefold()
    return src or (mtype.casefold() or "unknown")


def extract(spec, salt, out_path):
    xml = os.path.join(spec["root"], spec["report"])
    owners, msgs = set(), []
    stack, els = [], []
    t_start = time.monotonic()

    def k(identifier):
        key = id_key(identifier)
        return salt.h("id", key) if key else None

    with open(xml, "rb") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = ln(el.tag)
            if ev == "start":
                stack.append(tag)
                els.append(el)
                continue
            stack.pop()
            els.pop()
            parent = stack[-1] if stack else None
            if tag == "model" and parent == "modelType":
                for r, p, _f in walk(conv(el)):
                    if r["t"] == "Party" and is_true(fv(r, "IsPhoneOwner")):
                        h = k(fv(r, "Identifier"))
                        if h:
                            owners.add(h)
                    if r["t"] != "InstantMessage":
                        continue
                    t0, _ = ts(fv(r, "TimeStamp"))
                    body = norm_body(fv(r, "Body"))
                    if t0 is None or not body:
                        continue
                    frm = parties(r, "From")
                    sender = k(fv(frm[0], "Identifier")) if frm else None
                    sender_owner = is_true(fv(frm[0], "IsPhoneOwner")) if frm else False
                    recips = frozenset(x for x in (k(fv(q, "Identifier")) for q in parties(r, "To")) if x)
                    chat = frozenset()
                    if p is not None and p["t"] == "Chat":
                        chat = frozenset(x for x in (k(fv(q, "Identifier")) for q in parties(p, "Participants")) if x)
                    msgs.append((salt.h("body", body), len(body), t0, family(r), sender, sender_owner, recips, chat,
                                 r["del"] or ""))
                el.clear()
                els[-1].remove(el)
            elif tag == "item" and parent == "metadata" and "taggedFiles" not in stack and "decodedData" not in stack:
                if el.get("name") == "MSISDN" and (el.text or "").strip():
                    h = k(el.text)
                    if h:
                        owners.add(h)
            elif tag in ("modelType", "taggedFiles", "decodedData", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
            elif parent in ("extraInfos", "carvedFiles", "infectedFiles", "taggedFiles"):
                el.clear()
                els[-1].remove(el)
    fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        pickle.dump({"owners": owners, "msgs": msgs}, fh, protocol=4)
    import resource
    return {"messages": len(msgs), "owner_identities": len(owners), "seconds": round(time.monotonic() - t_start, 1),
            "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}


def tier(mx, my, ox, oy, occ_x, occ_y):
    """(tier or None) for two messages already equal on K1, K4 and K5."""
    _, blen, _, _, sx, sx_owner, rx, cx, _ = mx
    _, _, _, _, sy, sy_owner, ry, cy, _ = my
    x_sent = sx_owner or (sx is not None and sx in ox)
    y_sent = sy_owner or (sy is not None and sy in oy)
    k2 = x_sent != y_sent
    k3 = False
    if k2 and x_sent:   # X's owner sent; on Y the sender is X's owner and Y's owner is a recipient or participant
        k3 = sy is not None and sy in ox and bool(oy & (rx | cx))
    elif k2 and y_sent:
        k3 = sx is not None and sx in oy and bool(ox & (ry | cy))
    if k2 and k3:
        return "matched_strong"
    distinctive = blen >= 10 and occ_x <= 3 and occ_y <= 3
    if distinctive and (sx is None or sy is None):
        return "matched_content_time"
    return None


def cross_pair(fx, fy):
    ox, oy = fx["owners"], fy["owners"]
    occ_x = collections.Counter(m[0] for m in fx["msgs"])
    occ_y = collections.Counter(m[0] for m in fy["msgs"])
    by_key = collections.defaultdict(list)
    for j, m in enumerate(fy["msgs"]):
        by_key[(m[0], m[3])].append(j)
    cands = []
    for i, m in enumerate(fx["msgs"]):
        for j in by_key.get((m[0], m[3]), ()):
            d = abs(fy["msgs"][j][2] - m[2])
            if d <= TAU:
                t = tier(m, fy["msgs"][j], ox, oy, occ_x[m[0]], occ_y[m[0]])
                if t:
                    cands.append((d, i, j, t))
    cands.sort()
    used_x, used_y, out = set(), set(), collections.Counter()
    deltas = collections.defaultdict(list)
    for _d, group in itertools.groupby(cands, key=lambda c: c[0]):
        group = [c for c in group if c[1] not in used_x and c[2] not in used_y]
        xs = collections.Counter(c[1] for c in group)
        ys = collections.Counter(c[2] for c in group)
        for d, i, j, t in group:
            if i in used_x or j in used_y:
                continue
            used_x.add(i)
            used_y.add(j)
            if xs[i] > 1 or ys[j] > 1:   # equal score, two candidates: left unassigned (5.3.4)
                out["ambiguous_pair"] += 1
                continue
            out[t] += 1
            if (fx["msgs"][i][8] in DELETED) != (fy["msgs"][j][8] in DELETED):
                out["deleted_one_side:" + t] += 1   # also recovered_from_other_side: one copy deleted, one intact
            deltas[(fx["msgs"][i][3], t)].append(d)
    partitions = {}
    for (fam, t), ds in deltas.items():
        n = len(ds)
        partitions.setdefault(t, collections.Counter())["server_stamped" if sum(1 for x in ds if x < 1) >= 0.9 * n
                                                         else "device_stamped"] += n
    return dict(out), {t: dict(c) for t, c in partitions.items()}


def candidate(fx, fy):
    """5.3.1: an owner of one appears as a party on the other, or the two share a party identity."""
    px = {m[4] for m in fx["msgs"] if m[4]} | {x for m in fx["msgs"] for x in m[6] | m[7]}
    py = {m[4] for m in fy["msgs"] if m[4]} | {x for m in fy["msgs"] for x in m[6] | m[7]}
    return bool(fx["owners"] & py or fy["owners"] & px or (px - fx["owners"]) & (py - fy["owners"]))


def main(argv):
    mode, corpus = argv[0], json.load(open(argv[1], encoding="utf-8"))
    priv = argv[2]
    os.makedirs(priv, mode=0o700, exist_ok=True)
    if mode == "extract":
        salt = Salt(os.path.join(priv, "salt.bin"))
        for label in argv[3].split(","):
            info = extract(corpus[label], salt, os.path.join(priv, label + ".a2.pkl"))
            print(json.dumps(dict(info, label=label)), flush=True)
        return 0
    out_path, case = argv[3], argv[4]
    labels = sorted(lbl for lbl, s in corpus.items() if s.get("case") == case)
    facts = {lbl: pickle.load(open(os.path.join(priv, lbl + ".a2.pkl"), "rb")) for lbl in labels}
    pairs, totals = [], collections.Counter()
    for x, y in itertools.combinations(labels, 2):
        if not candidate(facts[x], facts[y]):
            pairs.append({"pair": [x, y], "candidate": False})
            continue
        counts, parts = cross_pair(facts[x], facts[y])
        totals.update(counts)
        pairs.append({"pair": [x, y], "candidate": True, "counts": counts, "timestamp_class": parts})
    out = {"what": "05 M-2b/M-2d by tier (a2_tiers.py); counts only; offset 0, tau 120 s (lower bound)",
           "case": case, "reports": labels, "phone_pairs": len(pairs),
           "candidate_pairs": sum(1 for p in pairs if p["candidate"]), "totals": dict(totals), "pairs": pairs}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(json.dumps({"totals": dict(totals), "candidate_pairs": out["candidate_pairs"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
