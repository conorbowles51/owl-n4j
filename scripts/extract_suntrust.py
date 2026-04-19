#!/usr/bin/env python3
"""
Pdfplumber-based parser for SunTrust and Truist "Essential Checking" statements
belonging to ERIC TANO TATAW, account 1000262334955.

SunTrust format (older, 2019-2020):
  Account summary on page 1 with:
    BEGINNING BALANCE  $X
    DEPOSITS/CREDITS   $Y
    CHECKS             $.00
    WITHDRAWALS/DEBITS $Z
    ENDING BALANCE     $...
  Transaction history with columns:
    DATE   CHECK #   TRANSACTION DESCRIPTION DETAILS   DEPOSITS/CREDITS   WITHDRAWALS/DEBITS   CURRENT BALANCE

Truist format (newer, 2022):
  Account summary with:
    Your previous balance as of ... $X
    Checks                          - 0.00
    Other withdrawals, debits...    - Y
    Deposits, credits and interest  + Z
    Your new balance as of ...      = $...
  Sections: "Other withdrawals, debits and service charges" / "Deposits, credits and interest"

Validation: sum of extracted deposits == DEPOSITS/CREDITS header (to the cent).
Same for withdrawals.  Statement accepted only if both match.
"""
from __future__ import annotations

import argparse
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
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATE_MD_RE = re.compile(r"^(\d{2})/(\d{2})\s+(.*)$")
MONEY_TRAIL_RE = re.compile(r"(-?[\d,]+\.\d{2})(?:\s+([\d,]+\.\d{2}))?\s*$")


def money_to_float(s: str) -> float:
    return float(s.replace("$", "").replace(",", "").strip())


def parse_suntrust(pdf_path: Path) -> Tuple[Optional[Dict], List[str]]:
    warnings: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [(p.extract_text() or "") for p in pdf.pages]
    full = "\n".join(pages_text)

    # ── Page 1 header totals
    p1 = pages_text[0]
    # Allow "$.00" as 0.00 (SunTrust prints zero totals that way)
    AMT = r"\$?(\d[\d,]*\.\d{2}|\.\d{2})"
    def _parse_amt(m):
        if not m: return None
        s = m.group(1).replace(",", "")
        if s.startswith("."): s = "0" + s
        return float(s)
    m_begin = re.search(r"BEGINNING BALANCE\s+" + AMT, p1)
    m_dep   = re.search(r"DEPOSITS/CREDITS\s+" + AMT, p1)
    m_chk   = re.search(r"(?<!OR DEBIT )CHECKS\s+" + AMT, p1)
    m_wth   = re.search(r"WITHDRAWALS/DEBITS\s+" + AMT, p1)
    m_end   = re.search(r"ENDING BALANCE\s+" + AMT, p1)

    if not (m_dep and m_wth):
        return None, ["could not find DEPOSITS/CREDITS or WITHDRAWALS/DEBITS on page 1"]

    totals = {
        "beginning_balance": _parse_amt(m_begin),
        "deposits": _parse_amt(m_dep),
        "checks": _parse_amt(m_chk) or 0.0,
        "withdrawals": _parse_amt(m_wth),
        "ending_balance": _parse_amt(m_end),
    }

    # Statement period
    m_per = re.search(r"STATEMENT PERIOD\s*\n[^\n]*?(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", p1)
    if not m_per:
        m_per = re.search(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", p1)
    if m_per:
        sd = datetime.strptime(m_per.group(1), "%m/%d/%Y")
        ed = datetime.strptime(m_per.group(2), "%m/%d/%Y")
        period = {"from": sd.strftime("%Y-%m-%d"), "to": ed.strftime("%Y-%m-%d")}
    else:
        period = {"from": "", "to": ""}
    year = sd.year if m_per else 2020

    # ── Walk transaction history lines
    # The TRANSACTION HISTORY section layout (text):
    #   MM/DD  [CHK#]  <DESC>  [DEPOSITS_AMT]  [WITHDRAWALS_AMT]  [BALANCE]
    #   <continuation of desc>
    #
    # The amount appears on the date line.  BALANCE is shown only for some
    # rows (running-balance marker). We determine direction by:
    #   - look up the row in the 2-column "DEPOSITS/CREDITS" vs "WITHDRAWALS/DEBITS"
    #     columns based on x-position
    # But since text extraction loses column info, we use a different signal:
    # the printed row shows at most TWO amounts — the txn amount, then maybe a
    # running balance. The first of the two is the transaction amount. We then
    # classify direction by matching description keywords (CREDIT/PAYROLL/DEPOSIT
    # for in, PURCHASE/WITHDRAWAL/PAYMENT for out) AND by post-hoc verifying
    # that the per-direction sums equal the header totals.

    # Helper classifier
    CREDIT_MARKERS = [
        "ELECTRONIC/ACH CREDIT", "ZELLE TRANSFER FROM", "ZELLE PAYMENT FROM",
        "ATM DEPOSIT", "POINT OF SALE CREDIT", "DEPOSIT", "REFUND",
        "INTEREST PAID", "REVERSAL", "REBATE", "TRANSFER FROM",
    ]
    DEBIT_MARKERS = [
        "CHECK CARD PURCHASE", "RECURRING CHECK CARD", "POINT OF SALE DEBIT",
        "ATM CASH WITHDRAWAL", "ZELLE TRANSFER TO", "ZELLE PAYMENT TO",
        "ELECTRONIC/ACH DEBIT", "BILL PAYMENT", "WIRE TRANSFER OUT",
        "MAINTENANCE FEE", "OVERDRAFT FEE", "NSF", "SERVICE FEE",
    ]

    def classify(desc: str) -> Optional[str]:
        u = desc.upper()
        for m in CREDIT_MARKERS:
            if m in u:
                return "in"
        for m in DEBIT_MARKERS:
            if m in u:
                return "out"
        return None

    # Group date-anchored rows
    rows: List[Dict] = []
    lines = full.split("\n")

    # Find the transaction history start
    tx_start_idx = None
    for i, ln in enumerate(lines):
        if "TRANSACTION HISTORY" in ln or "DEPOSITS/" in ln and "WITHDRAWALS/" in ln.upper():
            tx_start_idx = i
            break
    if tx_start_idx is None:
        return None, ["no TRANSACTION HISTORY section found"]

    current: Optional[Dict] = None
    for ln in lines[tx_start_idx:]:
        s = ln.strip()
        if not s:
            continue
        # STOP on section-end markers (after TRANSACTION HISTORY comes the
        # "CREDIT AND DEBIT TOTALS" summary, then the "BALANCE ACTIVITY HISTORY"
        # two-column layout which would otherwise be parsed as fake rows).
        if ("CREDIT AND DEBIT TOTALS" in s.upper() or
            "BALANCE ACTIVITY HISTORY" in s.upper() or
            "THE ENDING DAILY BALANCES" in s.upper() or
            "DAILY POSTED BALANCE" in s.upper()):
            break
        # skip boilerplate
        if any(tok in s for tok in ("MEMBER FDIC", "PAGE ", "Page ", "SUNTRUST BANK", "STATEMENT PERIOD",
                                      "ACCOUNT SUMMARY", "OVERDRAFT PROTECTION", "QUESTIONS?",
                                      "TRANSACTION HISTORY", "USA-ET-")):
            continue
        # skip column headers
        if s.startswith("DATE CHECK #") or s.startswith("DEPOSITS/") or s.startswith("DATE TRANSACTION") or s.startswith("DEPOSITS/CREDITS"):
            continue

        m = DATE_MD_RE.match(s)
        if not m:
            # Continuation line — append to current
            if current is not None:
                current["desc"] = (current["desc"] + " " + s).strip()
            continue

        mm, dd, rest = m.group(1), m.group(2), m.group(3).strip()

        # Special marker "BEGINNING BALANCE"
        if "BEGINNING BALANCE" in rest.upper() or "ENDING BALANCE" in rest.upper():
            current = None
            continue

        # Extract trailing amounts.  A row has 1 or 2 trailing money tokens:
        #   <desc> <amount>            (no running balance shown)
        #   <desc> <amount> <balance>  (running balance shown)
        # Split the rest by whitespace to find trailing money tokens.
        toks = rest.rsplit(None, 2)
        amt = None
        desc_part = None
        # Try both-money (last two tokens are money)
        if len(toks) >= 2 and re.fullmatch(r"-?[\d,]+\.\d{2}", toks[-1]) and re.fullmatch(r"-?[\d,]+\.\d{2}", toks[-2]):
            # amount then balance
            amt = money_to_float(toks[-2])
            desc_part = " ".join(toks[:-2])
        elif len(toks) >= 1 and re.fullmatch(r"-?[\d,]+\.\d{2}", toks[-1]):
            amt = money_to_float(toks[-1])
            desc_part = " ".join(toks[:-1])
        else:
            # No amount on this line — treat as description line only, attach to
            # current row if any
            if current is not None:
                current["desc"] = (current["desc"] + " " + s).strip()
            continue

        if desc_part is None or not desc_part:
            continue

        current = {
            "mm": mm, "dd": dd, "amt": amt, "desc": desc_part,
        }
        rows.append(current)

    # Classify direction
    final_rows: List[Dict] = []
    for idx, r in enumerate(rows, start=1):
        dr = classify(r["desc"])
        if dr is None:
            # Unclassified — attempt context guess: if description has "TO " or "PURCHASE" lean out; "FROM" or "CREDIT" lean in
            u = r["desc"].upper()
            if " FROM " in u or " CREDIT" in u:
                dr = "in"
            elif " TO " in u or "PURCHASE" in u or "WITHDRAWAL" in u:
                dr = "out"
            else:
                warnings.append(f"unclassified direction: {r['desc'][:120]!r}")
                dr = "out"  # conservative default
        mm, dd = int(r["mm"]), int(r["dd"])
        year_eff = year
        # Handle statement spanning year boundary: if month is before start month, year += 1
        if m_per and mm < int(m_per.group(1).split("/")[0]) and sd.year == ed.year:
            year_eff = year + 1
        final_rows.append({
            "date": f"{year_eff:04d}-{mm:02d}-{dd:02d}",
            "description_raw": r["desc"],
            "amount": abs(r["amt"]),
            "direction": dr,
        })

    # Validate totals
    ins = round(sum(t["amount"] for t in final_rows if t["direction"] == "in"), 2)
    outs = round(sum(t["amount"] for t in final_rows if t["direction"] == "out"), 2)
    hdr_out = totals["withdrawals"] + totals["checks"]
    validation = {
        "deposits": {"header": totals["deposits"], "extracted": ins, "ok": abs(ins - totals["deposits"]) < 0.01},
        "withdrawals": {"header": hdr_out, "extracted": outs, "ok": abs(outs - hdr_out) < 0.01},
    }
    if not (validation["deposits"]["ok"] and validation["withdrawals"]["ok"]):
        return None, [f"SUBTOTAL MISMATCH: {validation}"]

    # Finalise
    doc_name = pdf_path.name
    for i, r in enumerate(final_rows, start=1):
        r["row_index"] = i
        r["channel"] = (
            "Zelle" if "ZELLE" in r["description_raw"].upper() else
            "Check Card" if "CHECK CARD" in r["description_raw"].upper() else
            "ACH" if "ACH" in r["description_raw"].upper() or "PAYROLL" in r["description_raw"].upper() else
            "ATM Withdrawal" if "ATM CASH WITHDRAWAL" in r["description_raw"].upper() else
            "ATM Deposit" if "ATM DEPOSIT" in r["description_raw"].upper() else
            "Point of Sale" if "POINT OF SALE" in r["description_raw"].upper() else
            "Service Fee" if any(k in r["description_raw"].upper() for k in ("FEE", "OVERDRAFT")) else
            "Other"
        )
        r["confidence"] = "high"
        r["source_page"] = 1
        r["source_section"] = "Transaction History"
        r["financial_category"] = "Other"
        cp = r["description_raw"][:80]
        if r["direction"] == "in":
            r["from_party"] = cp
            r["to_party"] = "ERIC TANO TATAW"
        else:
            r["from_party"] = "ERIC TANO TATAW"
            r["to_party"] = cp

    return {
        "doc_name": doc_name,
        "case_id": CASE_ID,
        "bank": "SunTrust / Truist",
        "account_holder": "ERIC TANO TATAW",
        "account_number": "1000262334955",
        "account_type": "Essential Checking",
        "statement_period": period,
        "header_totals": totals,
        "validation": validation,
        "extraction_model": "pdfplumber line-based parser (SunTrust/Truist)",
        "extracted_at": "2026-04-17",
        "extraction_method": "pdfplumber text + line-walk + direction classifier + subtotal validation",
        "transactions": final_rows,
    }, warnings


def parse_truist(pdf_path: Path) -> Tuple[Optional[Dict], List[str]]:
    """Newer Truist format (post 2021)."""
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [(p.extract_text() or "") for p in pdf.pages]
    full = "\n".join(pages_text)
    p1 = pages_text[0]

    m_prev = re.search(r"Your previous balance as of (\d+/\d+/\d+)\s+\$?(-?[\d,]+\.\d{2})", p1)
    m_chk = re.search(r"Checks\s*-\s*\$?([\d,]+\.\d{2})", p1)
    m_wth = re.search(r"Other withdrawals, debits and service charges\s*-\s*\$?([\d,]+\.\d{2})", p1)
    m_dep = re.search(r"Deposits, credits and interest\s*\+\s*\$?([\d,]+\.\d{2})", p1)
    m_new = re.search(r"Your new balance as of (\d+/\d+/\d+)\s+=?\s*\$?(-?[\d,]+\.\d{2})", p1)

    if not (m_dep and m_wth):
        return None, ["could not find Truist totals on page 1"]

    totals = {
        "beginning_balance": money_to_float(m_prev.group(2)) if m_prev else None,
        "deposits": money_to_float(m_dep.group(1)),
        "checks": money_to_float(m_chk.group(1)) if m_chk else 0.0,
        "withdrawals": money_to_float(m_wth.group(1)),
        "ending_balance": money_to_float(m_new.group(2)) if m_new else None,
    }

    period = {
        "from": datetime.strptime(m_prev.group(1), "%m/%d/%Y").strftime("%Y-%m-%d") if m_prev else "",
        "to": datetime.strptime(m_new.group(1), "%m/%d/%Y").strftime("%Y-%m-%d") if m_new else "",
    }
    year = int(period["to"][:4]) if period["to"] else 2022

    # Walk sections. Truist uses "Other withdrawals, debits..." and "Deposits, credits..." markers.
    rows: List[Dict] = []

    def parse_section(text: str, direction: str) -> List[Dict]:
        out = []
        for ln in text.split("\n"):
            s = ln.strip()
            m = re.match(r"(\d{2})/(\d{2})\s+(.+?)\s+(-?[\d,]+\.\d{2})\s*$", s)
            if not m:
                continue
            mm, dd, desc, amt = m.group(1), m.group(2), m.group(3).strip(), m.group(4)
            out.append({
                "mm": mm, "dd": dd, "desc": desc, "amount": abs(money_to_float(amt)),
                "direction": direction,
            })
        return out

    # Extract sections between markers
    def slice_section(full_text: str, start: str, end: str) -> str:
        a = full_text.find(start)
        if a < 0: return ""
        b = full_text.find(end, a)
        if b < 0: return ""
        return full_text[a:b]

    # Find the TRANSACTION section markers, not the summary line.  Both
    # "Other withdrawals, debits and service charges" and "Deposits, credits
    # and interest" also appear in the page-1 account summary.  The
    # transaction section is the SECOND occurrence, immediately followed by
    # "DATE DESCRIPTION AMOUNT($)".
    def slice_tx_section(full_text: str, start_marker: str, end_marker: str) -> str:
        # Find the start marker immediately followed by a DATE/DESCRIPTION/AMOUNT header
        pat = re.compile(re.escape(start_marker) + r"\s*\n\s*DATE\s+DESCRIPTION\s+AMOUNT")
        m = pat.search(full_text)
        if not m:
            return ""
        a = m.end()
        b = full_text.find(end_marker, a)
        if b < 0: return ""
        return full_text[a:b]

    wth_text = slice_tx_section(full, "Other withdrawals, debits and service charges",
                                  "Total other withdrawals")
    dep_text = slice_tx_section(full, "Deposits, credits and interest",
                                  "Total deposits, credits")

    for r in parse_section(wth_text, "out"): rows.append(r)
    for r in parse_section(dep_text, "in"): rows.append(r)

    final_rows: List[Dict] = []
    for r in rows:
        year_eff = year
        # Handle year wrap
        final_rows.append({
            "date": f"{year_eff:04d}-{int(r['mm']):02d}-{int(r['dd']):02d}",
            "description_raw": r["desc"],
            "amount": r["amount"],
            "direction": r["direction"],
        })

    # Validation
    ins = round(sum(t["amount"] for t in final_rows if t["direction"] == "in"), 2)
    outs = round(sum(t["amount"] for t in final_rows if t["direction"] == "out"), 2)
    validation = {
        "deposits": {"header": totals["deposits"], "extracted": ins, "ok": abs(ins - totals["deposits"]) < 0.01},
        "withdrawals": {"header": totals["withdrawals"], "extracted": outs, "ok": abs(outs - totals["withdrawals"]) < 0.01},
    }
    if not (validation["deposits"]["ok"] and validation["withdrawals"]["ok"]):
        return None, [f"SUBTOTAL MISMATCH: {validation}"]

    for i, r in enumerate(final_rows, start=1):
        r["row_index"] = i
        r["channel"] = "Zelle" if "ZELLE" in r["description_raw"].upper() else (
            "Service Fee" if "MAINTENANCE" in r["description_raw"].upper() or "FEE" in r["description_raw"].upper()
            else "Other")
        r["confidence"] = "high"
        r["source_page"] = 1
        r["source_section"] = "Truist sections"
        r["financial_category"] = "Other"
        cp = r["description_raw"][:80]
        if r["direction"] == "in":
            r["from_party"] = cp
            r["to_party"] = "ERIC TANO TATAW"
        else:
            r["from_party"] = "ERIC TANO TATAW"
            r["to_party"] = cp

    return {
        "doc_name": pdf_path.name,
        "case_id": CASE_ID,
        "bank": "Truist",
        "account_holder": "ERIC TANO TATAW",
        "account_number": "1000262334955",
        "account_type": "Essential Checking",
        "statement_period": period,
        "header_totals": totals,
        "validation": validation,
        "extraction_model": "pdfplumber line-based parser (Truist)",
        "extracted_at": "2026-04-17",
        "extraction_method": "section slicing + line regex + subtotal validation",
        "transactions": final_rows,
    }, []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", required=True)
    args = parser.parse_args()
    docs = [ln.strip() for ln in Path(args.targets).read_text().splitlines() if ln.strip()]
    for doc in docs:
        hits = list(CASE_DIR.rglob(doc))
        if not hits:
            print(f"✗ {doc}  NOT FOUND")
            continue
        # Detect SunTrust vs Truist from page 1
        with pdfplumber.open(hits[0]) as pdf:
            t1 = (pdf.pages[0].extract_text() or "")
        if "SUNTRUST BANK" in t1:
            obj, warns = parse_suntrust(hits[0])
            fmt = "SunTrust"
        elif "TRUIST" in t1.upper() or "Truist.com" in t1:
            obj, warns = parse_truist(hits[0])
            fmt = "Truist"
        else:
            print(f"?? {doc}: unrecognised format")
            continue
        if obj is None:
            print(f"✗ {doc}  ({fmt})  {warns[-1][:140] if warns else '?'}")
            continue
        out_path = OUT_DIR / (doc.replace(".pdf", ".json"))
        out_path.write_text(json.dumps(obj, indent=2))
        n = len(obj["transactions"])
        ins = sum(t["amount"] for t in obj["transactions"] if t["direction"] == "in")
        outs = sum(t["amount"] for t in obj["transactions"] if t["direction"] == "out")
        print(f"✓ {doc}  ({fmt})  {n:>3} txns  in=${ins:>11,.2f}  out=${outs:>11,.2f}")


if __name__ == "__main__":
    main()
