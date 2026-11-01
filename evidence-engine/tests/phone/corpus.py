"""The reference corpus for the opt-in corpus tests (docs/cellebrite/01-intake-capture-storage.md section 12).

``LOUPE_PHONE_CORPUS`` names a JSON file on the server mapping report labels to ``{"root": <report folder>}``. The
server manifest keys the 14 reports ``P01`` to ``P14``; ``c3``, ``c9`` and ``c8`` are the server copies P06, P09 and
P02 (01 section 1.1) and are used when the file has no key of that name. ``LOUPE_PHONE_CORPUS_SCRATCH`` is a
writable folder for containers made from the corpus (a zip of a report folder). Nothing here is evidence: the
expected values in ``corpus_expected.json`` are counts only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ALIASES = {"c3": "P06", "c9": "P09", "c8": "P02"}
CORPUS = os.getenv("LOUPE_PHONE_CORPUS")
SCRATCH = os.getenv("LOUPE_PHONE_CORPUS_SCRATCH")
SKIP_REASON = "Requires LOUPE_PHONE_CORPUS (the server corpus map) and LOUPE_TEST_PHONE_PG_URL"


def expected() -> dict:
    return json.loads((Path(__file__).with_name("corpus_expected.json")).read_text())


def root(label: str) -> Path:
    data = json.loads(Path(CORPUS).read_text())
    entry = data.get(label) or data[ALIASES[label]]
    return Path(entry["root"])
