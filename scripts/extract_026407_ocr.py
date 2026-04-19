#!/usr/bin/env python3
"""
OCR-based parser for USA-ET-026407.pdf — Lee Kameron's Ameris Bank Free
Checking, 130 pages, 12 monthly statements.  The first 5 months (Dec 2020 -
Apr 2021) parsed cleanly with pdfplumber and are already validated + loaded.
Pages 55-130 (May-Nov 2021) have degraded embedded text and failed validation.

Approach:
  - OCR every page once (cache)
  - Parse statements using the same logic as extract_ameris_026407.py but
    reading from OCR text instead of pdfplumber text
  - Validate per-month Total additions / Total subtractions
  - Write USA-ET-026407_ocr.json with the OCR-derived months; combine with
    the earlier pdfplumber months via a separate load step.

Note: we will replace the existing USA-ET-026407.json output since this
supersedes it with ALL validated months.
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

PDF = CASE_DIR / "P9.1" / "USA-ET-026407.pdf"
CACHE = REPO / "ingestion" / "data" / "audit_results" / "_ocr_cache" / "USA-ET-026407.txt"
CACHE.parent.mkdir(parents=True, exist_ok=True)

HOLDER = "LEE KAMERON"
ACCT = "1030224644"


def money(s: str) -> float:
    s = s.replace("$", "").replace(",", "").strip()
    if s.startswith("."): s = "0" + s
    return float(s)


def get_or_build_ocr() -> List[str]:
    if CACHE.exists():
        return CACHE.read_text().split("\n===PAGE-BREAK===\n")
    print(f"OCRing {PDF.name} (130 pages) ...")
    texts = ocr_pdf_pages(PDF, psm=6)
    CACHE.write_text("\n===PAGE-BREAK===\n".join(texts))
    print(f"Cached OCR at {CACHE}")
    return texts


AMT = r"(-?\$?(?:\d[\d,]*\.\d{2}|\.\d{2}))"
DATE_RE = re.compile(r"^(\d{2})[-/](\d{2})\s+(.+?)\s+" + AMT + r"\s*$")


def parse_one(text: str, period_year: int, this_month: int) -> Tuple[Optional[Dict], List[str]]:
    warnings: List[str] = []

    # Extract summary totals — be lenient with OCR variations
    m_add = re.search(r"Total\s+additions?\s+\$?\s*([\d,]+\.\d{2})", text, re.I)
    m_sub = re.search(r"Total\s+subtractions?\s+\$?-?\s*([\d,]+\.\d{2})", text, re.I)
    m_beg = re.search(r"Beginning\s+balance\s+\$?\s*(-?[\d,]+\.\d{2})", text, re.I)
    m_end = re.search(r"Ending\s+balance\s+\$?\s*(-?[\d,]+\.\d{2})", text, re.I)

    if not (m_add and m_sub):
        return None, ["could not find Total additions / subtractions on OCR text"]

    total_add = money(m_add.group(1))
    total_sub = money(m_sub.group(1))
    if total_sub < 0:
        total_sub = -total_sub

    # Enclosures (paid checks)
    enc_rows: List[Dict] = []
    m_encl = re.search(
        r"Number\s+Date\s+Amount(?:\s+Number\s+Date\s+Amount)?\s*\n(.*?)(?=\n(?:Date\s+Description|Daily\s+balances|Total))",
        text, re.DOTALL | re.I,
    )
    if m_encl:
        for m in re.finditer(r"(\d+)\s+(\d{2})[-/](\d{2})\s+(-?\$?[\d,]+\.\d{2})", m_encl.group(1)):
            chknum, mm, dd, amt_s = m.group(1), m.group(2), m.group(3), m.group(4)
            amt = abs(money(amt_s))
            enc_rows.append({
                "mm": mm, "dd": dd,
                "desc": f"Check paid (check# {chknum})" if chknum != "0" else "Check paid (no check number)",
                "amount": amt, "direction": "out",
            })

    # Transaction rows
    rows: List[Dict] = list(enc_rows)
    current: Optional[Dict] = None
    in_txn_section = False
    for ln in text.split("\n"):
        s = ln.strip()
        if not s: continue
        if re.search(r"Daily\s+balances|Total\s+Overdraft|Total\s+for\s+Total\s+prior", s, re.I):
            break
        if any(tok in s for tok in (
            "Page ", "Ameris Bank", "P.O. Box", "Customer Service", "Direct inquiries",
            "FOREST PARK GA", "LEE KAMERON", "Statement of Account", "Last statement:",
            "This statement:", "Total days in statement", "USA-ET-", "Free Checking",
            "Account number", "Summary of Account", "Number Date Amount", "Enclosures",
            "Account Number Ending", "Low balance", "Average balance",
            "Beginning balance", "Ending balance", "Total additions", "Total subtractions",
        )):
            continue
        if re.match(r"Date\s+Description", s, re.I):
            in_txn_section = True
            continue
        if not in_txn_section: continue
        m = DATE_RE.match(s)
        if m:
            mm, dd, desc, amt_s = m.group(1), m.group(2), m.group(3).strip(), m.group(4)
            try:
                amt = money(amt_s)
            except ValueError:
                continue
            direction = "in" if amt >= 0 else "out"
            current = {"mm": mm, "dd": dd, "desc": desc, "amount": abs(amt), "direction": direction}
            rows.append(current)
        else:
            if current is not None:
                current["desc"] = (current["desc"] + " " + s).strip()

    # Classify rows whose amount sign is ambiguous (OCR may lose the "-")
    # by checking description keywords
    DEBIT_MARKERS = ("Wd", "Purchase", "Check Card", "Preauthorized", "Zelle Acct Debit",
                     "POS Purchase", "Withdrawal", "ATM WD", "Check paid")
    for r in rows:
        u = r["desc"]
        if any(m in u for m in DEBIT_MARKERS) and r["direction"] != "out":
            r["direction"] = "out"

    ins = round(sum(r["amount"] for r in rows if r["direction"] == "in"), 2)
    outs = round(sum(r["amount"] for r in rows if r["direction"] == "out"), 2)
    validation = {
        "additions": {"header": total_add, "extracted": ins, "ok": abs(ins - total_add) < 0.01},
        "subtractions": {"header": total_sub, "extracted": outs, "ok": abs(outs - total_sub) < 0.01},
    }
    if not (validation["additions"]["ok"] and validation["subtractions"]["ok"]):
        return None, [f"MISMATCH: {validation}"]

    final_rows: List[Dict] = []
    for r in rows:
        year_eff = period_year
        if int(r["mm"]) > this_month:
            year_eff -= 1
        final_rows.append({
            "date": f"{year_eff:04d}-{int(r['mm']):02d}-{int(r['dd']):02d}",
            "description_raw": r["desc"],
            "amount": r["amount"],
            "direction": r["direction"],
        })
    return {
        "totals": {"additions": total_add, "subtractions": total_sub,
                     "beginning_balance": money(m_beg.group(1)) if m_beg else None,
                     "ending_balance": money(m_end.group(1)) if m_end else None},
        "validation": validation,
        "rows": final_rows,
    }, warnings


def main():
    pages = get_or_build_ocr()
    print(f"OCR'd {len(pages)} pages")

    # Find "Last statement: <date> / This statement: <date>" markers
    boundaries = []
    for i, t in enumerate(pages):
        m = re.search(r"Last statement:\s+(\w+ \d+,?\s*\d{4})\s*\n?\s*This statement:\s+(\w+ \d+,?\s*\d{4})", t, re.I)
        if m:
            boundaries.append((i, m.group(1), m.group(2)))
    print(f"Detected {len(boundaries)} statement boundaries")

    all_rows: List[Dict] = []
    month_summaries: List[Dict] = []
    failed: List[Dict] = []

    for idx, (start, prev_d, this_d) in enumerate(boundaries):
        end = boundaries[idx+1][0] if idx+1 < len(boundaries) else len(pages)
        block = "\n".join(pages[start:end])
        try:
            ed = datetime.strptime(this_d.replace(",", "").strip(), "%B %d %Y")
            period_year = ed.year
            this_month = ed.month
        except ValueError:
            period_year = 2021
            this_month = 12

        stmt, warns = parse_one(block, period_year, this_month)
        if stmt is None:
            print(f"✗ stmt {idx+1} ({prev_d} → {this_d}, pg {start+1}-{end}): {warns[-1][:200]}")
            failed.append({"statement": idx+1, "period": f"{prev_d} → {this_d}", "reason": warns[-1][:300]})
            continue
        print(f"✓ stmt {idx+1} ({prev_d} → {this_d}, pg {start+1}-{end}): {len(stmt['rows'])} rows  "
              f"add=${stmt['totals']['additions']:>9,.2f}  sub=${stmt['totals']['subtractions']:>9,.2f}")
        month_summaries.append({
            "statement_period": {"from": prev_d, "to": this_d},
            "totals": stmt["totals"],
            "validation": stmt["validation"],
            "row_count": len(stmt["rows"]),
        })
        all_rows.extend(stmt["rows"])

    # Build final JSON
    channel_of = lambda d: (
        "Zelle" if "Zelle" in d else
        "Check Card" if "Check Card" in d or "MERCHANT PURCHASE" in d else
        "ATM Deposit" if "ATM" in d and "Deposit" in d else
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
            "confidence": "medium",  # OCR-sourced
            "source_page": 1,
            "source_section": "Ameris monthly (OCR)",
            "financial_category": "Other",
        })

    dates = [r["date"] for r in final_rows]
    out = {
        "doc_name": "USA-ET-026407.pdf",
        "case_id": CASE_ID,
        "bank": "Ameris Bank",
        "account_holder": HOLDER,
        "account_number": ACCT,
        "account_type": "Free Checking",
        "statement_period": {"from": min(dates) if dates else "", "to": max(dates) if dates else ""},
        "header_totals": {
            "statements_in_document": len(boundaries),
            "statements_validated": len(month_summaries),
            "by_month": month_summaries,
            "failed_months": failed,
            "extraction_note": "OCR-based re-extraction supersedes earlier pdfplumber JSON",
        },
        "extraction_model": "Tesseract 5.5 + line parser + subtotal validation",
        "extracted_at": "2026-04-18",
        "extraction_method": "OCR at 300 DPI, per-month Total additions/subtractions validation",
        "transactions": final_rows,
    }
    (OUT_DIR / "USA-ET-026407.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote USA-ET-026407.json: {len(final_rows)} txns, {len(month_summaries)}/{len(boundaries)} months validated")


if __name__ == "__main__":
    main()
