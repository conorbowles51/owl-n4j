"""05 section 11.6 perceptual-tier gate, pass 2: pair media messages across phones without using content, then
compare attachment MD5s. Counts only.

usage: python3 -I p8_cross.py <corpus.json> <data_dir> <out.json>

Pairing (05 5.3.2 K1, K2, K3, K5 with tau = 120 s and offset 0; K4 content deliberately NOT used, since MD5 is
what is being measured): same family; sender copy outgoing and receiver copy incoming (direction as A3);
one of the sender copy's recipients is an owner identifier of the receiving phone, and the receiver copy's
sender is an owner identifier of the sending phone (owner identifiers and normalisation as a3_extract);
|dt| <= 120 s. Assignment as 05 5.3.4: greedy by |dt|, ties at equal |dt| left unassigned.
"""
import collections
import itertools
import json
import os
import pickle
import re
import sys

TAU = 120.0
GUARD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$")


def load(d, label):
    with open(os.path.join(d, label + ".p8.pkl"), "rb") as fh:
        return pickle.load(fh)


def md5set(m):
    return frozenset(a[1] for a in m["att"] if a[0] == "md5")


def pool(msgs, strict):
    out = []
    for m in msgs:
        if m["t"] is None or not m["att"]:
            continue
        if strict and not md5set(m):
            continue
        out.append(m)
    return out


def candidates(S, R, strict, k3="both"):
    """Edges (|dt|, i, j) from S outgoing to R incoming."""
    so, ro = S["owner_keys"], R["owner_keys"]
    if k3 == "caption":
        def ok(m, P, Q):
            return m["body"] and m["blen"] >= 10 and P["body_occ"][m["body"]] <= 3 and Q["body_occ"][m["body"]] <= 3
        snd = [m for m in pool(S["msgs"], strict) if m["dir"] == "outgoing" and ok(m, S, R)]
        rcv = [m for m in pool(R["msgs"], strict) if m["dir"] == "incoming" and ok(m, R, S)]
    else:
        snd = [m for m in pool(S["msgs"], strict) if m["dir"] == "outgoing" and (k3 == "receiver" or (m["to"] & ro) or (k3 == "group" and (m["chat_parts"] & ro)))]
        rcv = [m for m in pool(R["msgs"], strict) if m["dir"] == "incoming" and (k3 == "sender" or m["from"] in so)]
    key = (lambda m: (m["fam"], m["body"])) if k3 == "caption" else (lambda m: m["fam"])
    byfam = collections.defaultdict(list)
    for j, m in enumerate(rcv):
        byfam[key(m)].append((m["t"], j))
    for v in byfam.values():
        v.sort()
    import bisect
    edges = []
    for i, m in enumerate(snd):
        v = byfam.get(key(m))
        if not v:
            continue
        k = bisect.bisect_left(v, (m["t"] - TAU, -1))
        while k < len(v) and v[k][0] <= m["t"] + TAU:
            edges.append((round(abs(v[k][0] - m["t"]), 3), i, v[k][1]))
            k += 1
    return snd, rcv, edges


def assign(edges):
    edges.sort()
    used_i, used_j, amb_i, amb_j = set(), set(), set(), set()
    pairs = []
    ambiguous = 0
    for score, grp in itertools.groupby(edges, key=lambda e: e[0]):
        live = [e for e in grp if e[1] not in used_i and e[2] not in used_j and e[1] not in amb_i and e[2] not in amb_j]
        di = collections.Counter(e[1] for e in live)
        dj = collections.Counter(e[2] for e in live)
        for e in live:
            if di[e[1]] > 1 or dj[e[2]] > 1:
                amb_i.add(e[1])
                amb_j.add(e[2])
        for e in live:
            if e[1] in amb_i or e[2] in amb_j:
                continue
            used_i.add(e[1])
            used_j.add(e[2])
            pairs.append(e)
    ambiguous = len(amb_i - used_i)
    return pairs, ambiguous


def compare(a, b):
    ma, mb = md5set(a), md5set(b)
    if not ma or not mb:
        side = a if not ma else b
        kinds = {x[0] for x in side["att"]}
        return "one side no MD5 (file present, no MD5)" if "no_md5" in kinds else "one side no file"
    if ma == mb:
        return "equal"
    if ma & mb:
        return "partial overlap (multi-attachment)"
    return "different"


def category(a, b):
    for m in (a, b):
        for x in m["att"]:
            if x[0] == "md5" and x[2]:
                return x[2]
    for m in (a, b):
        for x in m["att"]:
            if x[2]:
                return x[2]
    return "<none>"


def tally(rows):
    c = collections.Counter(r["cmp"] for r in rows)
    both = c["equal"] + c["different"] + c["partial overlap (multi-attachment)"]
    return {"pairs": len(rows), **dict(sorted(c.items())), "both sides with MD5": both,
            "share different among both-MD5 (partial counted as not different)": round(c["different"] / both, 4) if both else None,
            "share not exactly equal among both-MD5": round((both - c["equal"]) / both, 4) if both else None}


def run(corpus, d, strict, k3="both"):
    cases = collections.defaultdict(list)
    for label, spec in sorted(corpus.items()):
        if os.path.exists(os.path.join(d, label + ".p8.pkl")):
            cases[spec["case"]].append(label)
    out = {}
    allrows = []
    for case, labels in sorted(cases.items()):
        data = {l: load(d, l) for l in labels}
        cres = {"pairs_of_phones": {}}
        crows = []
        for la, lb in itertools.combinations(labels, 2):
            rows = []
            info = {}
            for s, r in ((la, lb), (lb, la)):
                snd, rcv, edges = candidates(data[s], data[r], strict, k3)
                pairs, amb = assign(edges)
                info["%s->%s" % (corpus[s]["spec05"], corpus[r]["spec05"])] = {
                    "sender-side pool messages passing K2/K3": len(snd), "receiver-side pool messages passing K2/K3": len(rcv),
                    "candidate edges": len(edges), "assigned": len(pairs), "left ambiguous (tie)": amb}
                # MD5s on the receiving phone's attachments, to test whether a 'different' pair is a mispairing
                r_md5 = collections.defaultdict(list)
                for m in data[r]["msgs"]:
                    for x in md5set(m):
                        r_md5[x].append(m["t"])
                for score, i, j in pairs:
                    a, b = snd[i], rcv[j]
                    if not md5set(a) and not md5set(b):
                        continue  # neither side has an MD5: not a media message under the task definition
                    cmpv = compare(a, b)
                    fam = a["fam"]
                    row = {"cmp": cmpv, "fam": fam, "cat": category(a, b), "dt0": score == 0.0,
                           "src": corpus[s]["spec05"], "dst": corpus[r]["spec05"],
                           "k3_full": bool(a["to"] & data[r]["owner_keys"]) and b["from"] in data[s]["owner_keys"],
                           "k3_receiver": b["from"] in data[s]["owner_keys"]}
                    if cmpv == "different":
                        row["sender_md5_elsewhere_on_receiver"] = any(x in r_md5 for x in md5set(a))
                    rows.append(row)
            cres["pairs_of_phones"]["%s & %s" % (corpus[la]["spec05"], corpus[lb]["spec05"])] = {
                "matching": info, "result": tally(rows)} if rows or any(v["candidate edges"] for v in info.values()) else "no candidate edges"
            crows += rows
        cres["total"] = tally(crows)
        fams = collections.Counter(r["fam"] for r in crows)
        cres["by_family"] = {(f if GUARD_RE.match(f.replace("app:", "")) and n >= 3 else "<other>"): tally([r for r in crows if r["fam"] == f])
                             for f, n in fams.items()}
        cres["by_file_category"] = {c: tally([r for r in crows if r["cat"] == c]) for c in sorted({r["cat"] for r in crows})}
        cres["by_time_class"] = {"dt exactly 0": tally([r for r in crows if r["dt0"]]),
                                 "dt non-zero": tally([r for r in crows if not r["dt0"]])}
        cres["K3 full holds"] = tally([r for r in crows if r["k3_full"]])
        cres["K3 receiver side holds"] = tally([r for r in crows if r["k3_receiver"]])
        diff = [r for r in crows if r["cmp"] == "different"]
        cres["different: sender MD5 found on another receiver-phone message (possible mispairing)"] = sum(
            1 for r in diff if r["sender_md5_elsewhere_on_receiver"])
        out[case] = cres
        allrows += crows
    out["all cases"] = tally(allrows)
    out["all cases by family"] = {(f if GUARD_RE.match(f.replace("app:", "")) else "<other>"): tally([r for r in allrows if r["fam"] == f]) for f in sorted({r["fam"] for r in allrows})}
    out["all cases by file category"] = {c: tally([r for r in allrows if r["cat"] == c]) for c in sorted({r["cat"] for r in allrows})}
    out["all cases K3 receiver side holds"] = tally([r for r in allrows if r["k3_receiver"]])
    out["all cases by time class"] = {"dt exactly 0": tally([r for r in allrows if r["dt0"]]), "dt non-zero": tally([r for r in allrows if not r["dt0"]])}
    out["all cases different with sender MD5 on another receiver message"] = sum(1 for r in allrows if r.get("sender_md5_elsewhere_on_receiver"))
    return out


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    res = {"what": "05 11.6 perceptual-tier gate; counts only", "tau_s": TAU,
           "main: pool = messages with >=1 non-URL attachment, pair kept if >=1 side has an MD5": run(corpus, argv[1], False),
           "strict: pool = media messages (>=1 attachment resolving to a tagged file with MD5) on both sides": run(corpus, argv[1], True),
           "05 K3 incl. group: sender copy's recipients OR its chat's participants include an owner identifier of the receiving phone, and the receiver copy's sender is an owner identifier of the sending phone": run(corpus, argv[1], False, "group"),
           "05 K3 incl. group, strict pool": run(corpus, argv[1], True, "group"),
           "K3 receiver-only: receiver copy's sender is an owner identifier of the sending phone; sender copy outgoing, recipients not checked": run(corpus, argv[1], False, "receiver"),
           "caption: K1 + K2 + K4 by distinct caption (normalised body >= 10 chars, <= 3 occurrences on each phone) + K5, K3 not required (05 matched_content_time)": run(corpus, argv[1], False, "caption"),
           "caption strict": run(corpus, argv[1], True, "caption"),
           "K3 sender-only: sender copy's recipients include an owner identifier of the receiving phone; receiver copy incoming, sender not checked": run(corpus, argv[1], False, "sender")}
    with open(argv[2], "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(json.dumps(res, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
