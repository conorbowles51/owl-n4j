#!/usr/bin/env python3
"""
Audit comparison: re-extracted PDF JSON  vs  stored Neo4j transactions.

For one (or all) doc(s) under ingestion/data/audit_results/<date>/,
load the extracted ground truth, pull every node with an `amount` that
MENTIONED_IN that document from Neo4j, and emit a side-by-side report.

Categorisation per stored row:
  - matched_correct        : matches an extracted row, direction agrees, parties agree
  - matched_direction_flip : matches by date+amount, but stored direction is opposite
  - matched_missing_party  : matches by date+amount, direction OK, but a from/to side is NULL
  - matched_party_mismatch : matches by date+amount, direction OK, but the named party
                             differs from what the PDF says
  - duplicate_of           : a 2nd, 3rd, ... stored row pointing at the same extracted row
  - orphan_in_store        : stored row with no matching extracted row (could be hallucination
                             or could be a real row I missed in extraction)

Categorisation per extracted (truth) row:
  - missing_in_store       : extracted row with no matching stored row
  - covered                : ≥1 matching stored row exists

Matching heuristic:
  date == date  AND  abs(amount - amount) < 0.01
  Counterparty agreement is judged separately on the matched set, not used as a key,
  because the bug we are hunting often *flips* the counterparty.

Run:
  python scripts/audit_compare.py                          # all docs in audit_results/2026-04-11
  python scripts/audit_compare.py USA-ET-000388.pdf        # one doc
  python scripts/audit_compare.py --date 2026-04-11        # explicit dated subdir
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from neo4j import GraphDatabase

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "testpassword")
CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"  # ET-Fraud / Eric Tataw

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_ROOT = REPO_ROOT / "ingestion" / "data" / "audit_results"

AMOUNT_TOLERANCE = 0.01

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_AMT_CLEAN = re.compile(r"[^\d\-.]")

def parse_amount(raw) -> Optional[float]:
    """Parse a Neo4j-stored amount (string or number) to a float, or None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return abs(float(raw))
    s = str(raw).strip()
    # Strip currency symbols and thousands separators, keep sign and decimal
    cleaned = _AMT_CLEAN.sub("", s.replace(",", ""))
    if not cleaned or cleaned in ("-", "."):
        return None
    try:
        return abs(float(cleaned))
    except ValueError:
        return None


def normalise_name(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def names_agree(a: Optional[str], b: Optional[str]) -> bool:
    """Loose name agreement: substring after normalisation."""
    na, nb = normalise_name(a), normalise_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 3 and (na in nb or nb in na):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Neo4j fetch
# ─────────────────────────────────────────────────────────────────────────────

CYPHER_FETCH = """
MATCH (n)-[:MENTIONED_IN]->(d:Document {name: $doc_name, case_id: $case_id})
WHERE n.amount IS NOT NULL
RETURN
  labels(n)[0]               AS type,
  n.key                      AS key,
  n.name                     AS name,
  n.date                     AS date,
  n.amount                   AS amount_raw,
  n.from_entity_name         AS from_name,
  n.from_entity_key          AS from_key,
  n.to_entity_name           AS to_name,
  n.to_entity_key            AS to_key,
  n.has_manual_from          AS has_manual_from,
  n.has_manual_to            AS has_manual_to,
  n.financial_category       AS category
"""


def fetch_stored(driver, doc_name: str) -> List[Dict]:
    with driver.session() as s:
        result = s.run(CYPHER_FETCH, doc_name=doc_name, case_id=CASE_ID)
        rows = []
        for r in result:
            rows.append({
                "type": r["type"],
                "key": r["key"],
                "name": r["name"],
                "date": r["date"],
                "amount": parse_amount(r["amount_raw"]),
                "amount_raw": r["amount_raw"],
                "from_name": r["from_name"],
                "to_name": r["to_name"],
                "has_manual_from": bool(r["has_manual_from"]),
                "has_manual_to": bool(r["has_manual_to"]),
                "category": r["category"],
            })
        return rows


# ─────────────────────────────────────────────────────────────────────────────
# Comparison
# ─────────────────────────────────────────────────────────────────────────────

def infer_stored_direction(account_holder: str, stored: Dict) -> Optional[str]:
    """
    Best-effort: figure out which direction a stored row claims.
      - 'in'  if account_holder appears in TO slot
      - 'out' if account_holder appears in FROM slot
      - None if neither side names the account holder
    """
    if names_agree(account_holder, stored.get("to_name")):
        return "in"
    if names_agree(account_holder, stored.get("from_name")):
        return "out"
    return None


def compare(extracted: Dict, stored_rows: List[Dict]) -> Dict:
    """Compare one document's extracted truth against its stored rows."""
    account_holder = extracted["account_holder"]
    truth_rows = extracted["transactions"]

    # Index stored rows by (date, amount_bucket) for matching
    stored_by_key: Dict[tuple, List[Dict]] = defaultdict(list)
    for s in stored_rows:
        if s["amount"] is None or s["date"] is None:
            continue
        key = (s["date"], round(s["amount"], 2))
        stored_by_key[key].append(s)

    findings_per_truth = []
    matched_stored_indices = set()

    for t in truth_rows:
        t_date = t["date"]
        t_amount = round(float(t["amount"]), 2)
        key = (t_date, t_amount)
        candidates = stored_by_key.get(key, [])

        if not candidates:
            findings_per_truth.append({
                "row_index": t["row_index"],
                "date": t_date,
                "amount": t_amount,
                "truth_direction": t["direction"],
                "truth_from": t["from_party"],
                "truth_to": t["to_party"],
                "verdict": "missing_in_store",
                "matched_stored": [],
            })
            continue

        per_candidate = []
        for cand in candidates:
            cand_id = id(cand)
            matched_stored_indices.add(cand_id)

            stored_dir = infer_stored_direction(account_holder, cand)
            verdict_parts = []

            # Direction check
            if stored_dir is None:
                # Stored row didn't name the account holder on either side
                verdict_parts.append("missing_party")
            elif stored_dir != t["direction"]:
                verdict_parts.append("direction_flip")
            # else direction agrees → no part added yet

            # Counterparty (the non-account-holder side) check, only if direction known
            if stored_dir is not None:
                truth_counterparty = t["from_party"] if t["direction"] == "in" else t["to_party"]
                stored_counterparty = cand["from_name"] if stored_dir == "in" else cand["to_name"]
                if not stored_counterparty:
                    if "missing_party" not in verdict_parts:
                        verdict_parts.append("missing_party")
                elif not names_agree(truth_counterparty, stored_counterparty):
                    verdict_parts.append("party_mismatch")

            verdict = "correct" if not verdict_parts else "+".join(verdict_parts)

            per_candidate.append({
                "stored_key": cand["key"],
                "stored_label": cand["type"],
                "stored_name": cand["name"],
                "stored_from": cand["from_name"],
                "stored_to": cand["to_name"],
                "stored_direction_inferred": stored_dir,
                "verdict": verdict,
                "has_manual_from": cand["has_manual_from"],
                "has_manual_to": cand["has_manual_to"],
                "category": cand["category"],
            })

        findings_per_truth.append({
            "row_index": t["row_index"],
            "date": t_date,
            "amount": t_amount,
            "truth_direction": t["direction"],
            "truth_from": t["from_party"],
            "truth_to": t["to_party"],
            "verdict": "covered",
            "match_count": len(per_candidate),
            "matched_stored": per_candidate,
        })

    # Stored rows that never matched a truth row
    orphans = []
    for s in stored_rows:
        if id(s) in matched_stored_indices:
            continue
        # Skip non-monetary nodes such as Account_Balance / AccountSummary
        if s["amount"] is None or s["date"] is None:
            continue
        if (s["type"] or "").lower() in {
            "account_balance", "accountbalance", "accountsummary",
            "account_summary", "accountstatement", "statement",
            "statementsummary", "balance", "accountbalancesnapshot",
            "accountbalanceevent", "loanpayoffbalance",
            "deferredinterestbalance", "transactionsummary",
            "balancesummary", "creditaccountbalance",
        }:
            continue
        orphans.append({
            "stored_key": s["key"],
            "stored_label": s["type"],
            "stored_name": s["name"],
            "date": s["date"],
            "amount": s["amount"],
            "from_name": s["from_name"],
            "to_name": s["to_name"],
        })

    # Aggregate counters
    counters = {
        "truth_rows": len(truth_rows),
        "stored_rows_with_amount": len(stored_rows),
        "truth_missing_in_store": 0,
        "truth_covered": 0,
        "stored_correct": 0,
        "stored_direction_flip": 0,
        "stored_missing_party": 0,
        "stored_party_mismatch": 0,
        "stored_combo_issues": 0,
        "stored_duplicate_overcounts": 0,  # how many extra stored rows beyond 1 per truth row
        "stored_orphans": len(orphans),
    }
    for f in findings_per_truth:
        if f["verdict"] == "missing_in_store":
            counters["truth_missing_in_store"] += 1
            continue
        counters["truth_covered"] += 1
        if f["match_count"] > 1:
            counters["stored_duplicate_overcounts"] += f["match_count"] - 1
        for m in f["matched_stored"]:
            v = m["verdict"]
            if v == "correct":
                counters["stored_correct"] += 1
            elif v == "direction_flip":
                counters["stored_direction_flip"] += 1
            elif v == "missing_party":
                counters["stored_missing_party"] += 1
            elif v == "party_mismatch":
                counters["stored_party_mismatch"] += 1
            else:
                counters["stored_combo_issues"] += 1

    return {
        "doc_name": extracted["doc_name"],
        "account_holder": account_holder,
        "counters": counters,
        "findings_per_truth": findings_per_truth,
        "orphans": orphans,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def render_markdown(report: Dict) -> str:
    c = report["counters"]
    out = []
    out.append(f"## {report['doc_name']}  —  account holder: **{report['account_holder']}**\n")
    out.append("**Headline counters**\n")
    out.append("```")
    for k, v in c.items():
        out.append(f"  {k:<35s} {v}")
    out.append("```\n")

    # Per-truth-row issues
    issue_rows = [f for f in report["findings_per_truth"] if f["verdict"] == "missing_in_store"
                  or any(m["verdict"] != "correct" for m in f.get("matched_stored", []))
                  or f.get("match_count", 0) > 1]
    if issue_rows:
        out.append("**Issue rows (truth → store):**\n")
        for f in issue_rows[:60]:  # Cap so the markdown stays readable
            t_dir = f["truth_direction"].upper()
            other = f["truth_from"] if f["truth_direction"] == "in" else f["truth_to"]
            out.append(f"- `{f['date']}  ${f['amount']:>10,.2f}  {t_dir:<3s}  {other}`")
            if f["verdict"] == "missing_in_store":
                out.append("    └─ **MISSING IN STORE**")
            else:
                for m in f["matched_stored"]:
                    if m["verdict"] != "correct" or f.get("match_count", 0) > 1:
                        flag = m["verdict"].upper()
                        out.append(
                            f"    └─ [{flag}] `{m['stored_label']}` from={m['stored_from']!r} "
                            f"to={m['stored_to']!r}  ({m['stored_key']})"
                        )
        if len(issue_rows) > 60:
            out.append(f"\n  …and {len(issue_rows) - 60} more issue rows")
        out.append("")

    if report["orphans"]:
        out.append(f"**Orphans in store ({len(report['orphans'])}) — stored rows with no matching PDF row:**\n")
        for o in report["orphans"][:30]:
            out.append(f"- `{o['date']}  ${o['amount']:>10,.2f}`  `{o['stored_label']}` "
                       f"name={o['stored_name']!r}  from={o['from_name']!r}  to={o['to_name']!r}")
        if len(report["orphans"]) > 30:
            out.append(f"\n  …and {len(report['orphans']) - 30} more orphans")
        out.append("")

    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("doc", nargs="?", help="Specific doc filename, or omit for all")
    parser.add_argument("--date", default="2026-04-11", help="Audit results subdir")
    args = parser.parse_args()

    audit_dir = AUDIT_ROOT / args.date
    if not audit_dir.exists():
        sys.exit(f"No audit dir at {audit_dir}")

    if args.doc:
        json_files = [audit_dir / (args.doc.replace(".pdf", "") + ".json")]
    else:
        json_files = sorted(p for p in audit_dir.glob("*.json")
                            if not p.name.startswith("_"))

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    all_reports = []
    md_chunks = ["# Re-extraction audit comparison\n",
                 f"_Generated against case `{CASE_ID}`_\n"]

    try:
        for jf in json_files:
            if not jf.exists():
                print(f"[skip] {jf} not found", file=sys.stderr)
                continue
            extracted = json.loads(jf.read_text())
            doc_name = extracted["doc_name"]
            stored = fetch_stored(driver, doc_name)
            report = compare(extracted, stored)
            all_reports.append(report)
            md_chunks.append(render_markdown(report))
    finally:
        driver.close()

    # Write JSON + markdown side-by-side
    out_json = audit_dir / "_audit_summary.json"
    out_md = audit_dir / "_audit_summary.md"
    out_json.write_text(json.dumps(all_reports, indent=2, default=str))
    out_md.write_text("\n".join(md_chunks))

    # Console summary
    print(f"\nWrote {out_json}")
    print(f"Wrote {out_md}\n")
    print("== Per-doc counters ==")
    for r in all_reports:
        c = r["counters"]
        print(f"\n{r['doc_name']}  ({r['account_holder']})")
        for k, v in c.items():
            print(f"  {k:<35s} {v}")


if __name__ == "__main__":
    main()
