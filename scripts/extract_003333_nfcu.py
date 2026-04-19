#!/usr/bin/env python3
"""
Parser for USA-ET-003333.pdf — Navy Federal Credit Union subpoena response for
DIMMPLES INC covering March-October 2021 (8 monthly statements, 30 pages).

Each monthly statement has:
  - Page 1: Summary of your deposit accounts showing Previous / Deposits /
    Withdrawals / Ending / YTD Dividends per account (Business Checking
    7117452727 and Mbr Business Savings 3142115389)
  - Pages 2-3: Transaction details per account
    "Business Checking - 7117452727" / "Mbr Business Savings - 3142115389"
    with "Date Transaction Detail Amount($) Balance($)" column header

Each transaction row has format: MM-DD <desc> <amount> <balance>
Validation: sum of deposits = summary Deposits/Credits per account,
sum of withdrawals = summary Withdrawals/Debits per account.

We determine direction from balance delta — if balance increased, direction=in;
decreased, direction=out.  Then validate per-account sums.
"""
from __future__ import annotations
import json, re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pdfplumber

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
REPO = Path(__file__).resolve().parent.parent
CASE_DIR = REPO / "ingestion" / "data" / CASE_ID
OUT_DIR = REPO / "ingestion" / "data" / "audit_results" / "2026-04-17"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PDF = CASE_DIR / "P3.4" / "USA-ET-003333.pdf"
HOLDER = "DIMMPLES INC"
ACCOUNTS = {
    "7117452727": "Business Checking",
    "3142115389": "Mbr Business Savings",
}


def money(s: str) -> float:
    s = s.replace("$", "").replace(",", "").strip()
    # NFCU prints withdrawals with trailing "-" (e.g., "4,000.00-"); convert to leading minus
    if s.endswith("-"):
        s = "-" + s[:-1]
    return float(s)


DATE_RE = re.compile(r"^(\d{2})-(\d{2})\s+(.+?)\s+(-?[\d,]+\.\d{2}-?)\s+(-?[\d,]+\.\d{2})\s*$")
DATE_BALANCE_ONLY = re.compile(r"^(\d{2})-(\d{2})\s+(Beginning Balance|Ending Balance)\s+(-?[\d,]+\.\d{2})\s*$")


def parse_statement(text: str, period_year: int) -> Dict:
    """Parse one monthly statement text (3 pages concatenated)."""
    # Extract summary per account
    summaries = {}
    # pattern "<AcctType>\n<AcctNum> $X.XX $Y.YY $Z.ZZ $W.WW $V.VV"
    for acct_num, acct_type in ACCOUNTS.items():
        pat = (re.escape(acct_type) + r"\s*\n?\s*" + re.escape(acct_num) +
               r"\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})")
        m = re.search(pat, text)
        if m:
            summaries[acct_num] = {
                "account_type": acct_type,
                "previous": money(m.group(1)),
                "deposits": money(m.group(2)),
                "withdrawals": money(m.group(3)),
                "ending": money(m.group(4)),
            }

    # Extract transactions per account section
    all_txns: List[Dict] = []
    current_acct = None
    current_balance: Optional[float] = None
    beginning_balance_per_acct = {}

    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            continue

        # Detect section start
        for acct_num, acct_type in ACCOUNTS.items():
            if s == f"{acct_type} - {acct_num}" or f"{acct_type} - {acct_num} (Continued" in s:
                current_acct = acct_num
                break

        # Detect beginning balance
        m_bb = DATE_BALANCE_ONLY.match(s)
        if m_bb and current_acct:
            if "Beginning" in m_bb.group(3):
                current_balance = money(m_bb.group(4))
                beginning_balance_per_acct[current_acct] = current_balance
            # else Ending Balance — sanity check but nothing else needed
            continue

        m = DATE_RE.match(s)
        if m and current_acct:
            mm, dd, desc, amt_s, new_bal_s = m.group(1), m.group(2), m.group(3).strip(), m.group(4), m.group(5)
            amt = money(amt_s)
            new_bal = money(new_bal_s)
            if current_balance is None:
                # Missing context — skip (shouldn't happen given proper parsing)
                continue
            delta = round(new_bal - current_balance, 2)
            direction = "in" if delta >= 0 else "out"
            # Sanity: |delta| should equal amt (allow 1¢ tolerance)
            if abs(abs(delta) - amt) > 0.01:
                # Ambiguous — infer direction from description
                u = desc.upper()
                if any(k in u for k in ("DEPOSIT", "CREDIT", "DIVIDEND", "REFUND", "TRANSFER FROM")):
                    direction = "in"
                elif any(k in u for k in ("WITHDRAW", "DEBIT", "PAYMENT", "FEE", "TRANSFER TO")):
                    direction = "out"
            current_balance = new_bal
            all_txns.append({
                "account": current_acct,
                "mm": mm, "dd": dd, "year": period_year,
                "desc": desc,
                "amount": abs(amt),
                "direction": direction,
            })

    return {"summaries": summaries, "transactions": all_txns}


def main():
    with pdfplumber.open(PDF) as pdf:
        pages_text = [(p.extract_text() or "") for p in pdf.pages]

    # Find each 3-page statement block by period marker
    boundaries = []
    for i, t in enumerate(pages_text):
        m = re.search(r"Statement Period\s*\n?\s*(\d{2})/(\d{2})/(\d{2})\s*-\s*(\d{2})/(\d{2})/(\d{2})", t)
        if m:
            # Start marker is "Page 1 of 3"
            if "Page 1 of 3" in t:
                boundaries.append((i, m.group(1), m.group(3)))

    # Merge per statement period (pages 1 of 3, 2 of 3, 3 of 3 all share start)
    print(f"Found {len(boundaries)} monthly statements")

    all_rows: List[Dict] = []
    month_summaries: List[Dict] = []

    for idx, (start_pg, mon, yr) in enumerate(boundaries):
        end_pg = boundaries[idx+1][0] if idx+1 < len(boundaries) else len(pages_text)
        block_text = "\n".join(pages_text[start_pg:end_pg])
        period_year = 2000 + int(yr)
        stmt = parse_statement(block_text, period_year)
        # Validate per-account
        validation = {}
        all_ok = True
        for acct_num, summary in stmt["summaries"].items():
            acct_rows = [r for r in stmt["transactions"] if r["account"] == acct_num]
            ins = round(sum(r["amount"] for r in acct_rows if r["direction"] == "in"), 2)
            outs = round(sum(r["amount"] for r in acct_rows if r["direction"] == "out"), 2)
            dep_ok = abs(ins - summary["deposits"]) < 0.01
            wth_ok = abs(outs - summary["withdrawals"]) < 0.01
            validation[acct_num] = {
                "deposits": {"header": summary["deposits"], "extracted": ins, "ok": dep_ok},
                "withdrawals": {"header": summary["withdrawals"], "extracted": outs, "ok": wth_ok},
            }
            if not (dep_ok and wth_ok):
                all_ok = False

        period_str = f"20{yr}-{mon}-01 / 20{yr}-{mon}-{ {'01':'31','02':'28','03':'31','04':'30','05':'31','06':'30','07':'31','08':'31','09':'30','10':'31','11':'30','12':'31'}[mon] }"

        if not all_ok:
            print(f"✗ statement {idx+1} ({period_str}): validation failed: {validation}")
            continue
        print(f"✓ statement {idx+1} ({period_str}): {len(stmt['transactions']):>3} rows validated")

        month_summaries.append({
            "period_start": f"20{yr}-{mon}",
            "summaries_by_account": stmt["summaries"],
            "validation": validation,
            "row_count": len(stmt["transactions"]),
        })
        all_rows.extend(stmt["transactions"])

    # Build final rows
    channel_of = lambda d: (
        "ATM Cash Deposit" if "Deposit" in d and "Fcp" in d.lower() else
        "ATM Cash Deposit" if d.startswith("Deposit") else
        "Dividend" if "Dividend" in d else
        "Transfer" if "Transfer" in d else
        "Wire" if "Wire" in d or "Fedwire" in d else
        "Other"
    )
    final_rows: List[Dict] = []
    for i, r in enumerate(all_rows, start=1):
        date = f"{r['year']:04d}-{r['mm']}-{r['dd']}"
        acct_type = ACCOUNTS[r["account"]]
        final_rows.append({
            "row_index": i,
            "date": date,
            "description_raw": r["desc"],
            "amount": r["amount"],
            "direction": r["direction"],
            "from_party": r["desc"][:80] if r["direction"] == "in" else HOLDER,
            "to_party": HOLDER if r["direction"] == "in" else r["desc"][:80],
            "channel": channel_of(r["desc"]),
            "confidence": "high",
            "source_page": 1,
            "source_section": f"NFCU {acct_type} {r['account']}",
            "financial_category": "Other",
            "nfcu_account": r["account"],
        })

    dates = [r["date"] for r in final_rows]
    out = {
        "doc_name": "USA-ET-003333.pdf",
        "case_id": CASE_ID,
        "bank": "Navy Federal Credit Union",
        "account_holder": HOLDER,
        "account_number": "7117452727 + 3142115389",
        "account_type": "Business Checking + Mbr Business Savings (subpoena response)",
        "statement_period": {"from": min(dates) if dates else "", "to": max(dates) if dates else ""},
        "header_totals": {
            "statements_in_document": len(boundaries),
            "statements_validated": len(month_summaries),
            "by_month": month_summaries,
        },
        "extraction_model": "pdfplumber per-account section parser with balance-delta direction",
        "extracted_at": "2026-04-17",
        "extraction_method": "per-statement subtotal validation per account",
        "transactions": final_rows,
    }
    (OUT_DIR / "USA-ET-003333.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote USA-ET-003333.json  {len(final_rows)} txns across {len(month_summaries)}/{len(boundaries)} months")


if __name__ == "__main__":
    main()
