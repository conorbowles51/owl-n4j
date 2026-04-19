#!/usr/bin/env python3
"""
Parser for the batch of 37 "check-image structured" PDFs located under P3.8
(Eric Tataw's Capital One 360 subpoena response).  Each PDF has 2 pages:
  page 1:  ProcDate YYYY/MM/DD, CheckAmt N.NN, SerialNum 0 (deposit ticket)
  page 2:  ProcDate YYYY/MM/DD, CheckAmt N.NN, SerialNum <real>

The two pages represent the SAME transaction (front and back of one check).
Each doc becomes ONE incoming check deposit into Eric Tataw's Capital One 360.

Validation: both pages must have identical ProcDate and CheckAmt. If they
differ the doc is skipped.
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Dict, List, Optional
import pdfplumber

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
REPO = Path(__file__).resolve().parent.parent
CASE_DIR = REPO / "ingestion" / "data" / CASE_ID
OUT_DIR = REPO / "ingestion" / "data" / "audit_results" / "2026-04-17"

HOLDER = "Eric Tataw"
ACCT = "36065389299"

DOC_IDS = """USA-ET-004518 USA-ET-004491 USA-ET-004529 USA-ET-004475 USA-ET-004533
USA-ET-004630 USA-ET-004596 USA-ET-004567 USA-ET-004429 USA-ET-004506
USA-ET-004499 USA-ET-004458 USA-ET-004514 USA-ET-004481 USA-ET-004497
USA-ET-004483 USA-ET-004579 USA-ET-004444 USA-ET-004485 USA-ET-004493
USA-ET-004452 USA-ET-004554 USA-ET-004556 USA-ET-004569 USA-ET-004520
USA-ET-004508 USA-ET-004634 USA-ET-004571 USA-ET-004565 USA-ET-004473
USA-ET-004467 USA-ET-004510 USA-ET-004460 USA-ET-004516 USA-ET-004535
USA-ET-004446 USA-ET-004545""".split()

DATE_RE = re.compile(r"ProcDate:\s+(\d{4})/(\d{2})/(\d{2})")
AMT_RE = re.compile(r"CheckAmt:\s+([\d,]+\.\d{2})")
SER_RE = re.compile(r"SerialNum:\s+(\d+)")


def parse_doc(doc_id: str) -> Optional[Dict]:
    name = doc_id + ".pdf"
    hits = list(CASE_DIR.rglob(name))
    if not hits:
        print(f"✗ {name}: NOT FOUND")
        return None
    p = hits[0]
    with pdfplumber.open(p) as pdf:
        page_data = []
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            dm = DATE_RE.search(t)
            am = AMT_RE.search(t)
            sm = SER_RE.search(t)
            if not (dm and am):
                continue
            page_data.append({
                "date": f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}",
                "amount": float(am.group(1).replace(",", "")),
                "serial": sm.group(1) if sm else "0",
            })

    if not page_data:
        print(f"✗ {doc_id}: no ProcDate/CheckAmt found")
        return None

    # Validate: all pages must agree on date + amount
    ref_date = page_data[0]["date"]
    ref_amt = page_data[0]["amount"]
    for pd in page_data[1:]:
        if pd["date"] != ref_date or abs(pd["amount"] - ref_amt) > 0.005:
            print(f"✗ {doc_id}: page mismatch {pd} vs {page_data[0]}")
            return None

    # Pick the non-zero serial (the actual check serial number)
    serials = [pd["serial"] for pd in page_data if pd["serial"] != "0"]
    serial = serials[0] if serials else "0"

    row = {
        "row_index": 1,
        "date": ref_date,
        "description_raw": f"Check deposit — check serial {serial}" if serial != "0" else "Check deposit (no serial)",
        "amount": ref_amt,
        "direction": "in",
        "from_party": f"Check #{serial}" if serial != "0" else "Check deposit",
        "to_party": HOLDER,
        "channel": "Check Deposit",
        "confidence": "medium",  # direction inferred, not stated on doc
        "source_page": 1,
        "source_section": "Check image (subpoena structured metadata)",
        "financial_category": "Other",
        "reference": serial if serial != "0" else None,
    }
    return {
        "doc_name": name,
        "case_id": CASE_ID,
        "bank": "Capital One 360 (subpoena response)",
        "account_holder": HOLDER,
        "account_number": ACCT,
        "account_type": "360 Checking",
        "statement_period": {"from": ref_date, "to": ref_date},
        "header_totals": {
            "notes": f"1 check deposit, amount ${ref_amt:.2f}, serial {serial}",
            "pages_cross_checked": len(page_data),
        },
        "extraction_model": "pdfplumber structured metadata parser",
        "extracted_at": "2026-04-17",
        "extraction_method": "ProcDate/CheckAmt/SerialNum regex; page 1 vs page 2 consistency check",
        "transactions": [row],
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    total_amt = 0.0
    for doc_id in DOC_IDS:
        obj = parse_doc(doc_id)
        if obj is None:
            continue
        (OUT_DIR / (doc_id + ".json")).write_text(json.dumps(obj, indent=2))
        ok += 1
        r = obj["transactions"][0]
        total_amt += r["amount"]
        print(f"✓ {doc_id}  {r['date']}  ${r['amount']:>8.2f}  serial={r['reference']}")
    print(f"\n== {ok}/{len(DOC_IDS)} docs, total ${total_amt:,.2f} ==")


if __name__ == "__main__":
    main()
