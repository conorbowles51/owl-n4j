#!/usr/bin/env python3
"""
Copy financial_category from legacy (v1) Transaction nodes to their matching
v2 (audit_status='proposed') counterparts.

Matching strategy:
  1. Same document + same date + same amount string  → exact match
  2. When multiple legacy rows share (doc, date, amount), use name-token
     overlap to pick the best match
  3. Legacy txns without an amount fall back to doc + date + name similarity

Only copies when the legacy category is non-empty and not 'Uncategorized'.
Skips v2 nodes that already have a manually-set category matching a legacy one
(idempotent).

Run:
    python scripts/copy_legacy_categories.py              # dry-run (default)
    python scripts/copy_legacy_categories.py --apply      # actually write
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "testpassword")
CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"


def parse_amount(amt_str: Optional[str]) -> Optional[str]:
    """Normalise amount string for comparison: strip whitespace, keep sign+digits+dot."""
    if not amt_str:
        return None
    s = amt_str.strip().replace(",", "").replace("$", "")
    # Normalise to 2 decimal places
    try:
        val = float(s)
        return f"{val:.2f}"
    except (ValueError, TypeError):
        return None


def name_tokens(name: Optional[str]) -> set:
    """Extract lowercase alpha tokens from a transaction name for fuzzy matching."""
    if not name:
        return set()
    tokens = re.split(r"[^a-zA-Z]+", name.lower())
    stopwords = {"to", "from", "the", "a", "an", "of", "for", "at", "in", "on",
                 "card", "purchase", "transfer", "debit", "credit", "zelle",
                 "check", "deposit", "payment", "adjustment"}
    return {t for t in tokens if len(t) >= 2 and t not in stopwords}


def token_overlap(a: set, b: set) -> float:
    """Jaccard-like similarity: intersection / min(len(a), len(b))."""
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    return overlap / min(len(a), len(b))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    args = parser.parse_args()
    dry_run = not args.apply

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        # ── Step 1: Load all legacy txns with categories ──
        print("Loading legacy transactions with categories...")
        legacy_result = session.run("""
            MATCH (n:Transaction)-[:MENTIONED_IN]->(d:Document)
            WHERE n.case_id = $case_id
              AND coalesce(n.audit_status, '') <> 'proposed'
              AND n.financial_category IS NOT NULL
              AND n.financial_category <> ''
              AND n.financial_category <> 'Uncategorized'
            RETURN n.key AS key, n.date AS date, n.amount AS amount,
                   n.name AS name, n.financial_category AS category,
                   d.name AS doc_name
        """, case_id=CASE_ID)

        # Index legacy by (doc, date, normalised_amount)
        # Structure: {(doc, date, norm_amt): [(key, name, category, name_tokens)]}
        legacy_by_dda: Dict[Tuple[str, str, Optional[str]], list] = defaultdict(list)
        # Also index by (doc, date) for fallback
        legacy_by_dd: Dict[Tuple[str, str], list] = defaultdict(list)
        legacy_count = 0

        for rec in legacy_result:
            legacy_count += 1
            norm_amt = parse_amount(rec["amount"])
            entry = {
                "key": rec["key"],
                "name": rec["name"],
                "category": rec["category"],
                "tokens": name_tokens(rec["name"]),
                "amount": norm_amt,
                "doc": rec["doc_name"],
            }
            legacy_by_dda[(rec["doc_name"], rec["date"], norm_amt)].append(entry)
            legacy_by_dd[(rec["doc_name"], rec["date"])].append(entry)

        print(f"  Loaded {legacy_count} legacy txns with categories")

        # ── Step 2: Load all v2 txns ──
        print("Loading v2 transactions...")
        v2_result = session.run("""
            MATCH (n:Transaction)-[:MENTIONED_IN]->(d:Document)
            WHERE n.case_id = $case_id
              AND n.audit_status = 'proposed'
            RETURN n.key AS key, n.date AS date, n.amount AS amount,
                   n.name AS name, n.financial_category AS current_cat,
                   n.audit_channel AS channel, d.name AS doc_name
        """, case_id=CASE_ID)

        v2_txns = []
        for rec in v2_result:
            v2_txns.append({
                "key": rec["key"],
                "date": rec["date"],
                "amount": rec["amount"],
                "name": rec["name"],
                "current_cat": rec["current_cat"],
                "channel": rec["channel"],
                "doc": rec["doc_name"],
            })
        print(f"  Loaded {len(v2_txns)} v2 txns")

        # ── Step 3: Match and collect updates ──
        print("\nMatching...")
        updates = []  # [(v2_key, new_category, new_name_or_None, match_type)]
        matched = 0
        skipped_already_set = 0
        no_match = 0
        ambiguous = 0

        for v2 in v2_txns:
            norm_amt = parse_amount(v2["amount"])
            v2_tokens = name_tokens(v2["name"])

            # Try exact (doc, date, amount) match first
            candidates = legacy_by_dda.get((v2["doc"], v2["date"], norm_amt), [])

            if not candidates and norm_amt is not None:
                # Try negated amount (sign mismatch between legacy and v2)
                try:
                    neg_amt = f"{-float(norm_amt):.2f}"
                    candidates = legacy_by_dda.get((v2["doc"], v2["date"], neg_amt), [])
                except (ValueError, TypeError):
                    pass

            match_type = "exact"

            if not candidates:
                # Fallback: doc + date, pick by name similarity
                candidates = legacy_by_dd.get((v2["doc"], v2["date"]), [])
                match_type = "name_fallback"

            if not candidates:
                no_match += 1
                continue

            if len(candidates) == 1:
                best = candidates[0]
            else:
                # If all candidates share the same category, use it directly
                unique_cats = set(c["category"] for c in candidates)
                if len(unique_cats) == 1:
                    best = candidates[0]
                else:
                    # Pick the candidate with best name-token overlap
                    scored = [(c, token_overlap(v2_tokens, c["tokens"])) for c in candidates]
                    scored.sort(key=lambda x: x[1], reverse=True)
                    best = scored[0][0]
                    best_score = scored[0][1]
                    # If top two have different categories but same score and
                    # score is low, skip (genuinely ambiguous)
                    if (len(scored) > 1
                            and scored[0][1] == scored[1][1]
                            and best_score < 0.3
                            and scored[0][0]["category"] != scored[1][0]["category"]):
                        ambiguous += 1
                        continue

            legacy_cat = best["category"]

            # Determine if name needs updating: when the channel defaulted to
            # "Other" the name reads "Other from ..." / "Other to ..." — replace
            # that prefix with the incoming legacy category so it's meaningful.
            new_name = None
            old_name = v2["name"] or ""
            channel = v2["channel"] or ""
            if channel == "Other" and (
                    old_name.startswith("Other from ")
                    or old_name.startswith("Other to ")):
                if legacy_cat != "Other":
                    new_name = legacy_cat + old_name[len("Other"):]

            # Skip if v2 already has this exact category and no name fix needed
            if v2["current_cat"] == legacy_cat and new_name is None:
                skipped_already_set += 1
                continue

            updates.append((v2["key"], legacy_cat, new_name, match_type))
            matched += 1

        print(f"\n  Matched: {matched}")
        print(f"  Already set: {skipped_already_set}")
        print(f"  No match: {no_match}")
        print(f"  Ambiguous (skipped): {ambiguous}")
        print(f"  Total v2: {len(v2_txns)}")

        # Show category distribution of updates
        cat_counts = defaultdict(int)
        for _, cat, _, _ in updates:
            cat_counts[cat] += 1
        print("\n  Categories being copied:")
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            print(f"    {cat}: {cnt}")

        name_fixes = sum(1 for _, _, nm, _ in updates if nm is not None)
        print(f"\n  Name prefix fixes: {name_fixes}")

        match_type_counts = defaultdict(int)
        for _, _, _, mt in updates:
            match_type_counts[mt] += 1
        print(f"\n  By match type: {dict(match_type_counts)}")

        # Show a few name fix examples
        if name_fixes > 0:
            print("\n  Sample name fixes:")
            shown = 0
            for key, cat, nm, _ in updates:
                if nm is not None and shown < 5:
                    shown += 1
                    # Find the original name
                    orig = next((v["name"] for v in v2_txns if v["key"] == key), "?")
                    print(f"    {orig[:60]}")
                    print(f"    → {nm[:60]}")

        # ── Step 4: Apply updates ──
        if dry_run:
            print(f"\n  DRY RUN — no changes written. Use --apply to write.")
        else:
            print(f"\n  Writing {len(updates)} updates...")
            batch_size = 500
            written = 0
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i + batch_size]
                # Use UNWIND for efficient batched update
                session.run("""
                    UNWIND $batch AS row
                    MATCH (n:Transaction {key: row.key, case_id: $case_id})
                    SET n.financial_category = row.category
                    SET n.name = CASE WHEN row.new_name IS NOT NULL
                                      THEN row.new_name ELSE n.name END
                """, batch=[{"key": k, "category": c, "new_name": nm}
                            for k, c, nm, _ in batch],
                   case_id=CASE_ID)
                written += len(batch)
                print(f"    Written {written}/{len(updates)}")
            print(f"  Done! {written} v2 nodes updated (categories + name fixes).")

    driver.close()


if __name__ == "__main__":
    main()
