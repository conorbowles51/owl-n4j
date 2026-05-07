"""One-time maintenance: strip embedded NUL bytes from existing ChromaDB
documents and metadata.

PRECONDITIONS (do not run with --apply without these):
  1. Fresh host backup of the chroma volume taken today.
  2. The boundary-fix code (sanitization in `app/services/chroma_client.py`)
     has been deployed for at least 24h with no regressions.

Usage:
  # Dry run — report only, no writes:
  python -m scripts.scrub_chromadb_nulls

  # Single collection, dry run:
  python -m scripts.scrub_chromadb_nulls --collection case_xxx_documents

  # Apply (writes), bounded:
  python -m scripts.scrub_chromadb_nulls --apply --collection case_xxx_documents --max-rewrite 100

Embeddings are intentionally preserved by using `collection.update()` (which
touches only the supplied fields) rather than `upsert()` — in chromadb 1.x,
upsert without an `embeddings` kwarg invokes the collection's embedding
function and would either error on dimension mismatch or silently overwrite
vectors with the default model. Do NOT change `update` to `upsert` here.

Re-embedding is intentionally NOT performed: existing vectors were generated
from text containing NULs (which tokenisers ignore or unknown-token), and
recomputing would change vector distribution and risk ranking shifts on
otherwise-stable queries with no upside.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

from app.services.chroma_client import get_chroma_client
from app.utils.text_sanitize import sanitize_json, sanitize_text

BATCH = 500


def _value_has_null(value: Any) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_value_has_null(v) for v in value.values())
    if isinstance(value, list):
        return any(_value_has_null(v) for v in value)
    return False


def _scrub_collection(coll, apply: bool, max_rewrite: int | None) -> dict[str, int]:
    stats = {"scanned": 0, "dirty": 0, "rewritten": 0, "bytes_removed": 0}

    offset = 0
    while True:
        result = coll.get(
            include=["documents", "metadatas"],
            limit=BATCH,
            offset=offset,
        )
        ids = result.get("ids") or []
        if not ids:
            break

        documents = result.get("documents") or [None] * len(ids)
        metadatas = result.get("metadatas") or [None] * len(ids)

        dirty_ids: list[str] = []
        clean_docs: list[str] = []
        clean_metas: list[dict[str, Any]] = []

        for cid, doc, meta in zip(ids, documents, metadatas):
            stats["scanned"] += 1
            doc_dirty = isinstance(doc, str) and "\x00" in doc
            meta_dirty = _value_has_null(meta) if meta else False
            if not (doc_dirty or meta_dirty):
                continue

            stats["dirty"] += 1
            new_doc = sanitize_text(doc) if isinstance(doc, str) else doc
            new_meta = sanitize_json(meta) if meta else meta
            if isinstance(doc, str) and isinstance(new_doc, str):
                stats["bytes_removed"] += len(doc) - len(new_doc)

            dirty_ids.append(cid)
            clean_docs.append(new_doc)
            clean_metas.append(new_meta)

            if max_rewrite is not None and stats["dirty"] >= max_rewrite:
                break

        if dirty_ids and apply:
            # IMPORTANT: use update(), NOT upsert(). update() only modifies
            # the supplied fields and never re-runs the embedding function.
            # See module docstring.
            coll.update(
                ids=dirty_ids,
                documents=clean_docs,
                metadatas=clean_metas,
            )
            stats["rewritten"] += len(dirty_ids)

        if max_rewrite is not None and stats["dirty"] >= max_rewrite:
            print(f"[scrub-chroma]   reached --max-rewrite={max_rewrite}, stopping early")
            break

        offset += len(ids)
        if len(ids) < BATCH:
            break

    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually rewrite (default: dry-run report)")
    parser.add_argument("--collection", default=None, help="Scrub only this collection name")
    parser.add_argument("--max-rewrite", type=int, default=None, help="Stop after N dirty rows (per collection)")
    args = parser.parse_args()

    client = get_chroma_client()

    if args.collection:
        try:
            collections = [client.get_collection(name=args.collection)]
        except Exception as e:
            print(f"[scrub-chroma] FATAL: collection {args.collection!r} not found: {e}")
            return 1
    else:
        listed = client.list_collections()
        names = [c.name if hasattr(c, "name") else str(c) for c in listed]
        collections = [client.get_collection(name=n) for n in names]

    grand = {"scanned": 0, "dirty": 0, "rewritten": 0, "bytes_removed": 0}

    print(f"[scrub-chroma] mode={'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"[scrub-chroma] {len(collections)} collection(s)")
    if args.max_rewrite is not None:
        print(f"[scrub-chroma] max-rewrite per collection = {args.max_rewrite}")

    for coll in collections:
        name = getattr(coll, "name", "<unknown>")
        stats = _scrub_collection(coll, apply=args.apply, max_rewrite=args.max_rewrite)
        print(
            f"[scrub-chroma] {name}: scanned={stats['scanned']} "
            f"dirty={stats['dirty']} rewritten={stats['rewritten']} "
            f"bytes_removed={stats['bytes_removed']}"
        )
        for k in grand:
            grand[k] += stats[k]

    print(
        f"[scrub-chroma] TOTAL scanned={grand['scanned']} "
        f"dirty={grand['dirty']} rewritten={grand['rewritten']} "
        f"bytes_removed={grand['bytes_removed']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
