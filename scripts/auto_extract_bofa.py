#!/usr/bin/env python3
"""
Automated BofA checking/savings statement parser.
Reads PDFs, extracts transactions, validates against header totals.

Usage:
    python scripts/auto_extract_bofa.py                    # process all remaining
    python scripts/auto_extract_bofa.py --tolerance 0.05   # 5% tolerance (default)
    python scripts/auto_extract_bofa.py --doc USA-ET-001391.pdf  # single doc
    python scripts/auto_extract_bofa.py --load              # also load to Neo4j after

The script reads from _queue.json, skips docs that already have JSONs,
and writes to ingestion/data/audit_results/2026-04-12/.
"""
import argparse, json, re, sys
from pathlib import Path
from pypdf import PdfReader
from datetime import datetime

CASE_ID = "7e3b2c4a-9f61-4d8e-b2a7-5c9f1036d4ab"
REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "ingestion" / "data" / CASE_ID
OUT = REPO / "ingestion" / "data" / "audit_results" / "2026-04-12"

def clean(txt):
    txt = re.sub(r'USA-ET-\d+\s*', '', txt)
    txt = re.sub(r'USA-\d+\s*', '', txt)
    txt = re.sub(r'(?:NATIONAL TELEGRAPH LLC|BELTHA B MOKUBE|ERIC TANO TATAW|'
                 r'FILM TRIP AUTO GROUP LLC|MARTHA F ATEMLEFAC|'
                 r'SUPERSTORE INTERNATIONAL MKT LLC)\s+!\s+Account #.*?Page \d+ of \d+', '', txt)
    txt = re.sub(r'Your (?:checking )?account\s*', '', txt, flags=re.I)
    txt = re.sub(r'continued\s*(?:on the next page)?\s*(?:Date\s*Description\s*Amount\s*)?', '', txt, flags=re.I)
    txt = re.sub(r'(?:Deposits and other \w+|Withdrawals and other \w+)\s*-\s*continued\s*'
                 r'(?:Date\s*Description\s*Amount\s*)?', '', txt, flags=re.I)
    return txt

def parse_checking(doc_name, tolerance=0.05):
    hits = list(ROOT.rglob(doc_name))
    if not hits:
        return None
    reader = PdfReader(str(hits[0]))
    pages = [(pg.extract_text() or "").strip() for pg in reader.pages]
    p1 = pages[0]

    # Account holder
    for kw, nm in [("NATIONAL TELEGRAPH", "NATIONAL TELEGRAPH LLC"),
                    ("BELTHA", "BELTHA B MOKUBE"),
                    ("FILM TRIP", "FILM TRIP AUTO GROUP LLC"),
                    ("MARTHA", "MARTHA F ATEMLEFAC"),
                    ("SUPERSTORE", "SUPERSTORE INTERNATIONAL MKT LLC")]:
        if kw in p1:
            holder = nm
            break
    else:
        holder = "ERIC TANO TATAW" if "ERIC" in p1 and "TATAW" in p1 else "Unknown"

    acct_m = re.search(r'Account (?:number|#)[:\s]*([\d ]+)', p1)
    acct = acct_m.group(1).strip() if acct_m else ""
    type_m = re.search(r'Your (.+?) for ', p1)
    acct_type = type_m.group(1).strip() if type_m else "Checking"

    pm = re.search(r'for\s+(\w+ \d+,?\s*\d{4})\s+to\s+(\w+ \d+,?\s*\d{4})', p1)
    sd = ed = None
    if pm:
        try:
            ed = datetime.strptime(pm.group(2).replace(",", "").strip(), "%B %d %Y")
            sd = datetime.strptime(pm.group(1).replace(",", "").strip(), "%B %d %Y")
        except:
            pass

    def hv(p):
        m = re.search(p, p1)
        return float(m.group(1).replace(",", "")) if m else 0

    hdr = {
        "beginning_balance": hv(r'Beginning balance.*?\$?([\d,]+\.\d{2})'),
        "deposits_credits": hv(r'Deposits and other (?:credits|additions)\s*([\d,]+\.\d{2})'),
        "withdrawals_debits": hv(r'Withdrawals and other (?:debits|subtractions)\s*-?([\d,]+\.\d{2})'),
        "checks": hv(r'Checks\s*-?([\d,]+\.\d{2})'),
        "service_fees": hv(r'Service fees\s*-?([\d,]+\.\d{2})'),
        "ending_balance": hv(r'Ending balance.*?-?\$?([\d,]+\.\d{2})'),
    }
    if re.search(r'Ending balance.*?-\$', p1):
        hdr["ending_balance"] = -hdr["ending_balance"]

    txt = clean("".join(pages[2:]))

    def fsec(s, e):
        a, b = txt.find(s), txt.find(e)
        return txt[a:b] if a >= 0 and b > a else ""

    txns = []
    ri = 0

    def ext(sec, dr, sn):
        nonlocal ri
        if not sec:
            return
        for part in re.split(r'(?=\d{2}/\d{2}/\d{2})', sec):
            part = part.strip()
            if not part or len(part) < 8:
                continue
            dm = re.match(r'(\d{2})/(\d{2})/(\d{2})', part)
            if not dm:
                continue
            rest = part[6:].strip()
            rest = re.sub(
                r'(?:Subtotal|Total|Daily|Note your|Your Overdraft|Card account|'
                r'Important|Service fees|Checks |We have|Action needed|Scammers|Please see).*$',
                '', rest, flags=re.I).strip()
            am = re.search(r'(-?[\d,]+\.\d{2})\s*$', rest)
            if not am:
                continue
            amt = float(am.group(1).replace(",", ""))
            desc = rest[:am.start()].strip()
            if not desc or "Total" in desc:
                continue

            ch = ("Zelle" if "Zelle" in desc
                  else "ATM Deposit" if "ATM" in desc and "DEPOSIT" in desc
                  else "ATM Withdrawal" if "ATM" in desc and "WITHDR" in desc
                  else "Check Card" if any(k in desc for k in ["CHECKCARD", "PURCHASE", "PMNT SENT"])
                  else "Cash App" if any(k in desc for k in ["Cash App", "CASH APP", "Square Inc"])
                  else "PayPal" if "PAYPAL" in desc
                  else "Online Banking Payment" if "Online Banking" in desc
                  else "Service Fee" if any(k in desc.upper() for k in ["OVERDRAFT", "NSF", "FEE", "MAINTENANCE"])
                  else "ACH" if "DES:" in desc
                  else "Counter/Teller" if any(k in desc for k in ["MD TLR", "Counter Credit"])
                  else "Mobile Deposit" if "MOBILE" in desc and "DEPOSIT" in desc
                  else "Check" if re.match(r'Check\s*#?\d+', desc)
                  else "Other")

            ri += 1
            txns.append({
                "row_index": ri,
                "date": f"{2000 + int(dm.group(3))}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}",
                "description_raw": desc,
                "amount": abs(amt),
                "direction": dr,
                "from_party": desc[:50] if dr == "in" else holder,
                "to_party": holder if dr == "in" else desc[:50],
                "channel": ch,
                "confidence": "high",
                "source_page": 3,
                "source_section": sn,
            })

    ext(fsec("Deposits and other", "Total deposits and other"), "in", "Deposits")
    ext(fsec("Withdrawals and other", "Total withdrawals and other"), "out", "Withdrawals")
    ext(fsec("Checks ", "Total checks") or fsec("ChecksDate", "Total checks"), "out", "Checks")
    ext(fsec("Service fees", "Total service fees"), "out", "Service fees")

    ins = round(sum(t["amount"] for t in txns if t["direction"] == "in"), 2)
    outs = round(sum(t["amount"] for t in txns if t["direction"] == "out"), 2)
    hdr_out = hdr["withdrawals_debits"] + hdr["checks"] + hdr["service_fees"]

    tol_in = max(10, hdr["deposits_credits"] * tolerance)
    tol_out = max(10, hdr_out * tolerance)
    in_ok = abs(ins - hdr["deposits_credits"]) < tol_in
    out_ok = abs(outs - hdr_out) < tol_out

    if in_ok and out_ok and len(txns) > 0:
        doc = {
            "doc_name": doc_name, "case_id": CASE_ID, "bank": "Bank of America",
            "account_holder": holder, "account_number": acct, "account_type": acct_type,
            "statement_period": {
                "from": sd.strftime("%Y-%m-%d") if sd else "",
                "to": ed.strftime("%Y-%m-%d") if ed else "",
            },
            "header_totals": hdr,
            "extraction_model": f"claude-opus-4-6 (automated checking parser — {tolerance*100:.0f}% tolerance)",
            "extracted_at": "2026-04-12",
            "extraction_method": f"Automated regex parser ({tolerance*100:.0f}% tolerance)",
            "transactions": txns,
            "totals_check": {
                "deposits": ins, "hdr_deposits": hdr["deposits_credits"],
                "withdrawals": outs, "hdr_withdrawals": hdr_out,
                "dep_diff_pct": round(abs(ins - hdr["deposits_credits"]) / max(1, hdr["deposits_credits"]) * 100, 1),
                "wd_diff_pct": round(abs(outs - hdr_out) / max(1, hdr_out) * 100, 1),
            },
            "extraction_summary": {
                "total_transactions": len(txns),
                "in_count": sum(1 for t in txns if t["direction"] == "in"),
                "out_count": sum(1 for t in txns if t["direction"] == "out"),
            },
        }
        with open(OUT / doc_name.replace(".pdf", ".json"), "w") as f:
            json.dump(doc, f, indent=2)
        return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tolerance", type=float, default=0.05, help="Tolerance as fraction (0.05 = 5%%)")
    parser.add_argument("--doc", help="Process single doc")
    parser.add_argument("--load", action="store_true", help="Load to Neo4j after processing")
    args = parser.parse_args()

    if args.doc:
        ok = parse_checking(args.doc, args.tolerance)
        print(f"{args.doc}: {'✓' if ok else '✗'}")
        return

    # Load queue
    queue_path = OUT / "_queue.json"
    if not queue_path.exists():
        sys.exit(f"No queue at {queue_path}")

    with open(queue_path) as f:
        queue = json.load(f)

    already = {p.stem + ".pdf" for p in OUT.glob("USA-ET*.json")}
    remaining = [d for d in queue["docs"] if d["doc_name"] not in already]

    print(f"Remaining: {len(remaining)} docs (tolerance: {args.tolerance*100:.0f}%)")

    passed = failed = total_txns = 0
    for d in remaining:
        try:
            if parse_checking(d["doc_name"], args.tolerance):
                passed += 1
                with open(OUT / d["doc_name"].replace(".pdf", ".json")) as f:
                    total_txns += json.load(f)["extraction_summary"]["total_transactions"]
            else:
                failed += 1
        except Exception as e:
            failed += 1

    total_jsons = len(list(OUT.glob("USA-ET*.json")))
    print(f"\nPassed: {passed}, Failed: {failed}, New txns: {total_txns}")
    print(f"Total JSONs: {total_jsons} / 198 ({total_jsons/198*100:.0f}%)")

    if args.load:
        import subprocess
        print("\nLoading to Neo4j...")
        subprocess.run([
            str(REPO / "venv" / "bin" / "python3"),
            str(REPO / "scripts" / "build_audit_v2_nodes.py"),
            "--date", "2026-04-12", "--apply"
        ])


if __name__ == "__main__":
    main()
