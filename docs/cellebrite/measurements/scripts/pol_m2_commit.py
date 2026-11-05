"""M2's committed file from its private output (04 section 13 guards).

usage: python3 -I pol_m2_commit.py <corpus.json> <m2-private.json> <m2-enums.json>

A mail folder can be named by its owner, so a folder value stays only when it is a mail system's own name or is on
reports of at least two different cases; any other becomes `<other>`, and `email_foldertoken_x_status_x_from` still
says what kind of folder it was. InstantMessage folders are the same check. A value the final guard (a3_guard_check)
would flag, such as a Precision that holds a number, becomes `<other>` too, on every measure.
"""
import collections
import importlib.util
import json
import os
import sys

_spec = importlib.util.spec_from_file_location("a3_guard_check", os.path.join(os.path.dirname(os.path.abspath(__file__)), "a3_guard_check.py"))
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)
SYSTEM_FOLDERS = {"Inbox", "INBOX", "Sent", "Sent Messages", "Draft", "Drafts", "Outbox", "Spam", "Recents", "Deleted Messages"}

FOLDER_MEASURES = ("email_folder_x_status_x_from_x_timestamp", "im_folder_x_status_x_platform_x_from_x_type")


def main(corpus, private, out):
    cases = {k: v["case"] for k, v in json.load(open(corpus, encoding="utf-8")).items()}
    res = json.load(open(private, encoding="utf-8"))
    for m in FOLDER_MEASURES:
        where = collections.defaultdict(set)
        for label, r in res["reports"].items():
            for k in r.get(m, {}):
                where[k.split(" | ")[0]].add(cases[label])
        keep = {v for v, c in where.items() if len(c) >= 2 or v == "<absent>" or v in SYSTEM_FOLDERS}
        for r in res["reports"].values():
            g = collections.Counter()
            for k, n in r.get(m, {}).items():
                parts = k.split(" | ")
                parts[0] = parts[0] if parts[0] in keep else "<other>"
                g[" | ".join(parts)] += n
            if m in r:
                r[m] = dict(sorted(g.items()))
    res["reports"] = {k: {x: y for x, y in v.items() if x != "seconds"} for k, v in res["reports"].items()}
    for r in res["reports"].values():
        for m, counts in r.items():
            g = collections.Counter()
            for k, n in counts.items():
                g[" | ".join("<other>" if any(rx.search(p) for _, rx in guard.RULES) else p for p in k.split(" | "))] += n
            r[m] = dict(sorted(g.items()))
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:4])
