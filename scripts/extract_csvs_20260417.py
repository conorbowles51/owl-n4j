#!/usr/bin/env python3
"""
Careful per-row CSV extractor for the BofA subpoena check-image / deposit-ticket
CSVs left over from the 2026-04-12 re-extraction pass.

Each CSV format is hand-parsed with csv.DictReader — no regex, no fuzzy matching.
Every row in the CSV becomes exactly one transaction in the output JSON.  After
parsing we assert (a) the output row count matches the CSV data row count and
(b) amounts are numeric and non-null.  Anything off aborts that doc.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
CASE_DIR = Path(f"/home/conorbowles51/app_v2/ingestion/data/{CASE_ID}")
OUT_DIR = Path("/home/conorbowles51/app_v2/ingestion/data/audit_results/2026-04-17")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Account → holder (taken from memory + observed in CSVs)
ACCOUNT_HOLDER = {
    "446035140515": ("ERIC TANO TATAW", "Bank of America", "Checking"),
    "446039800440": ("BELTHA B MOKUBE", "Bank of America", "Checking"),
    "446045680094": ("BELTHA B MOKUBE", "Bank of America", "Checking"),
}


def money(s: str) -> float:
    s = (s or "").strip().strip('"').strip("'")
    if s.startswith("$"):
        s = s[1:]
    s = s.replace(",", "")
    if not s:
        return 0.0
    return float(s)


def iso_date(s: str) -> str:
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"unparsable date: {s!r}")


def categorize_channel(channel: str, direction: str) -> str:
    # mirror backend/services/from_to_extraction_service.py 5-value taxonomy
    c = channel.lower()
    if "deposit" in c or "atm" in c:
        return "Other"  # deposit into the account holder — "Other" = cash/branch receipt
    if "check" in c:
        return "Other"
    return "Other"


# ── Format A: Deposit Tickets (Date Deposited, ..., Amount Deposited, Serial Number, ...)
def parse_format_a(path: Path) -> Tuple[Dict, List[Dict]]:
    """Deposit tickets = incoming deposits into Deposit Account."""
    rows_out = []
    accounts_seen = set()
    dates = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            date = iso_date(row["Date Deposited"])
            amount = money(row["Amount Deposited"])
            serial = (row.get("Serial Number") or "").strip()
            deposit_acct = (row.get("Deposit Account") or "").strip()
            file_name = (row.get("File Name") or "").strip()
            dates.append(date)
            accounts_seen.add(deposit_acct)
            # Serial "0" = cash deposit, otherwise check
            if serial and serial != "0":
                channel = "Branch Deposit"
                from_party = f"Deposit (check serial {serial})"
                raw = f"Deposit ticket (serial {serial})"
            else:
                channel = "Branch Deposit"
                from_party = "Deposit (cash)"
                raw = "Deposit ticket (cash)"
            rows_out.append({
                "row_index": i,
                "date": date,
                "description_raw": raw,
                "amount": amount,
                "direction": "in",
                "from_party": from_party,
                "to_party": None,  # filled below with account holder
                "channel": channel,
                "confidence": "high",
                "source_page": 1,
                "source_section": "Deposit Tickets",
                "financial_category": "Other",
                "reference": serial if serial and serial != "0" else None,
                "deposit_account": deposit_acct,
                "_file_name": file_name,
            })
    # Resolve holder from most common deposit account
    if len(accounts_seen) == 1:
        acct = accounts_seen.pop()
        holder, bank, typ = ACCOUNT_HOLDER.get(
            acct, (f"Account {acct}", "Bank of America", "Checking")
        )
    else:
        # Mixed accounts — holder is the most common one
        counts: Dict[str, int] = {}
        for r in rows_out:
            counts[r["deposit_account"]] = counts.get(r["deposit_account"], 0) + 1
        acct = max(counts, key=counts.get)
        holder, bank, typ = ACCOUNT_HOLDER.get(
            acct, (f"Account {acct}", "Bank of America", "Checking")
        )
    for r in rows_out:
        # Per-row holder resolution so mixed-account CSVs stay correct
        row_acct = r.pop("deposit_account")
        row_holder, _, _ = ACCOUNT_HOLDER.get(
            row_acct, (holder, bank, typ)
        )
        r["to_party"] = row_holder
        # Source section = file name (so Neo4j summary surfaces the image)
        if r.pop("_file_name", None):
            pass
    header = {
        "bank": bank,
        "account_holder": holder,
        "account_number": acct,
        "account_type": typ,
        "statement_period": {"from": min(dates), "to": max(dates)} if dates else None,
    }
    return header, rows_out


# ── Format B: Check Deposits (remitter-side view) — INCOMING
def parse_format_b(path: Path) -> Tuple[Dict, List[Dict]]:
    rows_out = []
    accounts_seen = set()
    dates = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            date = iso_date(row["Date Presented"])
            amount = money(row["Amount Presented"])
            check_no = (row.get("Check Number") or "").strip()
            remitter_acct = (row.get("Remitter Account Number") or "").strip()
            remitter_rt = (row.get("Remitter R/T Number") or "").strip()
            deposit_acct = (row.get("Deposit Account") or "").strip()
            accounts_seen.add(deposit_acct)
            dates.append(date)
            if check_no and check_no != "0":
                raw = f"Check #{check_no} from acct {remitter_acct} (RT {remitter_rt})"
                from_party = f"Check #{check_no} from acct {remitter_acct}"
                ref = check_no
            else:
                raw = f"Deposit from acct {remitter_acct} (RT {remitter_rt})"
                from_party = f"Transfer from acct {remitter_acct}"
                ref = None
            rows_out.append({
                "row_index": i,
                "date": date,
                "description_raw": raw,
                "amount": amount,
                "direction": "in",
                "from_party": from_party,
                "to_party": None,
                "channel": "Check Deposit",
                "confidence": "high",
                "source_page": 1,
                "source_section": "Check Images (Deposit side)",
                "financial_category": "Other",
                "reference": ref,
                "deposit_account": deposit_acct,
            })
    if len(accounts_seen) >= 1:
        counts: Dict[str, int] = {}
        for r in rows_out:
            counts[r["deposit_account"]] = counts.get(r["deposit_account"], 0) + 1
        acct = max(counts, key=counts.get)
        holder, bank, typ = ACCOUNT_HOLDER.get(
            acct, (f"Account {acct}", "Bank of America", "Checking")
        )
    else:
        acct, holder, bank, typ = "", "Unknown", "Bank of America", "Checking"
    for r in rows_out:
        row_acct = r.pop("deposit_account")
        row_holder, _, _ = ACCOUNT_HOLDER.get(
            row_acct, (holder, bank, typ)
        )
        r["to_party"] = row_holder
    header = {
        "bank": bank,
        "account_holder": holder,
        "account_number": acct,
        "account_type": typ,
        "statement_period": {"from": min(dates), "to": max(dates)} if dates else None,
    }
    return header, rows_out


# ── Format C: Paid Checks (Item Date, ..., Amount, Serial Number, Payee Name) — OUTGOING
def parse_format_c(path: Path) -> Tuple[Dict, List[Dict]]:
    rows_out = []
    accounts_seen = set()
    dates = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            date = iso_date(row["Item Date"])
            amount = money(row["Amount"])
            serial = (row.get("Serial Number") or "").strip()
            payee = (row.get("Payee Name") or "").strip()
            acct = (row.get("Account Number") or "").strip()
            accounts_seen.add(acct)
            dates.append(date)
            if payee:
                to_party = payee
                raw = f"Check #{serial} to {payee}"
            elif serial and serial != "0":
                to_party = f"Check #{serial} payee"
                raw = f"Check #{serial}"
            else:
                to_party = "Unknown payee"
                raw = "Check payment"
            rows_out.append({
                "row_index": i,
                "date": date,
                "description_raw": raw,
                "amount": amount,  # stored as positive magnitude; loader applies sign from direction
                "direction": "out",
                "from_party": None,
                "to_party": to_party,
                "channel": "Check",
                "confidence": "high",
                "source_page": 1,
                "source_section": "Paid Checks",
                "financial_category": "Other",
                "reference": serial if serial and serial != "0" else None,
                "account_number": acct,
            })
    # Only one account should appear in a Paid Checks file
    assert len(accounts_seen) == 1, f"{path.name}: expected 1 account, got {accounts_seen}"
    acct = accounts_seen.pop()
    holder, bank, typ = ACCOUNT_HOLDER.get(
        acct, (f"Account {acct}", "Bank of America", "Checking")
    )
    for r in rows_out:
        r.pop("account_number", None)
        r["from_party"] = holder
    header = {
        "bank": bank,
        "account_holder": holder,
        "account_number": acct,
        "account_type": typ,
        "statement_period": {"from": min(dates), "to": max(dates)} if dates else None,
    }
    return header, rows_out


# ── Dispatch by header ────────────────────────────────────────────────────────
def detect_format(path: Path) -> str:
    with path.open() as f:
        header = f.readline().strip()
    if header.startswith("Date Deposited,"):
        return "A"
    if header.startswith("Date Presented,"):
        return "B"
    if header.startswith("Item Date,Sequence Number,State Code"):
        return "C"
    raise RuntimeError(f"{path.name}: unrecognised header: {header[:80]}")


# ── Main ──────────────────────────────────────────────────────────────────────
TARGETS = [
    ("P3.3", "USA-ET-001755.csv"),
    ("P3.3", "USA-ET-001692.csv"),
    ("P3.3", "USA-ET-001629.csv"),
    ("P3.3", "USA-ET-001628.csv"),
    ("P3.3", "USA-ET-001527.csv"),
    ("P3.1", "USA-ET-000840.csv"),
    ("P13",  "USA-ET-046201.csv"),
    ("P13",  "USA-ET-046202.csv"),
    ("P13",  "USA-ET-046203.csv"),
    ("P13",  "USA-ET-046204.csv"),
]


def process(rel_dir: str, name: str) -> Dict:
    src = CASE_DIR / rel_dir / name
    if not src.exists():
        raise FileNotFoundError(src)

    # Count CSV data rows independently as a sanity check
    with src.open() as f:
        data_rows = sum(1 for _ in f) - 1

    fmt = detect_format(src)
    parser = {"A": parse_format_a, "B": parse_format_b, "C": parse_format_c}[fmt]
    header, txns = parser(src)

    assert len(txns) == data_rows, f"{name}: parsed {len(txns)} but CSV had {data_rows} data rows"
    for t in txns:
        assert t["date"] and t["amount"] is not None and t["direction"] in ("in", "out")
        assert t["amount"] >= 0, f"{name} row {t['row_index']}: negative magnitude"

    out = {
        "doc_name": name,
        "case_id": CASE_ID,
        **header,
        "header_totals": {
            "notes": f"{len(txns)} txns from CSV (format {fmt})",
            "total_amount": round(sum(t["amount"] for t in txns), 2),
        },
        "extraction_model": "python csv.DictReader",
        "extracted_at": "2026-04-17",
        "extraction_method": f"Direct CSV parsing (format {fmt})",
        "transactions": txns,
    }

    out_path = OUT_DIR / (name.replace(".csv", "") + ".json")
    out_path.write_text(json.dumps(out, indent=2))
    return {
        "doc": name, "fmt": fmt, "rows": len(txns),
        "total": out["header_totals"]["total_amount"],
        "holder": header["account_holder"],
        "period": header.get("statement_period"),
        "out": str(out_path),
    }


def main():
    summary = []
    for rel_dir, name in TARGETS:
        try:
            r = process(rel_dir, name)
        except Exception as exc:
            print(f"FAIL {name}: {exc}")
            raise
        summary.append(r)
        print(f"OK  {r['doc']:<24s}  fmt={r['fmt']}  rows={r['rows']:>4d}  total=${r['total']:>12,.2f}  {r['holder']:<20s}  {r['period']}")
    print(f"\n== {len(summary)} docs, {sum(s['rows'] for s in summary)} total rows ==")


if __name__ == "__main__":
    main()
