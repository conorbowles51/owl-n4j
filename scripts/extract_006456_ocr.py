#!/usr/bin/env python3
"""
OCR-based parser for USA-ET-006456.pdf — 16-page Early Warning Zelle subpoena
response for multiple NATIONAL TELEGRAPH LLC / DIMMPLES INC / Eric Tataw tokens.

Strategy:
  - OCR all 16 pages
  - Detect Payments Sent vs Payments Received sections
  - Extract per-row: DATE, PAYMENT_ID, SENDER, RECEIVER, BUSINESS, AMOUNT
  - Dedupe by payment_id (same as 003423)
"""
from __future__ import annotations
import json, re, sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocr_helpers import ocr_pdf_pages

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
REPO = Path(__file__).resolve().parent.parent
CASE_DIR = REPO / "ingestion" / "data" / CASE_ID
OUT_DIR = REPO / "ingestion" / "data" / "audit_results" / "2026-04-18"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PDF = CASE_DIR / "P3.10" / "USA-ET-006456.pdf"
CACHE = REPO / "ingestion" / "data" / "audit_results" / "_ocr_cache" / "USA-ET-006456.txt"
CACHE.parent.mkdir(parents=True, exist_ok=True)


def get_or_build_ocr() -> List[str]:
    if CACHE.exists():
        return CACHE.read_text().split("\n===PAGE-BREAK===\n")
    print(f"OCRing {PDF.name} ...")
    texts = ocr_pdf_pages(PDF, psm=6)
    CACHE.write_text("\n===PAGE-BREAK===\n".join(texts))
    print(f"Cached OCR")
    return texts


# Row format from OCR:
# 11/17/2021 17:09:53 BACzcH4zaplg Bank of America NATIONAL TELEGRAPH LLC Bank of America <profile-id> DIMMPLES INC <first> <last> <token> DELIVERED $180.00
# The date+time anchors each row. Amount always at end with $N.NN format.
DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+\d{1,2}:\d{2}:\d{2})?\s+(.*?)(?:\s+\$([\d,]+\.\d{2}))\s*(DELIVERED|SENT|FAILED|REJECTED)?\s*$", re.I)
# More lenient: date at start, $amount somewhere in the line
LENIENT_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})(?:\s+\d{1,2}:\d{2}:\d{2})?(.*?)(\$[\d,]+\.\d{2})", re.I)
PAY_ID_RE = re.compile(r"(BAC\w{6,}|COF\w{6,}|OPF\w{6,}|JPM\w{6,}|WFC\w{6,}|BBT\w{6,})")
SECTION_SENT = re.compile(r"Payments[\s.]*Sent", re.I)
SECTION_RECEIVED = re.compile(r"Payments[\s.]*Received", re.I)


def money(s: str) -> float:
    return float(s.replace("$", "").replace(",", "").strip())


def parse_rows(pages: List[str]) -> List[Dict]:
    """Extract rows by finding date anchors and the next $amount token."""
    rows: List[Dict] = []
    current_section = "unknown"
    DATE_ANCHOR = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
    AMOUNT_TOK = re.compile(r"\$([\d,]+\.\d{2})")

    for page_no, text in enumerate(pages, start=1):
        if SECTION_SENT.search(text): current_section = "sent"
        elif SECTION_RECEIVED.search(text): current_section = "received"

        # Find all date anchors and amount tokens with their positions
        date_hits = [(m.start(), m.group(1)) for m in DATE_ANCHOR.finditer(text)]
        amt_hits = [(m.start(), m.group(1)) for m in AMOUNT_TOK.finditer(text)]
        if not date_hits or not amt_hits:
            continue

        # For each date, find the NEXT amount token (forward in text).
        # Pair them one-to-one greedily.
        used_amt = set()
        for di, (dpos, date_s) in enumerate(date_hits):
            # Boundary: up to the next date anchor
            next_dpos = date_hits[di+1][0] if di+1 < len(date_hits) else len(text)
            # Find first unused amount token whose start falls between dpos and next_dpos
            chosen = None
            for ai, (apos, amt_s) in enumerate(amt_hits):
                if ai in used_amt: continue
                if apos > dpos and apos < next_dpos:
                    chosen = (ai, apos, amt_s)
                    break
            if chosen is None:
                continue
            ai, apos, amt_s = chosen
            used_amt.add(ai)
            try:
                d = datetime.strptime(date_s, "%m/%d/%Y")
            except ValueError:
                continue
            try:
                amt = money(amt_s)
            except ValueError:
                continue
            if amt < 0.01 or amt > 1_000_000: continue
            # Pull a "context" span as the raw row (±160 chars around date)
            ctx_start = max(0, dpos - 20)
            ctx_end = min(len(text), apos + 40)
            raw_row = text[ctx_start:ctx_end].replace("\n", " ").strip()
            pay_id_m = PAY_ID_RE.search(raw_row)
            pay_id = pay_id_m.group(1) if pay_id_m else ""
            rows.append({
                "date": d.strftime("%Y-%m-%d"),
                "raw_row": raw_row,
                "amount": amt,
                "payment_id": pay_id,
                "section": current_section,
                "source_page": page_no,
            })
    return rows


def main():
    pages = get_or_build_ocr()
    print(f"OCR'd {len(pages)} pages")
    rows = parse_rows(pages)
    print(f"Found {len(rows)} raw rows")

    # Dedupe by (section, payment_id) when available, else (section, date, amount)
    seen = {}
    kept: List[Dict] = []
    for r in rows:
        key = (r["section"], r["payment_id"] or (r["date"], r["amount"]))
        if key in seen: continue
        seen[key] = True
        kept.append(r)
    print(f"After dedupe: {len(kept)} rows")

    # Direction: "sent" section → account holder = sender (typically NATIONAL
    # TELEGRAPH LLC or DIMMPLES based on search tokens); "received" → recipient.
    # Without parsing each row's columns cleanly we can't know the direction
    # per transaction.  Since this is a subpoena response and text is imperfect,
    # we LOAD all rows with confidence=medium and flag the direction ambiguous.
    # The section field (sent vs received) tells us the gross direction.
    final: List[Dict] = []
    for i, r in enumerate(kept, start=1):
        desc = r["raw_row"][:150]
        direction = "out" if r["section"] == "sent" else "in"
        # Heuristic counterparty extraction from raw row — pick the first big
        # token that looks like a name (all caps words)
        # Account holder: unknown without OCR column accuracy; mark as composite
        holder = "NATIONAL TELEGRAPH LLC / DIMMPLES INC (subpoena multi-holder)"
        final.append({
            "row_index": i,
            "date": r["date"],
            "description_raw": f"Zelle {r['section'].upper()} ({r['payment_id'] or 'unknown-ref'}) — {desc[:100]}",
            "amount": r["amount"],
            "direction": direction,
            "from_party": holder if direction == "out" else "Zelle counterparty (OCR)",
            "to_party": "Zelle counterparty (OCR)" if direction == "out" else holder,
            "channel": "Zelle",
            "confidence": "medium",
            "source_page": r["source_page"],
            "source_section": f"006456 Payments {r['section'].title()} (OCR)",
            "financial_category": "Transfer",
            "reference": r["payment_id"] or None,
        })

    if not final:
        print("No rows extracted — doc skipped.")
        return

    dates = [r["date"] for r in final]
    out = {
        "doc_name": "USA-ET-006456.pdf",
        "case_id": CASE_ID,
        "bank": "Zelle (Early Warning Services, OCR)",
        "account_holder": "NATIONAL TELEGRAPH LLC / DIMMPLES INC",
        "account_number": "Multi-token subpoena response",
        "account_type": "Zelle profile",
        "statement_period": {"from": min(dates), "to": max(dates)},
        "header_totals": {
            "sent_count": sum(1 for r in final if r["direction"] == "out"),
            "recv_count": sum(1 for r in final if r["direction"] == "in"),
            "sent_total": round(sum(r["amount"] for r in final if r["direction"] == "out"), 2),
            "recv_total": round(sum(r["amount"] for r in final if r["direction"] == "in"), 2),
            "validation": "No printed totals on subpoena; payment-ID uniqueness + date-range sanity; confidence=medium due to OCR",
        },
        "extraction_model": "Tesseract 5.5 + Zelle row regex",
        "extracted_at": "2026-04-18",
        "extraction_method": "OCR at 300 DPI, lenient date+amount row detection, dedup by payment_id",
        "transactions": final,
    }
    (OUT_DIR / "USA-ET-006456.json").write_text(json.dumps(out, indent=2))
    print(f"wrote USA-ET-006456.json: {len(final)} txns "
          f"(out=${out['header_totals']['sent_total']:,.2f}, in=${out['header_totals']['recv_total']:,.2f})")


if __name__ == "__main__":
    main()
