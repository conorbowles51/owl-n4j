"""One-time maintenance: strip embedded NUL bytes from Neo4j string
properties on nodes and relationships.

PRECONDITIONS (do not run with --apply without these):
  1. Fresh Neo4j backup taken today (`neo4j-admin database dump` or online
     backup if Enterprise).
  2. ChromaDB scrub completed and 24h hold-back observed.

Usage:
  # Dry run — count only:
  python -m scripts.scrub_neo4j_nulls

  # Apply (writes), case-scoped, bounded:
  python -m scripts.scrub_neo4j_nulls --apply --case-id <id> --max-rewrite 100

  # Apply, single label only:
  python -m scripts.scrub_neo4j_nulls --apply --label Person

The pagination pattern is intentionally `LIMIT $batch` with NO `SKIP` —
cleaned rows naturally drop out of the WHERE filter, so each next batch
returns the next chunk of dirty rows. Failed writes are tracked in a
`failed_ids` set and excluded from subsequent batches to avoid loops.

`SET n = $props` replaces only the property bag (Neo4j labels and
relationship types are preserved). `properties(n)` returns the full user
property set, so the round-trip is lossless apart from NUL/lone-surrogate
removal in string values.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from app.services import neo4j_client
from app.utils.text_sanitize import sanitize_json

BATCH = 500
NUL = "\x00"


def _build_node_match(label: str | None, case_id: str | None) -> tuple[str, dict[str, Any]]:
    label_clause = f":`{label}`" if label else ""
    where_extras: list[str] = []
    params: dict[str, Any] = {"nul": NUL}
    if case_id is not None:
        where_extras.append("n.case_id = $case_id")
        params["case_id"] = case_id
    base = f"MATCH (n{label_clause}) WHERE any(k IN keys(n) WHERE toString(n[k]) CONTAINS $nul)"
    for extra in where_extras:
        base += f" AND {extra}"
    return base, params


def _build_rel_match(case_id: str | None) -> tuple[str, dict[str, Any]]:
    where_extras: list[str] = []
    params: dict[str, Any] = {"nul": NUL}
    if case_id is not None:
        where_extras.append("r.case_id = $case_id")
        params["case_id"] = case_id
    base = "MATCH ()-[r]->() WHERE any(k IN keys(r) WHERE toString(r[k]) CONTAINS $nul)"
    for extra in where_extras:
        base += f" AND {extra}"
    return base, params


async def _count(match_clause: str, params: dict[str, Any], var: str) -> int:
    rows = await neo4j_client.execute_query(
        f"{match_clause} RETURN count({var}) AS c", params
    )
    return rows[0]["c"] if rows else 0


async def _scrub_nodes(
    apply: bool,
    label: str | None,
    case_id: str | None,
    max_rewrite: int | None,
) -> dict[str, int]:
    stats = {"dirty_initial": 0, "scanned": 0, "rewritten": 0, "skipped": 0}
    match_clause, base_params = _build_node_match(label, case_id)

    stats["dirty_initial"] = await _count(match_clause, base_params, "n")
    print(f"[scrub-neo4j] nodes dirty (initial): {stats['dirty_initial']}")
    if stats["dirty_initial"] == 0 or not apply:
        return stats

    failed_ids: list[int] = []

    while True:
        if max_rewrite is not None and stats["rewritten"] >= max_rewrite:
            print(f"[scrub-neo4j]   nodes: reached --max-rewrite={max_rewrite}, stopping")
            break

        params = {**base_params, "failed": failed_ids, "limit": BATCH}
        rows = await neo4j_client.execute_query(
            f"{match_clause} AND NOT id(n) IN $failed "
            f"RETURN id(n) AS id, properties(n) AS props "
            f"ORDER BY id(n) LIMIT $limit",
            params,
        )
        if not rows:
            break

        for row in rows:
            stats["scanned"] += 1
            cleaned = sanitize_json(row["props"])
            try:
                await neo4j_client.execute_write(
                    "MATCH (n) WHERE id(n) = $id SET n = $props",
                    {"id": row["id"], "props": cleaned},
                )
                stats["rewritten"] += 1
            except Exception as e:
                failed_ids.append(row["id"])
                stats["skipped"] += 1
                print(f"[scrub-neo4j]   skip node id={row['id']} ({type(e).__name__}: {e})")

            if max_rewrite is not None and stats["rewritten"] >= max_rewrite:
                break

    return stats


async def _scrub_relationships(
    apply: bool,
    case_id: str | None,
    max_rewrite: int | None,
) -> dict[str, int]:
    stats = {"dirty_initial": 0, "scanned": 0, "rewritten": 0, "skipped": 0}
    match_clause, base_params = _build_rel_match(case_id)

    stats["dirty_initial"] = await _count(match_clause, base_params, "r")
    print(f"[scrub-neo4j] rels dirty (initial): {stats['dirty_initial']}")
    if stats["dirty_initial"] == 0 or not apply:
        return stats

    failed_ids: list[int] = []

    while True:
        if max_rewrite is not None and stats["rewritten"] >= max_rewrite:
            print(f"[scrub-neo4j]   rels: reached --max-rewrite={max_rewrite}, stopping")
            break

        params = {**base_params, "failed": failed_ids, "limit": BATCH}
        rows = await neo4j_client.execute_query(
            f"{match_clause} AND NOT id(r) IN $failed "
            f"RETURN id(r) AS id, properties(r) AS props "
            f"ORDER BY id(r) LIMIT $limit",
            params,
        )
        if not rows:
            break

        for row in rows:
            stats["scanned"] += 1
            cleaned = sanitize_json(row["props"])
            try:
                await neo4j_client.execute_write(
                    "MATCH ()-[r]->() WHERE id(r) = $id SET r = $props",
                    {"id": row["id"], "props": cleaned},
                )
                stats["rewritten"] += 1
            except Exception as e:
                failed_ids.append(row["id"])
                stats["skipped"] += 1
                print(f"[scrub-neo4j]   skip rel id={row['id']} ({type(e).__name__}: {e})")

            if max_rewrite is not None and stats["rewritten"] >= max_rewrite:
                break

    return stats


async def _verify(label: str | None, case_id: str | None) -> tuple[int, int]:
    nm, np = _build_node_match(label, case_id)
    rm, rp = _build_rel_match(case_id)
    return (
        await _count(nm, np, "n"),
        await _count(rm, rp, "r"),
    )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually rewrite (default: dry-run count)")
    parser.add_argument("--label", default=None, help="Limit nodes to this label")
    parser.add_argument("--case-id", default=None, help="Limit to nodes/rels with this case_id property")
    parser.add_argument("--max-rewrite", type=int, default=None, help="Stop after N rewrites (per pass)")
    parser.add_argument("--skip-rels", action="store_true", help="Only scrub nodes, not relationships")
    args = parser.parse_args()

    print(f"[scrub-neo4j] mode={'APPLY' if args.apply else 'DRY-RUN'}")
    if args.label:
        print(f"[scrub-neo4j] label filter: {args.label}")
    if args.case_id:
        print(f"[scrub-neo4j] case-id filter: {args.case_id}")
    if args.max_rewrite is not None:
        print(f"[scrub-neo4j] max-rewrite per pass = {args.max_rewrite}")

    node_stats = await _scrub_nodes(
        apply=args.apply,
        label=args.label,
        case_id=args.case_id,
        max_rewrite=args.max_rewrite,
    )
    print(
        f"[scrub-neo4j] nodes: dirty_initial={node_stats['dirty_initial']} "
        f"scanned={node_stats['scanned']} rewritten={node_stats['rewritten']} "
        f"skipped={node_stats['skipped']}"
    )

    if not args.skip_rels:
        rel_stats = await _scrub_relationships(
            apply=args.apply,
            case_id=args.case_id,
            max_rewrite=args.max_rewrite,
        )
        print(
            f"[scrub-neo4j] rels: dirty_initial={rel_stats['dirty_initial']} "
            f"scanned={rel_stats['scanned']} rewritten={rel_stats['rewritten']} "
            f"skipped={rel_stats['skipped']}"
        )

    if args.apply:
        node_remaining, rel_remaining = await _verify(args.label, args.case_id)
        print(
            f"[scrub-neo4j] post-verify: nodes_with_nul={node_remaining} "
            f"rels_with_nul={rel_remaining}"
        )

    await neo4j_client.close_neo4j()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
