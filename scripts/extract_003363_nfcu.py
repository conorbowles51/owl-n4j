#!/usr/bin/env python3
"""
Extract transactions from USA-ET-003363.pdf (Navy Federal subpoena response).
Sections:
  - page 1: single savings deposit (4/15/2021 $13,200)
  - pages 2-3: Deposit Verification log for DIMMPLES INC (~30 rows)
  - pages 4-7: Individual check images w/ Posting Date / Amount / Serial Number
  - pages 8-11: Fedwire outgoing transactions (credit transfers)
"""
import json, re
from pathlib import Path
import pdfplumber

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
CASE = Path(f"/home/conorbowles51/app_v2/ingestion/data/{CASE_ID}")
OUT = Path("/home/conorbowles51/app_v2/ingestion/data/audit_results/2026-04-17")
PDF = CASE / "P3.4" / "USA-ET-003363.pdf"

MONTH_MAP = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], start=1)}


def parse():
    assert PDF.exists()
    with pdfplumber.open(PDF) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]

    txns = []
    ri = 0

    # Page 1 — savings deposit.  Match just the date + type + amount since the
    # teller/branch IDs aren't needed for the financial record.
    p1 = pages[0]
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4}).*?(Savings Deposit|Deposit|Withdrawal|Cash Deposit)\s+\$?([\d,]+\.\d{2})', p1)
    if m:
        ri += 1
        txns.append({
            "row_index": ri,
            "date": f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}",
            "description_raw": f"{m.group(4)} (NFCU savings account 3142115389)",
            "amount": float(m.group(5).replace(",", "")),
            "direction": "in",
            "from_party": "Cash Deposit (NFCU branch V5)",
            "to_party": "DIMMPLES INC",
            "channel": "Branch Savings Deposit",
            "confidence": "high",
            "source_page": 1,
            "source_section": "NFCU savings deposit record",
            "financial_category": "Other",
        })

    # Pages 2-3 — Deposit Verification log
    log_pages = "\n".join(pages[1:3])
    # Row format: MM/DD/YYYY ATM_ID LOCATION SEQ CODE ORIG CURR DIFF TOTAL_CASH TOTAL_CHK DEPOSITOR
    dep_re = re.compile(
        r'(\d{2})/(\d{2})/(\d{4})\s+(\S+)\s+(\S+)\s+(\d+)\s+(\S+)\s+'
        r'([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+-\s+'
        r'([\d,]+\.\d{2}|-)\s+([\d,]+\.\d{2}|-)\s+DIMMPLES INC'
    )
    for m in dep_re.finditer(log_pages):
        mm, dd, yyyy = m.group(1), m.group(2), m.group(3)
        atm = m.group(4)
        loc = m.group(5)
        seq = m.group(6)
        code = m.group(7)
        amt = float(m.group(8).replace(",", ""))
        tc = m.group(10); tk = m.group(11)
        is_cash = (tc != "-" and tc != "")
        is_check = (tk != "-" and tk != "")
        channel = "ATM Cash Deposit" if is_cash else "ATM Check Deposit" if is_check else "ATM Deposit"
        ri += 1
        txns.append({
            "row_index": ri,
            "date": f"{yyyy}-{mm}-{dd}",
            "description_raw": f"{channel} ({loc}) seq {seq} code {code}",
            "amount": amt,
            "direction": "in",
            "from_party": "ATM Deposit" if is_cash else "Check Deposit",
            "to_party": "DIMMPLES INC",
            "channel": channel,
            "confidence": "high",
            "source_page": 2,
            "source_section": "Deposit Verification Log",
            "financial_category": "Other",
            "reference": f"seq {seq}",
        })

    # Pages 4-7 — individual check images with Posting Date / Amount / Serial
    for pi in range(3, 7):
        if pi >= len(pages): break
        t = pages[pi]
        m_date = re.search(r'Posting Date\s+(\d{4})\s+(\w+)\s+(\d{1,2})', t)
        m_amt = re.search(r'Amount\s+\$?([\d,]+\.\d{2})', t)
        m_ser = re.search(r'Serial Number\s+(\d+)', t)
        m_chk = re.search(r'Check Number\s+(\d+)', t)
        if m_date and m_amt:
            yr = m_date.group(1); mo = MONTH_MAP[m_date.group(2)[:3]]; dy = int(m_date.group(3))
            amt = float(m_amt.group(1).replace(",", ""))
            chknum = m_chk.group(1) if m_chk else "0"
            ser = m_ser.group(1) if m_ser else "0"
            ri += 1
            txns.append({
                "row_index": ri,
                "date": f"{yr}-{mo:02d}-{dy:02d}",
                "description_raw": f"Check deposit (serial {ser}, check# {chknum})",
                "amount": amt,
                "direction": "in",
                "from_party": f"Check #{chknum} / serial {ser}",
                "to_party": "DIMMPLES INC",
                "channel": "Check Deposit",
                "confidence": "high",
                "source_page": pi + 1,
                "source_section": "Check image detail",
                "financial_category": "Other",
                "reference": chknum if chknum != "0" else ser,
            })

    # Pages 8-11 — Fedwire transactions
    for pi in range(7, len(pages)):
        t = pages[pi]
        if "Transaction Id:" not in t:
            continue
        m_date = re.search(r'Settlement Date:\s+(\d{4})-(\d{2})-(\d{2})', t)
        m_amt = re.search(r'Settlement Amount:\s+([\d,]+\.\d{2})\s+USD', t)
        m_cd = re.search(r'Credit / Debit:\s+(Credit|Debit)', t)
        m_ref = re.search(r'Transaction Reference:\s+(\S+)', t)
        if not (m_date and m_amt): continue
        # Credit party
        m_credit = re.search(r'Credit Party\s*[\s\S]*?Name:\s+[\w,.]+?\s+([A-Z][A-Z\s,.&]+?)\n', t)
        # More permissive — look for "Name: DIMMPLES INC <Name>"
        m_names = re.search(r'Name:\s+DIMMPLES INC\s+(.+?)\s*\n', t)
        credit_name = m_names.group(1).strip() if m_names else "Unknown"
        direction = "out" if m_cd and m_cd.group(1) == "Credit" else "in"
        # Wait: Credit/Debit: Credit means DIMMPLES sent (DIMMPLES=Debit Party, so money goes OUT)
        # In the Fedwire system, "Credit" classification from DIMMPLES' view = outgoing wire
        amt = float(m_amt.group(1).replace(",", ""))
        ri += 1
        txns.append({
            "row_index": ri,
            "date": f"{m_date.group(1)}-{m_date.group(2)}-{m_date.group(3)}",
            "description_raw": f"Fedwire {direction.upper()} ({m_ref.group(1) if m_ref else 'N/A'}) to {credit_name}",
            "amount": amt,
            "direction": "out",  # DIMMPLES is debit party — sending
            "from_party": "DIMMPLES INC",
            "to_party": credit_name,
            "channel": "Fedwire",
            "confidence": "high",
            "source_page": pi + 1,
            "source_section": "Fedwire transaction detail",
            "financial_category": "Transfer",
            "reference": m_ref.group(1) if m_ref else None,
        })

    return txns


def main():
    txns = parse()
    OUT.mkdir(parents=True, exist_ok=True)
    doc = {
        "doc_name": "USA-ET-003363.pdf",
        "case_id": CASE_ID,
        "bank": "Navy Federal Credit Union",
        "account_holder": "DIMMPLES INC",
        "account_number": "XXXXXX5389",
        "account_type": "Savings/Checking",
        "statement_period": {
            "from": min(t["date"] for t in txns),
            "to": max(t["date"] for t in txns),
        },
        "header_totals": {
            "deposits_count": sum(1 for t in txns if t["direction"]=="in"),
            "wires_count": sum(1 for t in txns if t["direction"]=="out"),
            "deposits_total": round(sum(t["amount"] for t in txns if t["direction"]=="in"), 2),
            "wires_total": round(sum(t["amount"] for t in txns if t["direction"]=="out"), 2),
        },
        "extraction_model": "pdfplumber + regex (custom NFCU subpoena parser)",
        "extracted_at": "2026-04-17",
        "extraction_method": "Section-specific regex per page group",
        "transactions": txns,
    }
    (OUT / "USA-ET-003363.json").write_text(json.dumps(doc, indent=2))
    print(f"USA-ET-003363.pdf  {len(txns)} txns  deposits=${doc['header_totals']['deposits_total']:,.2f}  wires=${doc['header_totals']['wires_total']:,.2f}")
    for t in txns[:3] + txns[-3:]:
        print(f"  {t['date']} {t['direction']} ${t['amount']:>10,.2f} {t['description_raw'][:60]}")


if __name__ == "__main__":
    main()
