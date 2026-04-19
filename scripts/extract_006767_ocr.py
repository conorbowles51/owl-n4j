#!/usr/bin/env python3
"""
OCR-based multi-statement parser for USA-ET-006767.pdf (Brianpetzold Tambi's
Capital One 360 Total Control Checking — 83 pages of 11 monthly statements).

Strategy:
  1. OCR every page at 300 DPI
  2. Concatenate into one big text
  3. Detect each statement (STATEMENT PERIOD markers)
  4. For each month:
     - Extract Opening Balance ("Mon D Opening Balance $X.XX") and Closing Balance
     - Walk date-anchored rows: "Mon D <desc> + $X.XX" (credits) or "- $X.XX" (debits)
     - Validate: opening + sum(credits) - sum(debits) == closing (within 1¢)
  5. Only include months that validate

Known OCR quirks for this doc:
  - "Deposit" sometimes OCR'd as "Deve" / "Dep posit"
  - "Purchase" → "bh chase" / "Gani" (still recoverable from amount anchor)
  - "Brianpetzold" misread variously (ignored — holder is fixed)
"""
from __future__ import annotations
import json, re, sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_helpers import ocr_pdf_pages

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
REPO = Path(__file__).resolve().parent.parent
CASE_DIR = REPO / "ingestion" / "data" / CASE_ID
OUT_DIR = REPO / "ingestion" / "data" / "audit_results" / "2026-04-18"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PDF = CASE_DIR / "P3.11" / "USA-ET-006767.pdf"
CACHE = REPO / "ingestion" / "data" / "audit_results" / "_ocr_cache" / "USA-ET-006767.txt"
CACHE.parent.mkdir(parents=True, exist_ok=True)

HOLDER = "Brianpetzold Tambi"
ACCT = "36065389299"  # placeholder — actual account TBD from OCR

MONTHS = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], start=1)}


def money(s: str) -> float:
    s = s.replace("$", "").replace(",", "").strip()
    if s.startswith("."): s = "0" + s
    return float(s)


# Date anchor: "Mon D" or "Mon DD" at start of line (optional leading whitespace)
DATE_HEAD_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{1,2})\b", re.I)

# Line shape: "<date> <desc> [+|-] $<amount>"
# OCR sometimes inserts noise chars between date and desc; be lenient.
ROW_RE = re.compile(
    r"^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{1,2})\s+(.*?)\s+([+\-~])\s*\$?([\d,]+\.\d{2})\s*(\$[\d,]+\.\d{2})?\s*$",
    re.I,
)
OPENING_RE = re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*\d*\s*Opening Balance\s+\$([\d,]+\.\d{2})", re.I)
CLOSING_RE = re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*\d*[!lI]?\s*Closing Balance\s+\$([\d,]+\.\d{2})", re.I)
PERIOD_RE = re.compile(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d+)\s*-\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d+),?\s*(\d{4})", re.I)
HERES_YOUR_RE = re.compile(r"Here.{0,4}your\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+bank statement", re.I)


def get_or_build_ocr_text() -> List[str]:
    """OCR once, then cache to disk for fast re-runs."""
    if CACHE.exists():
        raw = CACHE.read_text()
        return raw.split("\n===PAGE-BREAK===\n")
    print(f"OCRing {PDF.name} (83 pages, will take a few minutes) ...")
    texts = ocr_pdf_pages(PDF, psm=6)
    CACHE.write_text("\n===PAGE-BREAK===\n".join(texts))
    print(f"Cached OCR at {CACHE}")
    return texts


def parse_statement(block_text: str) -> Tuple[Optional[Dict], List[str]]:
    """Parse one statement's OCR text.  Return (stmt, warnings) or (None, warnings)."""
    warnings: List[str] = []

    m_period = PERIOD_RE.search(block_text)
    m_open = OPENING_RE.search(block_text)
    m_close = CLOSING_RE.search(block_text)

    if not m_open:
        return None, ["missing Opening Balance"]
    if not m_close:
        return None, ["missing Closing Balance"]

    open_bal = money(m_open.group(2))
    close_bal = money(m_close.group(2))

    if m_period:
        em = m_period.group(3).title()[:3]
        ed_day = int(m_period.group(4))
        year = int(m_period.group(5))
        sm = m_period.group(1).title()[:3]
        sd_day = int(m_period.group(2))
        period = {
            "from": f"{year:04d}-{MONTHS[sm]:02d}-{sd_day:02d}",
            "to": f"{year:04d}-{MONTHS[em]:02d}-{ed_day:02d}",
        }
    else:
        year = datetime.now().year
        period = {"from": "", "to": ""}

    rows: List[Dict] = []
    for ln in block_text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if "Opening Balance" in s or "Closing Balance" in s:
            continue
        m = ROW_RE.match(s)
        if not m:
            continue
        mon_s, day_s, desc, sign, amt_s = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        try:
            amt = money(amt_s)
        except ValueError:
            continue
        direction = "in" if sign in ("+", "~") else "out"
        # ~ is often OCR'd "+"; treat as credit with low confidence
        mon = MONTHS[mon_s.title()[:3]]
        day = int(day_s)
        rows.append({
            "mon": mon, "day": day, "year": year,
            "desc": desc.strip(),
            "amount": amt,
            "direction": direction,
        })

    ins = round(sum(r["amount"] for r in rows if r["direction"] == "in"), 2)
    outs = round(sum(r["amount"] for r in rows if r["direction"] == "out"), 2)
    expected_close = round(open_bal + ins - outs, 2)

    if abs(expected_close - close_bal) >= 0.01:
        return None, [
            f"balance mismatch: open={open_bal} + in={ins} - out={outs} = {expected_close} ≠ close={close_bal}"
        ]

    return {
        "period": period,
        "open_bal": open_bal,
        "close_bal": close_bal,
        "deposits_extracted": ins,
        "withdrawals_extracted": outs,
        "rows": rows,
    }, warnings


def segment_statements(pages: List[str]) -> List[Tuple[int, int, str]]:
    """Segment by 'Here's your <Month> <Year> bank statement' marker which
    appears exactly once per statement (on the first page)."""
    markers: List[Tuple[int, str, str]] = []  # (page_idx, month_name, year)
    for i, t in enumerate(pages):
        m = HERES_YOUR_RE.search(t)
        if m:
            markers.append((i, m.group(1), m.group(2)))

    blocks = []
    for j, (start, mon, yr) in enumerate(markers):
        end = markers[j+1][0] if j+1 < len(markers) else len(pages)
        # For the LAST statement, cap the end at the last page that contains
        # "Closing Balance" plus a small margin — anything after that is
        # unrelated court records / other docs
        if j == len(markers) - 1:
            # Find closing balance page in this block
            for k in range(end - 1, start - 1, -1):
                if CLOSING_RE.search(pages[k]):
                    end = min(k + 2, end)  # keep the closing page + 1 more
                    break
        blocks.append((start, end, "\n".join(pages[start:end])))
    return blocks


def main():
    pages = get_or_build_ocr_text()
    print(f"OCR'd {len(pages)} pages")

    blocks = segment_statements(pages)
    print(f"Detected {len(blocks)} monthly statements")

    all_rows: List[Dict] = []
    month_summaries: List[Dict] = []
    failed: List[Dict] = []

    for idx, (start, end, text) in enumerate(blocks):
        stmt, warns = parse_statement(text)
        period_str = "?"
        m_p = PERIOD_RE.search(text)
        if m_p:
            period_str = f"{m_p.group(1)} {m_p.group(2)} {m_p.group(5)}"
        if stmt is None:
            print(f"✗ stmt {idx+1} ({period_str}, pg {start+1}-{end}): {warns[-1]}")
            failed.append({"index": idx+1, "period": period_str, "start_page": start+1, "reason": warns[-1]})
            continue
        print(f"✓ stmt {idx+1} ({period_str}, pg {start+1}-{end}): "
              f"{len(stmt['rows']):>3} rows  in=${stmt['deposits_extracted']:>10,.2f}  "
              f"out=${stmt['withdrawals_extracted']:>10,.2f}  "
              f"({stmt['period']['from']} → {stmt['period']['to']})")
        month_summaries.append({
            "statement_period": stmt["period"],
            "open_balance": stmt["open_bal"],
            "close_balance": stmt["close_bal"],
            "deposits": stmt["deposits_extracted"],
            "withdrawals": stmt["withdrawals_extracted"],
            "row_count": len(stmt["rows"]),
        })
        for r in stmt["rows"]:
            all_rows.append(r)

    # Build final rows in loader format
    final: List[Dict] = []
    for i, r in enumerate(all_rows, start=1):
        d = f"{r['year']:04d}-{r['mon']:02d}-{r['day']:02d}"
        final.append({
            "row_index": i,
            "date": d,
            "description_raw": r["desc"],
            "amount": r["amount"],
            "direction": r["direction"],
            "from_party": r["desc"][:80] if r["direction"] == "in" else HOLDER,
            "to_party": HOLDER if r["direction"] == "in" else r["desc"][:80],
            "channel": (
                "ATM Cash Deposit" if "ATM" in r["desc"] and "Deposit" in r["desc"] else
                "ATM Cash Withdrawal" if "ATM" in r["desc"] and "Withdrawal" in r["desc"] else
                "Debit Card" if "Debit Card" in r["desc"] or "Purchase" in r["desc"] else
                "Cash App" if "Square" in r["desc"] or "Cash App" in r["desc"].upper() else
                "WorldRemit" if "WORLDREMIT" in r["desc"].upper() else
                "SSI Benefit" if "SSI" in r["desc"] or "SUPP SEC" in r["desc"] else
                "Transfer" if "Withdrawal" in r["desc"] else
                "Other"
            ),
            "confidence": "medium",  # OCR-sourced
            "source_page": 1,
            "source_section": "Capital One 360 OCR",
            "financial_category": "Other",
        })

    dates = [r["date"] for r in final]
    out = {
        "doc_name": "USA-ET-006767.pdf",
        "case_id": CASE_ID,
        "bank": "Capital One 360",
        "account_holder": HOLDER,
        "account_number": "Total Control Checking (OCR)",
        "account_type": "360 Total Control Checking",
        "statement_period": {"from": min(dates) if dates else "", "to": max(dates) if dates else ""},
        "header_totals": {
            "statements_in_document": len(blocks),
            "statements_validated": len(month_summaries),
            "by_month": month_summaries,
            "failed_months": failed,
        },
        "extraction_model": "Tesseract 5.5 + pdfplumber + balance-equation validation",
        "extracted_at": "2026-04-18",
        "extraction_method": "OCR at 300 DPI, per-month opening+deposits-withdrawals=closing validation",
        "transactions": final,
    }
    (OUT_DIR / "USA-ET-006767.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote USA-ET-006767.json: {len(final)} txns across {len(month_summaries)}/{len(blocks)} validated months")
    if failed:
        print(f"({len(failed)} months failed validation — see header_totals.failed_months)")


if __name__ == "__main__":
    main()
