"""Final guard over a JSON output before it is committed (04 section 13): fails if any key or string value looks
like case content. Prints only the JSON path of a failing item and the rule it broke, never the item.

usage: python3 -I a3_guard_check.py <file.json> [...]
"""
import json
import re
import sys

RULES = [
    ("seven or more consecutive digits", re.compile(r"\d{7,}")),
    ("e-mail or handle", re.compile(r"[^\s|]@[^\s|]")),
    ("coordinate-like decimal", re.compile(r"-?\d{1,3}\.\d{5,}")),
    ("phone-like number", re.compile(r"\+\d[\d\s().-]{6,}")),
    ("url", re.compile(r"(?i)\b(?:https?://|www\.)")),
    ("hex digest", re.compile(r"\b[0-9a-f]{24,}\b")),
    ("long free text", re.compile(r"\S+(?: \S+){9,}")),
]
ALLOWED_LONG = re.compile(r"^(skipped|not cross-matched|Stage A3|Element-level|Structure-only|Reference corpus)")


def walk(o, path, bad):
    if isinstance(o, dict):
        for k, v in o.items():
            check(str(k), path + "/<key>", bad)
            walk(v, path + "/" + (str(k) if not any(r.search(str(k)) for _, r in RULES) else "<flagged key>"), bad)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, "%s[%d]" % (path, i), bad)
    elif isinstance(o, str):
        check(o, path, bad)


BUCKET = re.compile(r"^(?:len:)?(?:1|2|10+)-9+$")  # our own log-bucket labels, e.g. 1000000-9999999


def check(s, path, bad):
    if ALLOWED_LONG.match(s):
        return
    for name, r in RULES:
        if any(r.search(part) for part in s.split(" | ") if not BUCKET.match(part)):
            bad.append((path, name))


def main(paths):
    bad = []
    for p in paths:
        walk(json.load(open(p, encoding="utf-8")), p, bad)
    for path, name in bad:
        print("FLAG %s: %s" % (path, name))
    print("checked %d file(s), %d flag(s)" % (len(paths), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
