"""Build the two tables of name folding (docs/cellebrite/02 section 8.4, steps 2 and 3).

    python scripts/phone_build_confusables.py /path/to/confusables.txt

- ``services/phone/data/confusables_latin.json``: from Unicode UTS #39 ``confusables.txt`` (pinned to 13.0.0, the
  Unicode version of Python 3.10's ``unicodedata``; its date and sha256 go in the header), the characters of the
  Cyrillic and Greek blocks that the file lists as confusable with exactly one ASCII letter.
- ``services/phone/data/styled_letters.json``: the styled letters NFKC leaves alone (negative circled and negative
  squared Latin capitals, regional indicators, Latin small capitals) to A to Z, as listed in 8.4 step 2.

Both are structure only: code points and letters, no case material.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "services", "phone", "data")
PINNED_VERSION = "13.0.0"
BLOCKS = ((0x0370, 0x03FF), (0x0400, 0x04FF), (0x0500, 0x052F), (0x1F00, 0x1FFF))
SMALL_CAPITALS = {"A": 0x1D00, "B": 0x0299, "C": 0x1D04, "D": 0x1D05, "E": 0x1D07, "F": 0xA730, "G": 0x0262,
                  "H": 0x029C, "I": 0x026A, "J": 0x1D0A, "K": 0x1D0B, "L": 0x029F, "M": 0x1D0D, "N": 0x0274,
                  "O": 0x1D0F, "P": 0x1D18, "R": 0x0280, "S": 0xA731, "T": 0x1D1B, "U": 0x1D1C, "V": 0x1D20,
                  "W": 0x1D21, "Y": 0x028F, "Z": 0x1D22}


def in_blocks(cp):
    return any(lo <= cp <= hi for lo, hi in BLOCKS)


def confusables(path):
    raw = open(path, "rb").read()
    text = raw.decode("utf-8-sig")
    date = re.search(r"^# Date: (.+)$", text, re.M)
    out = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        src, target = [p.strip() for p in line.split(";")[:2]]
        if " " in src:
            continue
        cp = int(src, 16)
        tgt = [int(x, 16) for x in target.split()]
        if in_blocks(cp) and len(tgt) == 1 and chr(tgt[0]).isascii() and chr(tgt[0]).isalpha():
            if unicodedata.name(chr(cp), ""):  # present in this Python's Unicode (13.0 on 3.10)
                out["%04X" % cp] = chr(tgt[0])
    return {"source": "Unicode UTS #39 confusables.txt", "version": PINNED_VERSION,
            "date": date.group(1).strip() if date else None, "sha256": hashlib.sha256(raw).hexdigest(),
            "rule": "Cyrillic and Greek block characters confusable with exactly one ASCII letter",
            "map": dict(sorted(out.items()))}


def styled():
    m = {}
    for i in range(26):
        m["%04X" % (0x1F150 + i)] = chr(65 + i)  # negative circled Latin capitals
        m["%04X" % (0x1F170 + i)] = chr(65 + i)  # negative squared Latin capitals
        m["%04X" % (0x1F1E6 + i)] = chr(65 + i)  # regional indicator symbols
    for letter, cp in SMALL_CAPITALS.items():
        m["%04X" % cp] = letter
    return {"source": "docs/cellebrite/02 section 8.4 step 2", "map": dict(sorted(m.items()))}


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    for name, doc in (("confusables_latin.json", confusables(argv[1])), ("styled_letters.json", styled())):
        with open(os.path.join(DATA, name), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1, sort_keys=False)
            fh.write("\n")
        print(name, len(doc["map"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
