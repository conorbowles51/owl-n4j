"""Folded document text for search (03 section 11.3, D-40): fill and refresh ``evidence_text_folds``.

``backfill(engine)`` folds every document text whose fold is missing, made from different text, or made by an
older fold, in batches committed one by one, so it resumes where it stopped. The phone worker runs it after each
pass with a time budget; ``scripts/fold_documents.py`` runs it to the end and prints counts and timings per case.
Thread documents written from phone records are folded too: their text is searchable like any document's.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict

from sqlalchemy import text

from services.phone import fold as F

log = logging.getLogger(__name__)
FOLD_VERSION = "fold-map/1"
BATCH = 10
WORKER_BUDGET_SECONDS = 20.0

STALE = ("FROM evidence_document_texts t JOIN evidence_files f ON f.id = t.evidence_file_id "
         "LEFT JOIN evidence_text_folds x ON x.evidence_file_id = t.evidence_file_id "
         "WHERE t.content IS NOT NULL AND (x.evidence_file_id IS NULL OR x.content_sha256 IS DISTINCT FROM "
         "t.content_sha256 OR x.fold_version <> :v)")


def remaining(conn) -> int:
    return int(conn.execute(text("SELECT count(*) " + STALE), {"v": FOLD_VERSION}).scalar() or 0)


def fold_one(conn, evidence_file_id, case_id, content, sha) -> int:
    started = time.perf_counter()
    folded, starts = F.fold_with_map(content)
    ms = int((time.perf_counter() - started) * 1000)
    conn.execute(text(
        "INSERT INTO evidence_text_folds (evidence_file_id, case_id, content_sha256, fold_version, content_folded, "
        "fold_map, original_chars, fold_ms, folded_at) VALUES (:i, :c, :h, :v, :f, :m, :n, :ms, now()) "
        "ON CONFLICT (evidence_file_id) DO UPDATE SET case_id = EXCLUDED.case_id, content_sha256 = "
        "EXCLUDED.content_sha256, fold_version = EXCLUDED.fold_version, content_folded = EXCLUDED.content_folded, "
        "fold_map = EXCLUDED.fold_map, original_chars = EXCLUDED.original_chars, fold_ms = EXCLUDED.fold_ms, "
        "folded_at = now()"),
        {"i": evidence_file_id, "c": case_id, "h": sha or "", "v": FOLD_VERSION, "f": folded,
         "m": F.pack_map(starts), "n": len(content), "ms": ms})
    return ms


def backfill(engine, budget_seconds=None, batch=BATCH) -> dict:
    """Fold what is stale, a batch per transaction, until done or ``budget_seconds`` is spent. Returns
    ``{"folded", "chars", "seconds", "remaining", "by_case": {case: {"rows", "chars", "ms"}}}``."""
    started = time.perf_counter()
    by_case = defaultdict(lambda: {"rows": 0, "chars": 0, "ms": 0})
    done = chars = 0
    while budget_seconds is None or time.perf_counter() - started < budget_seconds:
        with engine.begin() as conn:
            rows = conn.execute(text(
                "SELECT t.evidence_file_id, f.case_id, t.content, t.content_sha256 " + STALE +
                " ORDER BY t.evidence_file_id LIMIT :b FOR UPDATE OF t SKIP LOCKED"),
                {"v": FOLD_VERSION, "b": batch}).fetchall()
            if not rows:
                break
            for r in rows:
                if budget_seconds is not None and done and time.perf_counter() - started >= budget_seconds:
                    break  # the rest of the batch waits for the next pass
                ms = fold_one(conn, r.evidence_file_id, r.case_id, r.content, r.content_sha256)
                c = by_case[str(r.case_id)]
                c["rows"] += 1
                c["chars"] += len(r.content)
                c["ms"] += ms
                done += 1
                chars += len(r.content)
    with engine.connect() as conn:
        left = remaining(conn)
    out = {"folded": done, "chars": chars, "seconds": round(time.perf_counter() - started, 2), "remaining": left,
           "by_case": dict(by_case)}
    if done:
        log.info("document folds: %d folded (%d characters) in %.1f s, %d remaining", done, chars, out["seconds"],
                 left)
    return out


def _after_pass(engine):
    backfill(engine, budget_seconds=WORKER_BUDGET_SECONDS)


def install():
    """Called by the phone worker: fold documents for search after each pass, at most 20 s at a time."""
    from services.phone import sweep
    sweep.register_after_pass(_after_pass)
