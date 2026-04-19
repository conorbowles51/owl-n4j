#!/usr/bin/env python3
"""
Extract Zelle Early Warning subpoena transactions from USA-ET-003423.pdf.

Structure:
  page  1      : cover
  page  2      : sender profile (non-transactional)
  page  3      : recipient profile (non-transactional)
  pages 4-76   : "Zelle Transaction Information - Payments Sent"
                 account holder = ERIC TATAW as SENDER, direction = 'out'
  pages 77-177 : "Zelle Transaction Information - Payments Received"
                 account holder = ERIC TATAW as RECIPIENT, direction = 'in'
  pages 178+   : field descriptions & FAQ (non-transactional)

Each transaction row on the data pages has the columns:
  DATE, TIME, PAYMENT ID, SENDING BANK, SENDER NAME, RECEIVING BANK,
  RECIPIENT PROFILE ID, BUSINESS NAME, RECIPIENT FIRST, RECIPIENT LAST,
  RECIPIENT TOKEN, PAYMENT STATUS, PAYMENT AMOUNT, PAYMENT MEMO
(For Payments Received, header is mirrored to SENDER FIRST / SENDER LAST / …)

We use pdfplumber.extract_tables() and walk rows carefully:
  - first non-empty row on a page is the header (identifies column order)
  - subsequent rows with a date (M/D/YYYY) in col 1 are transaction rows
  - continuation rows (no date) are merged into the prior row's memo / token
Status = 'DELIVERED' rows only (others are pending / rejected — we keep them all
but mark category accordingly).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pdfplumber

PDF = Path("/home/conorbowles51/app_v2/ingestion/data/7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab/P3.4/USA-ET-003423.pdf")
OUT = Path("/home/conorbowles51/app_v2/ingestion/data/audit_results/2026-04-17/USA-ET-003423.json")
CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"

DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")
AMOUNT_RE = re.compile(r"\$([\d,]+\.\d{2})")

PAYMENTS_SENT_START = 4
PAYMENTS_SENT_END = 76   # inclusive
PAYMENTS_RECEIVED_START = 77
PAYMENTS_RECEIVED_END = 177  # inclusive


def clean(s: Optional[str]) -> str:
    if not s:
        return ""
    # pdfplumber injects PUA chars (\ue353 etc) between digits where columns squeeze
    s = re.sub(r"[\ue000-\uf8ff]", "", s)
    return s.strip()


def first_date(s: str) -> Optional[str]:
    m = DATE_RE.match(clean(s).split("\n", 1)[0])
    if not m:
        return None
    mm, dd, yy = m.group(1), m.group(2), m.group(3)
    try:
        return datetime.strptime(f"{mm}/{dd}/{yy}", "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def first_amount(s: str) -> Optional[float]:
    m = AMOUNT_RE.search(clean(s))
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def process_table(table: List[List[Optional[str]]], direction: str,
                  page_no: int, counter: List[int]) -> List[Dict]:
    """Walk a single page table and emit transaction dicts."""
    # Strip empty leading/trailing columns — some tables have None-only side columns
    if not table:
        return []
    # Identify real columns: any col where at least one cell has text
    ncols = len(table[0])
    keep = [c for c in range(ncols) if any(clean(r[c]) for r in table if c < len(r))]

    rows = [[(r[c] if c < len(r) else "") for c in keep] for r in table]

    def get(row, idx):
        if idx >= len(row):
            return ""
        v = row[idx]
        return clean(v) if v is not None else ""

    # The header is a combined header+first-data row (the PDF packs them).
    # We detect it by "PAYMENT ID" appearing in col 1 (which also contains the
    # first payment_id value).  But we cannot rely on "PAYMENT AMOUNT" text
    # because the amount column packs the label with the first value string.
    header_idx = None
    for i, row in enumerate(rows[:10]):
        joined = " ".join(clean(x) for x in row).upper()
        if "PAYMENT ID" in joined and "SENDING BANK NAME" in joined:
            header_idx = i
            break
    if header_idx is None:
        return []

    # The header row itself contains the first data row's values in col 1+
    # (payment_id, sending_bank, sender_name, ...) combined with the labels via
    # "LABEL\nVALUE".  We need to pull the post-newline portion of each cell
    # from the header row as the first transaction row.  Col 0 of the header
    # row similarly contains "DATE...\n<first date>".
    def after_label(cell) -> str:
        s = clean(cell)
        if "\n" not in s:
            return ""
        return s.split("\n", 1)[1].strip()

    synthesised_first = [after_label(c) for c in rows[header_idx]]
    data_rows = [synthesised_first] + rows[header_idx + 1:]

    out: List[Dict] = []
    last_row_dict: Optional[Dict] = None

    for r in data_rows:
        # Skip footer rows (contain "USA-ET-" page number) or empty
        joined = " ".join(clean(x) for x in r)
        if not joined:
            continue
        if joined.startswith("USA-ET-") and len(joined) < 20:
            continue

        date_cell = get(r, 0)
        d_iso = first_date(date_cell)
        if d_iso is None:
            # Continuation line — attach any memo text to last row
            if last_row_dict is not None:
                extra = joined.replace("USA-ET-", "").strip()
                if extra and len(extra) < 200:
                    last_row_dict["_continuation"] = (
                        last_row_dict.get("_continuation", "") + " " + extra
                    ).strip()
            continue

        # This is a new transaction row.
        payment_id = get(r, 1)
        sending_bank = get(r, 2)
        sender_name = get(r, 3)  # "LAST, FIRST"
        receiving_bank = get(r, 4)
        recipient_profile_id = get(r, 5)
        business_name = get(r, 6)
        recip_first = get(r, 7)
        recip_last = get(r, 8)
        recip_token = get(r, 9)
        payment_status = get(r, 10)
        payment_amount_s = get(r, 11)
        payment_memo = get(r, 12)

        amount = first_amount(payment_amount_s)
        if amount is None:
            # Row had no parseable amount — ignore
            continue

        # The first row of each page also has a HEADER overlap — detect this
        if payment_amount_s == "PAYMENT AMOUNT" or "PAYMENT AMOUNT" in payment_amount_s:
            continue

        counter[0] += 1
        row_idx = counter[0]

        # Counterparty = recipient (for sent) or sender (for received)
        if direction == "out":
            # Sent: account holder is SENDER; counterparty is RECIPIENT
            cp_business = business_name
            cp_person = " ".join(x for x in [recip_first, recip_last] if x).strip()
            cp_name = cp_business or cp_person or "Unknown recipient"
            cp_bank = receiving_bank
            cp_token = recip_token
        else:
            # Received: the "SENDER NAME" column holds the counterparty, and
            # the "RECIPIENT FIRST/LAST" columns hold Eric Tataw (the holder).
            # sender_name comes in as "LAST, FIRST" — flip to "First Last".
            parts = [p.strip() for p in sender_name.split(",")]
            if len(parts) == 2:
                cp_person = f"{parts[1].title()} {parts[0].title()}"
            else:
                cp_person = sender_name
            cp_business = business_name
            cp_name = cp_business or cp_person or "Unknown sender"
            cp_bank = sending_bank
            cp_token = recip_token  # still applies — sender's profile token not given

        description = f"Zelle {direction.upper()} {payment_status or 'SENT'} ({payment_id}) {cp_bank} {cp_name} {cp_token} {payment_memo}".strip()

        txn = {
            "row_index": row_idx,
            "date": d_iso,
            "description_raw": description,
            "amount": amount,
            "direction": direction,
            "from_party": (sender_name if direction == "out" else cp_name),
            "to_party":   (cp_name if direction == "out" else "ERIC TATAW"),
            "channel": "Zelle",
            "confidence": "high" if payment_status == "DELIVERED" else "medium",
            "source_page": page_no,
            "source_section": "Payments Sent" if direction == "out" else "Payments Received",
            "financial_category": "Transfer",
            "reference": payment_id,
            "payment_status": payment_status,
            "counterparty_bank": cp_bank,
            "counterparty_token": cp_token,
            "memo": payment_memo,
        }
        out.append(txn)
        last_row_dict = txn

    return out


def run():
    print(f"opening {PDF.name} ...", flush=True)
    txns_sent: List[Dict] = []
    txns_recv: List[Dict] = []
    counter = [0]

    with pdfplumber.open(PDF) as pdf:
        for pno in range(PAYMENTS_SENT_START, PAYMENTS_SENT_END + 1):
            page = pdf.pages[pno - 1]
            for tbl in (page.extract_tables() or []):
                txns_sent += process_table(tbl, "out", pno, counter)
            if pno % 10 == 0:
                print(f"  sent: processed up to page {pno}, running total {len(txns_sent)}", flush=True)
        print(f"  SENT TOTAL: {len(txns_sent)}", flush=True)

        counter[0] = 0
        for pno in range(PAYMENTS_RECEIVED_START, PAYMENTS_RECEIVED_END + 1):
            page = pdf.pages[pno - 1]
            for tbl in (page.extract_tables() or []):
                txns_recv += process_table(tbl, "in", pno, counter)
            if pno % 10 == 0:
                print(f"  recv: processed up to page {pno}, running total {len(txns_recv)}", flush=True)
        print(f"  RECV TOTAL: {len(txns_recv)}", flush=True)

    # Normalise whitespace in all string fields (counterparty names sometimes
    # pick up embedded newlines from wrapped PDF cells — e.g. "NATIONAL
    # TELEGRAPH\nLLC"). Collapse any run of whitespace to a single space.
    def _ws(s):
        if not isinstance(s, str):
            return s
        return re.sub(r"\s+", " ", s).strip()
    for t in txns_sent + txns_recv:
        for k in ("from_party", "to_party", "description_raw", "memo",
                  "counterparty_bank", "counterparty_token", "reference"):
            if k in t:
                t[k] = _ws(t.get(k))

    # Final numbering across both streams
    all_txns = []
    for i, t in enumerate(txns_sent + txns_recv, start=1):
        t["row_index"] = i
        all_txns.append(t)

    out_obj = {
        "doc_name": "USA-ET-003423.pdf",
        "case_id": CASE_ID,
        "bank": "Zelle (Early Warning Services)",
        "account_holder": "ERIC TATAW",
        "account_number": "Zelle token 19174801068 / 12023902247",
        "account_type": "Zelle profile",
        "statement_period": {
            "from": min((t["date"] for t in all_txns), default=None),
            "to": max((t["date"] for t in all_txns), default=None),
        },
        "header_totals": {
            "sent_count": len(txns_sent),
            "recv_count": len(txns_recv),
            "sent_total": round(sum(t["amount"] for t in txns_sent), 2),
            "recv_total": round(sum(t["amount"] for t in txns_recv), 2),
        },
        "extraction_model": "pdfplumber table parser (subpoena response)",
        "extracted_at": "2026-04-17",
        "extraction_method": "pdfplumber extract_tables() per page, column 0 = date anchor",
        "transactions": all_txns,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out_obj, indent=2))
    print(f"wrote {OUT}  ({len(all_txns)} txns)  sent_total=${out_obj['header_totals']['sent_total']:,}  recv_total=${out_obj['header_totals']['recv_total']:,}")


if __name__ == "__main__":
    run()
