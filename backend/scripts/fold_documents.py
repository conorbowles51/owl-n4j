"""Fold every document text for Loupe-wide search, to the end, and print counts and timings per case (03 D-40).

The same backfill the phone worker runs 20 s at a time after each pass; this runs it until nothing is left. It is
resumable: stopping it loses at most the batch in hand. Output is counts and timings only: case ids, rows,
characters, milliseconds.

    python scripts/fold_documents.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from postgres.session import _get_engine  # noqa: E402
from services.search import document_folds  # noqa: E402


def main() -> int:
    engine = _get_engine()
    with engine.connect() as conn:
        before = document_folds.remaining(conn)
    out = document_folds.backfill(engine)
    print(json.dumps({"stale_before": before, "folded": out["folded"], "characters": out["chars"],
                      "seconds": out["seconds"], "remaining": out["remaining"], "by_case": out["by_case"]},
                     sort_keys=True))
    return 0 if out["remaining"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
