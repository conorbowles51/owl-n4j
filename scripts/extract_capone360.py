#!/usr/bin/env python3
"""
Parser for Capital One 360 savings statements (USA-ET-004454/4462/4487).
Format: one transaction per "Month DD ... Credit +/Debit - $amt $balance" line,
possibly wrapped across 2-3 physical lines.
"""
import json, re
from pathlib import Path
from datetime import datetime
import pdfplumber

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
CASE = Path(f"/home/conorbowles51/app_v2/ingestion/data/{CASE_ID}")
OUT = Path("/home/conorbowles51/app_v2/ingestion/data/audit_results/2026-04-17")

MONTHS = {m: i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], start=1)}

DOCS = [
    ("P3.8/USA-ET-004454.pdf", 2019, 4),
    ("P3.8/USA-ET-004462.pdf", 2019, 5),
    ("P3.8/USA-ET-004487.pdf", 2019, 8),
]

# Date-anchor regex (matches any row that has "Mon DD ... Credit/Debit ± $amt $balance"
# on a single line, possibly with an empty or filled description between the date
# and the Credit/Debit marker).
LINE_RE = re.compile(
    r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+'
    r'(.*?)(Credit|Debit)\s+[-+]\s*\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$'
)


def parse_doc(rel: str, year_hint: int, expected_month: int):
    path = CASE / rel
    if not path.exists():
        return None
    with pdfplumber.open(path) as pdf:
        full_text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    # Statement period
    per = re.search(r'(\w+)\s+(\d+)\s*-\s*(\w+)\s+(\d+),?\s*(\d{4})', full_text)
    if per:
        sm, sd = per.group(1)[:3], int(per.group(2))
        em, ed = per.group(3)[:3], int(per.group(4))
        yr = int(per.group(5))
    else:
        yr, sm, sd, em, ed = year_hint, list(MONTHS.keys())[expected_month-1], 1, list(MONTHS.keys())[expected_month-1], 28

    acct_m = re.search(r'360 (?:Checking|Savings)\.+(\d+)', full_text) or re.search(r'360 (?:Checking|Savings)\s*-\s*(\d+)', full_text)
    acct = acct_m.group(1) if acct_m else "?"

    lines = [l for l in full_text.split("\n")]
    trimmed = [l.strip() for l in lines]

    txns = []
    ri = 0

    # Walk lines. Each line that matches LINE_RE is a txn "anchor".  If the
    # description portion inside the anchor is empty/short, we stitch in the
    # prev and next lines (wrapped-description case on Capital One 360).
    date_start_any = re.compile(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}')
    for i, line in enumerate(trimmed):
        m = LINE_RE.match(line)
        if not m:
            continue
        month = MONTHS[m.group(1)]
        day = int(m.group(2))
        inline_desc = m.group(3).strip()
        kind = m.group(4)
        amt = float(m.group(5).replace(",", ""))

        if len(inline_desc) < 4:
            prev_line = trimmed[i-1] if i > 0 else ""
            next_line = trimmed[i+1] if i+1 < len(trimmed) else ""
            if date_start_any.match(prev_line) or LINE_RE.match(prev_line):
                prev_line = ""
            if date_start_any.match(next_line) or LINE_RE.match(next_line):
                next_line = ""
            desc = (prev_line + " " + next_line).strip()
        else:
            desc = inline_desc

        direction = "in" if kind == "Credit" else "out"
        ri += 1
        txns.append({
            "row_index": ri,
            "date": f"{yr:04d}-{month:02d}-{day:02d}",
            "description_raw": desc,
            "amount": amt,
            "direction": direction,
            "from_party": desc[:60] if direction == "in" else "Eric Tataw",
            "to_party": "Eric Tataw" if direction == "in" else desc[:60],
            "channel": (
                "ATM Cash Deposit" if "ATM" in desc and "Deposit" in desc else
                "ATM Cash Withdrawal" if "ATM" in desc and ("Withdrawal" in desc or "WITHDR" in desc) else
                "Debit Card" if "Debit Card" in desc else
                "Interest" if "Interest" in desc else
                "Money received" if desc.startswith("Money received") or "received from" in desc else
                "Transfer" if "Withdrawal" in desc or "MOBILE PMT" in desc or "Money sent" in desc else
                "Other"
            ),
            "confidence": "high",
            "source_page": 2,
            "source_section": "Capital One 360 monthly",
            "financial_category": "Other",
        })

    # Header totals
    summary = {
        "interest_earned": 0,
        "opening": None,
        "closing": None,
    }
    m = re.search(r'INTEREST EARNED[\s\S]{0,200}?\$([\d,]+\.\d{2})', full_text)

    doc_name = Path(rel).name
    return {
        "doc_name": doc_name,
        "case_id": CASE_ID,
        "bank": "Capital One 360",
        "account_holder": "Eric Tataw",
        "account_number": acct,
        "account_type": "360 Checking",
        "statement_period": {
            "from": f"{yr}-{MONTHS[sm]:02d}-{sd:02d}",
            "to":   f"{yr}-{MONTHS[em]:02d}-{ed:02d}",
        },
        "header_totals": {"notes": f"{len(txns)} txns parsed"},
        "extraction_model": "pdfplumber line-merge + regex",
        "extracted_at": "2026-04-17",
        "extraction_method": "Capital One 360 format line-based parser",
        "transactions": txns,
    }


def main():
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", help="text file of USA-ET-NNNNNN.pdf names")
    ap.add_argument("--validate-balance", action="store_true",
                    help="require open+deposits-withdrawals=close to pass")
    args = ap.parse_args()

    if args.targets:
        names = [ln.strip() for ln in Path(args.targets).read_text().splitlines() if ln.strip()]
        # Resolve relative paths
        targets = []
        for name in names:
            hits = list(CASE.rglob(name))
            if not hits:
                print(f"✗ {name}  NOT FOUND")
                continue
            rel = str(hits[0].relative_to(CASE))
            targets.append((rel, 0, 0))
    else:
        targets = DOCS

    OUT.mkdir(parents=True, exist_ok=True)
    ok = 0
    for rel, yr, mo in targets:
        out = parse_doc(rel, yr, mo)
        if out is None:
            print(f"SKIP {rel}")
            continue
        n = len(out["transactions"])
        ins = sum(t["amount"] for t in out["transactions"] if t["direction"] == "in")
        outs = sum(t["amount"] for t in out["transactions"] if t["direction"] == "out")

        # Validate balance equation
        if args.validate_balance:
            import pdfplumber as pp, re as rr
            with pp.open(CASE / rel) as pdf:
                full = "\n".join(p.extract_text() or "" for p in pdf.pages)
            m_open = rr.search(r'(\w+ \d+)\s+Opening Balance\s+\$([\d,]+\.\d{2})', full)
            m_close = rr.search(r'(\w+ \d+)\s+Closing Balance\s+\$([\d,]+\.\d{2})', full)
            if not (m_open and m_close):
                print(f"✗ {rel}  no Opening/Closing balance found — CANNOT VALIDATE")
                continue
            open_bal = float(m_open.group(2).replace(",", ""))
            close_bal = float(m_close.group(2).replace(",", ""))
            expected_close = round(open_bal + ins - outs, 2)
            if abs(expected_close - close_bal) >= 0.01:
                print(f"✗ {rel}  balance mismatch: open={open_bal} + in={ins} - out={outs} = {expected_close} ≠ close={close_bal}")
                continue

        (OUT / (out["doc_name"].replace(".pdf", ".json"))).write_text(json.dumps(out, indent=2))
        ok += 1
        print(f"✓ {out['doc_name']:<24s}  {n:>3} txns  in=${ins:,.2f}  out=${outs:,.2f}  {out['statement_period']['from']}–{out['statement_period']['to']}")
    print(f"\n== {ok}/{len(targets)} passed ==")

if __name__ == "__main__":
    main()
