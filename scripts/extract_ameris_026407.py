#!/usr/bin/env python3
"""
Pdfplumber-based parser for USA-ET-026407.pdf — Lee Kameron's Ameris Bank
Free Checking statements. 130 pages, 12 monthly statements (Dec 2020 - Nov 2021).

Each statement has:
  - Page 1 summary with "Beginning balance", "Total additions", "Total subtractions",
    "Ending balance"
  - Transaction rows: MM-DD #<Type> <amount> with wrapped descriptive lines
  - Amount appears on the date line; additions are positive, subtractions are
    negative (printed with leading "-")

Validation: per-month, sum(additions) == Total additions, sum(subtractions) ==
|Total subtractions|. The PDF stacks 12 monthly statements end-to-end so each
is validated independently.

Output: one JSON per month (USA-ET-026407_<year>-<month>.pdf as doc name, but
audit_doc field set to USA-ET-026407.pdf so legacy-v1 lookups still match).
Actually, since Neo4j only has one Document node for USA-ET-026407.pdf, we
concatenate all months into ONE JSON keyed on the doc, with validation metadata
per month embedded in header_totals.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
REPO = Path(__file__).resolve().parent.parent
CASE_DIR = REPO / "ingestion" / "data" / CASE_ID
OUT_DIR = REPO / "ingestion" / "data" / "audit_results" / "2026-04-17"

PDF = CASE_DIR / "P9.1" / "USA-ET-026407.pdf"

HOLDER = "LEE KAMERON"
ACCT = "1030224644"

MONTH_NUM = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}


def money(s: str) -> float:
    s = s.replace("$", "").replace(",", "").strip()
    # Ameris writes ".01" for 1-cent values; normalise leading "." → "0."
    if s.startswith("."):
        s = "0" + s
    elif s.startswith("-.") or s.startswith("+."):
        s = s[0] + "0" + s[1:]
    return float(s)


def parse_one_statement(pages_text: List[str], start_page_idx: int,
                         end_page_idx: int, prev_date_str: str,
                         this_date_str: str) -> Tuple[Optional[Dict], List[str]]:
    """Return (statement_dict, warnings).  statement_dict is None if validation fails."""
    warnings: List[str] = []
    text = "\n".join(pages_text[start_page_idx:end_page_idx])

    # Extract summary totals (from page 1 of the statement)
    p1 = pages_text[start_page_idx]
    m_beg = re.search(r"Beginning balance\s+\$([\d,.\-]+)", p1)
    m_add = re.search(r"Total additions\s+\$([\d,.\-]+)", p1)
    m_sub = re.search(r"Total subtractions\s+\$?-?([\d,.\-]+)", p1)
    m_end_pair = re.search(r"Ending [Bb]alance\s+\$?([\d,.\-]+)", p1)

    if not (m_add and m_sub):
        return None, ["could not find Total additions / subtractions"]

    beg = money(m_beg.group(1)) if m_beg else 0.0
    total_add = money(m_add.group(1))
    total_sub = money(m_sub.group(1))
    end_bal = money(m_end_pair.group(1)) if m_end_pair else None

    # Statement period
    try:
        sd = datetime.strptime(prev_date_str, "%B %d, %Y").strftime("%Y-%m-%d")
        ed = datetime.strptime(this_date_str, "%B %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        sd = ed = ""
    period_year = int(ed[:4]) if ed else datetime.now().year

    # First: pull enclosure rows (paid checks) from the summary block.
    # Format: "Number Date Amount [Number Date Amount]\n<N> <MM-DD> <amt> [<N> <MM-DD> <amt>]"
    # Each such row is a paid check (direction=out).
    # The block sits between "Number Date Amount" and the next "Date Description" header.
    enc_rows: List[Dict] = []
    encl_block_re = re.compile(
        r"Number Date Amount(?:\s+Number Date Amount)?\s*\n(.*?)(?=\n(?:Date Description|Daily balances|Total))",
        re.DOTALL,
    )
    m_encl = encl_block_re.search(p1)
    if m_encl:
        enc_row_re = re.compile(r"(\d+)\s+(\d{2})-(\d{2})\s+(-?\$?[\d,]+\.\d{2})")
        for m in enc_row_re.finditer(m_encl.group(1)):
            chknum, mm, dd, amt_s = m.group(1), m.group(2), m.group(3), m.group(4)
            amt = abs(money(amt_s))
            enc_rows.append({
                "mm": mm, "dd": dd,
                "desc": f"Check paid (check# {chknum})" if chknum != "0" else "Check paid (no check number)",
                "amount": amt, "direction": "out",
            })

    # Extract transactions.  Each row begins "MM-DD #<Type> <amount>" on a line.
    # Subsequent non-dated lines are description continuation.
    lines = text.split("\n")
    rows: List[Dict] = list(enc_rows)
    current: Optional[Dict] = None
    # Amount = either N.DD or .DD (where Ameris writes "+.01" or ".01" for 1-cent entries)
    AMT = r"(-?\$?(?:[\d,]+\.\d{2}|\.\d{2}))"
    DATE_RE = re.compile(r"^(\d{2})-(\d{2})\s+(.+?)\s+" + AMT + r"\s*$")
    DATE_DEPOSIT_RE = re.compile(r"^(\d{2})-(\d{2})\s+(Deposit)\s+" + AMT + r"\s*$")

    in_txn_section = False  # flip once we see "Date Description Additions Subtractions"
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        # STOP at Daily balances / Total balance sections
        if s.startswith("Daily balances") or s.startswith("Total for Total prior") or s.startswith("Total Overdraft"):
            break
        # Skip boilerplate
        if any(tok in s for tok in (
            "Page ", "Ameris Bank", "P.O. Box", "Customer Service",
            "Direct inquiries", "FOREST PARK GA", "LEE KAMERON",
            "Statement of Account", "Last statement:", "This statement:",
            "Total days in statement", "USA-ET-", "Free Checking",
            "Account number", "Summary of Account Balance",
            "Number Date Amount", "Enclosures",
            "Summary of Account", "Account Number Ending",
            "Low balance", "Average balance", "Beginning balance",
            "Total additions", "Total subtractions",
        )):
            continue
        # Anchor: only parse rows once we're past the txn section header
        if s.startswith("Date Description"):
            in_txn_section = True
            continue
        if not in_txn_section:
            continue
        # Match date row
        m = DATE_RE.match(s) or DATE_DEPOSIT_RE.match(s)
        if m:
            mm, dd, desc, amt_s = m.group(1), m.group(2), m.group(3).strip(), m.group(4)
            amt = money(amt_s)
            direction = "in" if amt >= 0 else "out"
            current = {
                "mm": mm, "dd": dd, "desc": desc,
                "amount": abs(amt), "direction": direction,
            }
            rows.append(current)
        else:
            if current is not None:
                # Continuation line (extra detail) — append to description
                current["desc"] = (current["desc"] + " " + s).strip()

    # Filter out rows whose description indicates summary (shouldn't happen with our filters)
    final: List[Dict] = []
    for r in rows:
        if not r["desc"]:
            continue
        year_eff = period_year
        # If month is before the "this statement" month, wrap back
        this_month = int(ed[5:7]) if ed else period_year
        if int(r["mm"]) > this_month:
            year_eff -= 1
        final.append({
            "date": f"{year_eff:04d}-{int(r['mm']):02d}-{int(r['dd']):02d}",
            "description_raw": r["desc"],
            "amount": r["amount"],
            "direction": r["direction"],
        })

    # Validate
    ins = round(sum(t["amount"] for t in final if t["direction"] == "in"), 2)
    outs = round(sum(t["amount"] for t in final if t["direction"] == "out"), 2)
    validation = {
        "additions": {"header": total_add, "extracted": ins, "ok": abs(ins - total_add) < 0.01},
        "subtractions": {"header": total_sub, "extracted": outs, "ok": abs(outs - total_sub) < 0.01},
    }
    if not (validation["additions"]["ok"] and validation["subtractions"]["ok"]):
        return None, [f"SUBTOTAL MISMATCH for {this_date_str}: {validation}"]

    return {
        "period": {"from": sd, "to": ed},
        "totals": {
            "beginning_balance": beg,
            "additions": total_add,
            "subtractions": total_sub,
            "ending_balance": end_bal,
        },
        "validation": validation,
        "rows": final,
    }, warnings


def main():
    assert PDF.exists()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(PDF) as pdf:
        pages_text = [(p.extract_text() or "") for p in pdf.pages]

    # Find statement boundaries (start pages)
    boundaries = []
    for i, t in enumerate(pages_text):
        m = re.search(r"Last statement:\s+(\w+ \d+, \d{4})\s*\n\s*This statement:\s+(\w+ \d+, \d{4})", t)
        if m:
            boundaries.append((i, m.group(1), m.group(2)))
    n = len(boundaries)
    print(f"Found {n} statement boundaries")

    all_rows: List[Dict] = []
    month_summaries: List[Dict] = []
    warnings: List[str] = []

    failed_months: List[Dict] = []
    for idx in range(n):
        start = boundaries[idx][0]
        end = boundaries[idx+1][0] if idx+1 < n else len(pages_text)
        prev_d = boundaries[idx][1]
        this_d = boundaries[idx][2]
        stmt, warns = parse_one_statement(pages_text, start, end, prev_d, this_d)
        if stmt is None:
            warnings.extend(warns)
            print(f"✗ statement {idx+1} ({prev_d} → {this_d}): {warns[-1][:200] if warns else '?'}")
            failed_months.append({"statement_number": idx+1, "period": f"{prev_d} → {this_d}", "reason": warns[-1][:300] if warns else "unknown"})
            continue
        print(f"✓ statement {idx+1} ({stmt['period']['from']} → {stmt['period']['to']}): "
              f"{len(stmt['rows']):>3} rows  add=${stmt['totals']['additions']:>10,.2f}  "
              f"sub=${stmt['totals']['subtractions']:>10,.2f}")
        month_summaries.append({
            "statement_period": stmt["period"],
            "totals": stmt["totals"],
            "validation": stmt["validation"],
            "row_count": len(stmt["rows"]),
        })
        for r in stmt["rows"]:
            all_rows.append(r)

    if failed_months:
        print(f"\n⚠ {len(failed_months)} month(s) failed validation and were NOT included:")
        for f in failed_months:
            print(f"  - stmt {f['statement_number']} ({f['period']}): {f['reason']}")

    # Assign row_index + finalise rows
    channel_of = lambda d: (
        "Zelle" if "Zelle" in d else
        "Check Card" if "Check Card" in d or "MERCHANT PURCHASE" in d else
        "ATM Deposit" if "ATM Deposit" in d or "Deposit" == d.split()[0] else
        "Cash App" if "CASH APP" in d.upper() or "Square Inc" in d else
        "PayPal" if "PAYPAL" in d.upper() else
        "Preauthorized" if "Preauthorized" in d else
        "Transfer" if "Electronic Transfer" in d else
        "Service Fee" if any(k in d.upper() for k in ("FEE", "OVERDRAFT")) else
        "Check" if re.match(r"^Check\s*\d+", d) else
        "Other"
    )
    final_rows: List[Dict] = []
    for i, r in enumerate(all_rows, start=1):
        desc = r["description_raw"]
        final_rows.append({
            "row_index": i,
            "date": r["date"],
            "description_raw": desc,
            "amount": r["amount"],
            "direction": r["direction"],
            "from_party": desc[:80] if r["direction"] == "in" else HOLDER,
            "to_party": HOLDER if r["direction"] == "in" else desc[:80],
            "channel": channel_of(desc),
            "confidence": "high",
            "source_page": 1,
            "source_section": "Ameris monthly statement",
            "financial_category": "Other",
        })

    all_dates = [r["date"] for r in final_rows]
    out = {
        "doc_name": "USA-ET-026407.pdf",
        "case_id": CASE_ID,
        "bank": "Ameris Bank",
        "account_holder": HOLDER,
        "account_number": ACCT,
        "account_type": "Free Checking",
        "statement_period": {
            "from": min(all_dates) if all_dates else "",
            "to": max(all_dates) if all_dates else "",
        },
        "header_totals": {
            "statements_in_document": n,
            "total_additions": round(sum(m["totals"]["additions"] for m in month_summaries), 2),
            "total_subtractions": round(sum(m["totals"]["subtractions"] for m in month_summaries), 2),
            "by_month": month_summaries,
        },
        "extraction_model": "pdfplumber line-based multi-statement parser",
        "extracted_at": "2026-04-17",
        "extraction_method": "per-month parsing with Total additions/subtractions validation",
        "transactions": final_rows,
    }
    out["header_totals"]["failed_months"] = failed_months
    (OUT_DIR / "USA-ET-026407.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote USA-ET-026407.json  {len(final_rows)} txns across {len(month_summaries)}/{n} months  "
          f"total_add=${out['header_totals']['total_additions']:,}  total_sub=${out['header_totals']['total_subtractions']:,}")
    if failed_months:
        print(f"({len(failed_months)} month(s) excluded — see header_totals.failed_months)")


if __name__ == "__main__":
    main()
