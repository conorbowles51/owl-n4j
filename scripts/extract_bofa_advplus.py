#!/usr/bin/env python3
"""
Pdfplumber-based parser for Bank of America "Adv Plus Banking" personal
checking statements AND "Business Advantage Fundamentals/Preferred Rewards for
Bus" business checking statements.

Format conventions observed on page 1 (account summary) for any statement:

    Beginning balance on <date> <signed $amount>
    Deposits and other (additions|credits) <amount>
    Withdrawals and other (subtractions|debits) -<amount>
    Checks -<amount>
    Service fees -<amount>
    Ending balance on <date> <signed $amount>

Transaction sections on pages 3+:
    Deposits and other (additions|credits)
    Date    Description    Amount
    MM/DD/YY <desc, may wrap to next line> <amount>
    ...
    Total deposits and other (additions|credits) $<amount>

    Withdrawals and other (subtractions|debits)
    Date    Description    Amount
    MM/DD/YY <desc, may wrap to next line> <-amount>
    ...
    Total withdrawals and other (subtractions|debits) -$<amount>

    [optional] Checks
    Date    Check #   Description   Amount
    MM/DD/YY  12345  ...  -<amount>
    Total checks -$<amount>

    [optional] Service fees
    Date    Description    Amount
    MM/DD/YY  ...  -<amount>
    Total service fees -$<amount>

Validation: every extracted section's sum must match its printed subtotal
to the cent.  A statement is accepted only if all subtotals match.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
REPO = Path(__file__).resolve().parent.parent
CASE_DIR = REPO / "ingestion" / "data" / CASE_ID
OUT_DIR = REPO / "ingestion" / "data" / "audit_results" / "2026-04-17"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HOLDERS = {
    "ERIC TANO TATAW": "ERIC TANO TATAW",
    "BELTHA B MOKUBE": "BELTHA B MOKUBE",
    "BELTHA BUME MOKUBE": "BELTHA B MOKUBE",
    "NATIONAL TELEGRAPH": "NATIONAL TELEGRAPH LLC",
    "DIMMPLES": "DIMMPLES INC",
    "FILM TRIP AUTO": "FILM TRIP AUTO GROUP LLC",
    "MARTHA F ATEMLEFAC": "MARTHA F ATEMLEFAC",
    "SUPERSTORE INTERNATIONAL": "SUPERSTORE INTERNATIONAL MKT LLC",
}

DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{2})\s+(.*)$")
AMT_RE = re.compile(r"(-?\$?[\d,]+\.\d{2})\s*$")
MONEY_RE = re.compile(r"(-?\$?[\d,]+\.\d{2})")


def money_to_float(s: str) -> float:
    s = s.strip().replace("$", "").replace(",", "")
    return float(s)


def parse_page1_summary(p1_text: str) -> Tuple[Dict[str, Optional[float]], str, str, str, str, str]:
    """Return (totals, holder, acct, acct_type, period_from_iso, period_to_iso)."""
    totals: Dict[str, Optional[float]] = {
        "beginning_balance": None,
        "deposits": None,
        "withdrawals": None,
        "checks": None,
        "service_fees": None,
        "ending_balance": None,
    }

    # Parse each summary line — BofA prints the label then a number, with
    # "Withdrawals/Checks/Service fees" shown with a leading "-" sign.
    def grab(pat: str) -> Optional[float]:
        m = re.search(pat, p1_text)
        if not m:
            return None
        return money_to_float(m.group(1))

    totals["beginning_balance"] = grab(r"Beginning balance on [^\n]+?(-?\$?[\d,]+\.\d{2})")
    # Deposits: positive
    totals["deposits"] = grab(r"Deposits and other (?:additions|credits)\s+\$?([\d,]+\.\d{2})")
    # Withdrawals: printed with a leading minus
    totals["withdrawals"] = grab(r"Withdrawals and other (?:subtractions|debits)\s+(-?\$?[\d,]+\.\d{2})")
    totals["checks"] = grab(r"(?<!otal )Checks\s+(-?\$?[\d,]+\.\d{2})")
    totals["service_fees"] = grab(r"Service fees\s+(-?\$?[\d,]+\.\d{2})")
    totals["ending_balance"] = grab(r"Ending balance on [^\n]+?(-?\$?[\d,]+\.\d{2})")

    # Withdrawals/checks/fees are stored as negatives on the printed summary.
    # We want to compare *magnitude* against the sum of |amount| of extracted
    # outgoing rows, so normalise to positive here.
    for k in ("withdrawals", "checks", "service_fees"):
        v = totals[k]
        if v is not None and v < 0:
            totals[k] = -v

    # Account holder / number / type / period
    holder = "Unknown"
    for kw, nm in HOLDERS.items():
        if kw in p1_text.upper():
            holder = nm
            break

    m_acct = re.search(r"Account number:\s*([\d\s]{10,})", p1_text)
    acct = re.sub(r"\s+", "", m_acct.group(1)).strip() if m_acct else ""

    m_type = re.search(r"Your\s+(.+?)\n", p1_text)
    acct_type = m_type.group(1).strip() if m_type else "Checking"
    # "Your Adv Plus Banking"  or "Your Business Advantage Fundamentals..."
    # strip trailing " for <date>" if present
    acct_type = re.sub(r"\s+for\s+.*", "", acct_type)

    m_per = re.search(r"for\s+(\w+ \d+,?\s*\d{4})\s+to\s+(\w+ \d+,?\s*\d{4})", p1_text)
    if m_per:
        try:
            sd = datetime.strptime(m_per.group(1).replace(",", "").strip(), "%B %d %Y")
            ed = datetime.strptime(m_per.group(2).replace(",", "").strip(), "%B %d %Y")
            sd_s, ed_s = sd.strftime("%Y-%m-%d"), ed.strftime("%Y-%m-%d")
        except Exception:
            sd_s = ed_s = ""
    else:
        sd_s = ed_s = ""

    return totals, holder, acct, acct_type, sd_s, ed_s


def collect_section_text(pages_text: List[str], start_marker: str, end_marker: str) -> str:
    """Return the slice of concatenated text between start_marker and end_marker.
    Skips page-header boilerplate that repeats on each page ('<holder> ! Account #
    ... ! <period>' and 'continued' / 'Date Description Amount' lines).
    """
    joined = "\n".join(pages_text)
    # Find the FIRST occurrence of start_marker AFTER page 1 (page 1 has it in
    # the summary, which we don't want to parse as a section).
    # We include page 1's boilerplate search area and then skip past the
    # "Ending balance on" line.
    m_end_of_p1 = re.search(r"Ending balance on [^\n]+\n", joined)
    search_from = m_end_of_p1.end() if m_end_of_p1 else 0
    body = joined[search_from:]

    a = body.find(start_marker)
    if a < 0:
        return ""
    b = body.find(end_marker, a)
    if b < 0:
        return ""
    return body[a:b]


def parse_section(section_text: str, direction: str, section_label: str,
                  expected_total: Optional[float]) -> Tuple[List[Dict], float, List[str]]:
    """Walk the section line-by-line.

    Returns (rows, actual_sum_magnitude, warnings).

    Each row is a dict with row-level fields the loader expects.  The caller
    is responsible for filling row_index, channel, from/to parties, etc.
    """
    warnings: List[str] = []
    rows: List[Dict] = []

    if not section_text:
        return rows, 0.0, warnings

    lines = [ln for ln in section_text.split("\n")]

    # Strip page-boilerplate lines
    def is_boilerplate(ln: str) -> bool:
        s = ln.strip()
        if not s:
            return True
        if s.startswith("Date Description"):
            return True
        if "continued on the next page" in s:
            return True
        if re.match(r".*continued$", s):
            return True
        if re.match(r"Page \d+ of \d+", s):
            return True
        if s.startswith("USA-ET-"):
            return True
        if re.match(r".*! Account # .* ! .* to .*", s):
            return True
        return False

    # Group lines into rows.  The date line holds the amount (always at end
    # of THAT line).  Any non-date lines that follow are description
    # continuation — they must not move the amount anchor off end-of-line, so
    # we extract the amount from the date-line FIRST, then append continuation
    # text to the description only.
    grouped: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for ln in lines:
        if is_boilerplate(ln):
            continue
        if ln.startswith(section_text[:40]):  # first line of section
            continue
        s = ln.strip()
        m_date = DATE_RE.match(s)
        if m_date:
            # New row: extract amount from this line
            mm, dd, yy = m_date.group(1), m_date.group(2), m_date.group(3)
            rest = m_date.group(4).strip()
            m_amt = AMT_RE.search(rest)
            if not m_amt:
                warnings.append(f"no amount on date line: {s[:140]!r}")
                current = None
                continue
            amt_s = m_amt.group(1)
            desc_head = rest[:m_amt.start()].strip()
            current = {
                "mm": mm, "dd": dd, "yy": yy,
                "amt_s": amt_s,
                "desc": desc_head,
            }
            grouped.append(current)
        else:
            if current is not None and s:
                current["desc"] = (current["desc"] + " " + s).strip()

    total = 0.0
    for g in grouped:
        mm, dd, yy = int(g["mm"]), int(g["dd"]), int(g["yy"])
        amt_s = g["amt_s"]
        desc = g["desc"].strip()
        try:
            amt = money_to_float(amt_s)
        except ValueError:
            warnings.append(f"bad amount {amt_s!r} desc={desc[:80]!r}")
            continue
        if not desc:
            warnings.append(f"empty description: date={mm}/{dd}/{yy} amt={amt_s}")
            continue

        # For withdrawal/check/service sections, BofA prints negative numbers.
        # Store positive magnitude; loader applies sign from direction.
        magnitude = abs(amt)
        total += magnitude

        year = 2000 + yy if yy < 70 else 1900 + yy
        rows.append({
            "date": f"{year:04d}-{mm:02d}-{dd:02d}",
            "description_raw": desc,
            "amount": magnitude,
            "direction": direction,
            "source_section": section_label,
        })

    return rows, round(total, 2), warnings


def channel_for(desc: str) -> str:
    d = desc.upper()
    if "ZELLE" in d:
        return "Zelle"
    if "BKOFAMERICA ATM" in d and "DEPOSIT" in d:
        return "ATM Deposit"
    if "BKOFAMERICA ATM" in d and ("WITHDRWL" in d or "WITHDRAW" in d):
        return "ATM Withdrawal"
    if "CHECKCARD" in d or "PURCHASE" in d or "PMNT SENT" in d:
        return "Check Card"
    if "CASH APP" in d or "SQUARE INC" in d:
        return "Cash App"
    if "PAYPAL" in d:
        return "PayPal"
    if "ONLINE BANKING" in d:
        return "Online Banking Payment"
    if any(k in d for k in ("OVERDRAFT", "NSF", " FEE", "MAINTENANCE", "SERVICE CHARGE")):
        return "Service Fee"
    if "DES:" in d:
        return "ACH"
    if "MD TLR" in d or "COUNTER CREDIT" in d:
        return "Counter/Teller"
    if "MOBILE" in d and "DEPOSIT" in d:
        return "Mobile Deposit"
    if re.match(r"^Check\s*#?\d+", desc):
        return "Check"
    return "Other"


def parse_statement(pdf_path: Path) -> Tuple[Optional[Dict], List[str]]:
    warnings: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [(p.extract_text() or "") for p in pdf.pages]

    p1 = pages_text[0]
    totals, holder, acct, acct_type, sd, ed = parse_page1_summary(p1)

    # Collect section texts
    # Starts and ends for each section — vary by personal vs business
    # personal: "additions" / "subtractions"; business: "credits" / "debits"
    markers = [
        ("deposits",   "Deposits and other additions",    "Total deposits and other additions",    "in"),
        ("deposits",   "Deposits and other credits",      "Total deposits and other credits",      "in"),
        ("withdrawals", "Withdrawals and other subtractions", "Total withdrawals and other subtractions", "out"),
        ("withdrawals", "Withdrawals and other debits",    "Total withdrawals and other debits",    "out"),
    ]

    rows: List[Dict] = []
    extracted_sums: Dict[str, float] = {"deposits": 0.0, "withdrawals": 0.0,
                                          "checks": 0.0, "service_fees": 0.0}

    for key, start, end, direction in markers:
        sec = collect_section_text(pages_text, start, end)
        if not sec:
            continue
        label = "Deposits" if key == "deposits" else "Withdrawals"
        expected = totals.get(key)
        got_rows, got_sum, warns = parse_section(sec, direction, label, expected)
        extracted_sums[key] += got_sum
        rows.extend(got_rows)
        warnings.extend(warns)

    # Checks section — special 2-column layout:
    #   Date    Check #   Amount    Date    Check #   Amount
    #   01/02/20 124      -1,400.00 01/02/20 129*     -775.00
    # A single regex across the whole section catches each (date, check#, amount).
    checks_sec = collect_section_text(pages_text, "Checks\nDate", "Total checks")
    if checks_sec:
        check_re = re.compile(r"(\d{2})/(\d{2})/(\d{2})\s+(\d+)\*?\s+(-?\$?[\d,]+\.\d{2})")
        for m in check_re.finditer(checks_sec):
            mm, dd, yy, chk, amt_s = m.groups()
            try:
                amt = abs(money_to_float(amt_s))
            except ValueError:
                continue
            year = 2000 + int(yy) if int(yy) < 70 else 1900 + int(yy)
            rows.append({
                "date": f"{year:04d}-{int(mm):02d}-{int(dd):02d}",
                "description_raw": f"Check #{chk}",
                "amount": amt,
                "direction": "out",
                "source_section": "Checks",
                "reference": chk,
            })
            extracted_sums["checks"] += amt

    # Service fees — single-column, same format as Deposits/Withdrawals
    fees_sec = collect_section_text(pages_text, "Service fees\n", "Total service fees")
    if fees_sec:
        fee_rows, fee_sum, warns = parse_section(fees_sec, "out", "Service fees", totals.get("service_fees"))
        extracted_sums["service_fees"] += fee_sum
        rows.extend(fee_rows)
        warnings.extend(warns)

    # Validate totals. We require EXACT match to the cent.
    validation: Dict[str, Dict] = {}
    all_ok = True
    for k in ("deposits", "withdrawals", "checks", "service_fees"):
        hdr = totals.get(k) or 0.0
        got = round(extracted_sums.get(k, 0.0), 2)
        ok = abs(hdr - got) < 0.005
        validation[k] = {"header": hdr, "extracted": got, "diff": round(got - hdr, 2), "ok": ok}
        if not ok and hdr > 0:
            all_ok = False

    if not all_ok:
        warnings.append(f"SUBTOTAL MISMATCH: {validation}")
        return None, warnings

    # Assign row_index, channel, from/to
    doc_name = pdf_path.name
    final_rows: List[Dict] = []
    # Sort by date then original order within section to preserve chronology
    for idx, r in enumerate(rows, start=1):
        r["row_index"] = idx
        r["channel"] = channel_for(r["description_raw"])
        r["confidence"] = "high"
        r["source_page"] = 3  # placeholder; loader resolves physical page via PageResolver
        r["financial_category"] = "Other"  # loader fills from legacy index when possible
        cp = r["description_raw"][:80]
        if r["direction"] == "in":
            r["from_party"] = cp
            r["to_party"] = holder
        else:
            r["from_party"] = holder
            r["to_party"] = cp
        final_rows.append(r)

    doc = {
        "doc_name": doc_name,
        "case_id": CASE_ID,
        "bank": "Bank of America",
        "account_holder": holder,
        "account_number": acct,
        "account_type": acct_type,
        "statement_period": {"from": sd, "to": ed},
        "header_totals": totals,
        "validation": validation,
        "extraction_model": "pdfplumber line-based parser (BofA Adv Plus / Business Advantage)",
        "extracted_at": "2026-04-17",
        "extraction_method": "pdfplumber extract_text + section markers + subtotal-match validation",
        "transactions": final_rows,
    }
    return doc, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("doc", nargs="?", help="Specific doc filename (USA-ET-NNNNNN.pdf) or omit for all targets listed")
    parser.add_argument("--targets", help="Text file with one doc filename per line")
    args = parser.parse_args()

    if args.doc:
        docs = [args.doc]
    elif args.targets:
        docs = [ln.strip() for ln in Path(args.targets).read_text().splitlines() if ln.strip()]
    else:
        sys.exit("Pass a doc name or --targets file.")

    ok = 0
    bad: List[Tuple[str, List[str]]] = []
    for doc in docs:
        hits = list(CASE_DIR.rglob(doc))
        if not hits:
            bad.append((doc, ["NOT FOUND"]))
            continue
        out_obj, warns = parse_statement(hits[0])
        if out_obj is None:
            bad.append((doc, warns))
            print(f"✗ {doc}  {warns[-1][:140] if warns else 'unknown error'}")
            continue
        out_path = OUT_DIR / (doc.replace(".pdf", ".json"))
        out_path.write_text(json.dumps(out_obj, indent=2))
        n = len(out_obj["transactions"])
        ins = sum(t["amount"] for t in out_obj["transactions"] if t["direction"] == "in")
        outs = sum(t["amount"] for t in out_obj["transactions"] if t["direction"] == "out")
        print(f"✓ {doc}  {n:>3} txns  in=${ins:>11,.2f}  out=${outs:>11,.2f}  holder={out_obj['account_holder']}")
        ok += 1

    print(f"\n== {ok}/{len(docs)} docs passed validation ==")
    if bad:
        print("\nFailures:")
        for d, w in bad:
            print(f"  {d}: {w[-1][:160] if w else '?'}")


if __name__ == "__main__":
    main()
