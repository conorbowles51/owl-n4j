"""Approaches 14 to 16 gates (05 sections 16a.6, 16b.6, 16c.6: M-14a/b, M-15a/b, M-16a/b/c) on one corpus case.

usage:
  python3 -I m14_16.py <private_dir> <a2 cross result.json> <out.json> <label>[,<label>...]

Reads the per-report files ``a2_tiers.py extract`` wrote (salted identity hashes, times, owner identities; mode
0600) and writes counts only. Messages only: the extract holds no calls or emails, so every count is a lower bound.
Identities are joined by equal normalised identifier (a3_extract.id_key), never by a reviewed decision, so M-14b (the
share resting on an unreviewed join) is 1.0 by construction here.

Owners: the phone's owner identities (header MSISDN, IsPhoneOwner parties). Phones whose owner identities overlap
are one owner (two extractions of one phone, or one person's two phones under one number).

Edges: a message's sender and each of its recipients (chat participants when it lists none); a message sent by the
owner with no sender identifier is attributed to the phone's owner.
"""
import collections
import itertools
import json
import os
import pickle
import random
import sys
from datetime import datetime, timezone

GAP_S = 14 * 86400
WINDOW_S = 90 * 86400
THRESHOLD = 0.5
MIN_SHARED = 5
SHUFFLES = 20


def epoch(t):
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, datetime):
        return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp()
    return None


def main(private_dir, cross_json, out_json, labels):
    phones = {}
    for label in labels:
        with open(os.path.join(private_dir, label + ".a2.pkl"), "rb") as fh:
            phones[label] = pickle.load(fh)
    # owners: union phones whose owner identities overlap
    parent = {lab: lab for lab in labels}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in itertools.combinations(labels, 2):
        if phones[a]["owners"] & phones[b]["owners"]:
            parent[find(a)] = find(b)
    owner_of_hash = {}
    for lab in labels:
        for h in phones[lab]["owners"]:
            owner_of_hash[h] = ("O", find(lab))

    def node(h):
        return owner_of_hash.get(h, h)

    edges = []          # (t, a, b, phone)
    counterparts = collections.defaultdict(lambda: collections.defaultdict(int))  # owner -> identity -> count
    for lab in labels:
        own = ("O", find(lab))
        ox = phones[lab]["owners"]
        for (_b, _l, t0, _f, sender, sender_owner, recips, chat, _d) in phones[lab]["msgs"]:
            t = epoch(t0)
            if t is None:
                continue
            a = own if (sender_owner or (sender is not None and sender in ox)) else (node(sender) if sender else None)
            if a is None:
                continue
            to = {node(x) for x in (recips or chat)} - {a}
            if a != own and not to:
                to = {own}
            for b in to:
                edges.append((t, a, b, lab))
            for x in ({a} | to) - {own}:
                if isinstance(x, tuple):
                    continue
                counterparts[own][x] += 1
    owners = sorted({("O", find(lab)) for lab in labels})
    # M-14a: per pair of owners, identities with at least one communication with each
    m14 = {}
    for x, y in itertools.combinations(owners, 2):
        common = set(counterparts[x]) & set(counterparts[y])
        m14["%s|%s" % (x[1], y[1])] = len(common)
    # M-15a: population at N = 1 and N = 5
    per_identity = collections.Counter()
    for _t, a, b, _p in edges:
        per_identity[a] += 1
        per_identity[b] += 1
    non_owner = {k: v for k, v in per_identity.items() if not isinstance(k, tuple)}
    owner_pairs = collections.Counter()
    for _t, a, b, _p in edges:
        if isinstance(a, tuple) and isinstance(b, tuple) and a != b:
            owner_pairs[tuple(sorted((a, b)))] += 1
    owners_in_contact = sorted({o for pair in owner_pairs for o in pair})
    with open(cross_json) as fh:
        cross = json.load(fh)
    # M-16: identity first/last times and counterpart sets
    first, last = {}, {}
    nbr = collections.defaultdict(list)    # identity -> [(t, counterpart)]
    for t, a, b, _p in edges:
        for x, y in ((a, b), (b, a)):
            if isinstance(x, tuple):
                continue
            first[x] = min(first.get(x, t), t)
            last[x] = max(last.get(x, t), t)
            nbr[x].append((t, y))
    end = max(t for t, *_ in edges) if edges else 0
    stopped = [x for x in last if last[x] < end - GAP_S]

    import bisect
    times = {}
    for x in nbr:
        nbr[x].sort(key=lambda e: e[0])
        times[x] = [t for t, _ in nbr[x]]

    def window_set(x, a, b):
        lo, hi = bisect.bisect_left(times[x], a), bisect.bisect_right(times[x], b)
        return {y for _, y in nbr[x][lo:hi]}
    before = {x: window_set(x, last[x] - WINDOW_S, last[x]) for x in stopped}

    def pairs(starts):
        """(Jaccard, shared) for every stopped X and every Y whose start falls within the gap after X's last."""
        after = {y: window_set(y, s, s + WINDOW_S) for y, s in starts.items()}
        by_start = sorted((s, y) for y, s in starts.items())
        keys = [s for s, _ in by_start]
        out = []
        for x in stopped:
            bx = before[x]
            if not bx:
                continue
            i = bisect.bisect_right(keys, last[x])
            j = bisect.bisect_right(keys, last[x] + GAP_S)
            for _s, y in by_start[i:j]:
                if y == x:
                    continue
                ay = after[y]
                inter = len(bx & ay)
                union = len(bx | ay)
                out.append((inter / union if union else 0.0, inter))
        return out
    observed = pairs(first)
    above = sum(1 for j, n in observed if j >= THRESHOLD and n >= MIN_SHARED)
    rng = random.Random(1603)
    ids_ = list(first)
    base = []
    for _ in range(SHUFFLES):
        vals = [first[i] for i in ids_]
        rng.shuffle(vals)
        shuffled = pairs(dict(zip(ids_, vals)))
        base.append((len(shuffled), sum(1 for j, n in shuffled if j >= THRESHOLD and n >= MIN_SHARED)))

    def hist(ps):
        bins = collections.Counter(min(9, int(j * 10)) for j, _ in ps)
        return {"%.1f" % (b / 10): bins[b] for b in range(10)}
    result = {
        "phones": len(labels), "owners": len(owners), "messages": sum(len(p["msgs"]) for p in phones.values()),
        "edges": len(edges),
        "m14a_common_contacts_per_owner_pair": dict(sorted(m14.items(), key=lambda kv: -kv[1])),
        "m14a_pairs_with_3_or_more": sum(1 for v in m14.values() if v >= 3),
        "m14b_share_unreviewed": 1.0,
        "m15a_population": {"N1": sum(1 for v in non_owner.values() if v >= 1) + len(owners),
                            "N5": sum(1 for v in non_owner.values() if v >= 5) + len(owners)},
        "m15a_owner_pairs_in_contact": len(owner_pairs), "m15a_owners_in_contact": len(owners_in_contact),
        "m15b_matched_strong": cross.get("totals", {}).get("matched_strong"),
        "m15b_owner_to_owner_message_copies": sum(owner_pairs.values()),
        "m16a_stopped_identities": len(stopped), "m16b_candidate_pairs": len(observed),
        "m16b_above_threshold": above, "m16b_jaccard_hist": hist(observed),
        "m16c_shuffles": SHUFFLES, "m16c_candidate_pairs_mean": round(sum(b[0] for b in base) / SHUFFLES, 1),
        "m16c_above_threshold_mean": round(sum(b[1] for b in base) / SHUFFLES, 2),
        "m16c_above_threshold_max": max(b[1] for b in base) if base else 0,
        "parameters": {"gap_days": GAP_S // 86400, "window_days": WINDOW_S // 86400, "threshold": THRESHOLD,
                       "min_shared": MIN_SHARED},
    }
    result["m14a_common_contacts_per_owner_pair"] = {
        "pairs": len(m14), "max": max(m14.values()) if m14 else 0,
        "distribution": dict(collections.Counter(min(v, 20) for v in m14.values()))}
    with open(out_json, "w") as fh:
        json.dump(result, fh, indent=1, sort_keys=True)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(","))
