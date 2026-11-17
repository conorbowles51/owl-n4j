"""The second invented case (lx-relevancetest A): "Demo 2: State v. Priya Halloran (synthetic)".

A smaller case in another domain than the demo case (embezzlement at a dental practice, not thefts and fencing), so
the relevance set and the report tests are not tuned to one case. Built with the demo case's own writers (the phone
report builder, the statement PDF writer, the text PDF and Word writers), so it loads through the same app paths.

The story: Dr Owen Brackley's practice, Corwen Street Dental, lost $18,640 in patient refund checks from January to
April 2024. He accuses his bookkeeper, Priya Halloran, because she "handles refunds". The records show the practice
manager, Dorian Pell, approved the refunds under Priya's login from the manager's workstation (three of them while
she was on approved leave at Lake Orrin), deposited seven of the eight checks to his own account, and moved money
to his partner Marisol Teague's company, which also billed the practice as a supplier that does not exist.

The answer key is second-truths.json beside this file; build with
    python3 evidence-engine/tests/relevance/second_case.py <out>
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "phone"))
import demo_case as dcm  # noqa: E402  (the demo case's writers: L, BANNER, write_text_pdf, write_docx)
import fixture_builder as fb  # noqa: E402

CASE_TITLE = "Demo 2: State v. Priya Halloran (synthetic)"
BANNER = dcm.BANNER
L = dcm.L

P = fb.Person
PEOPLE = [
    P("priya", "Priya Halloran", ["+17175550211"], {"WhatsApp": "+17175550211"}, "priya.halloran@example.com"),
    P("dorian", "Dorian Pell", ["+17175550221"], {"WhatsApp": "+17175550221"}, "dorian.pell@example.net"),
    P("marisol", "Marisol Teague", ["+17175550231"], {"WhatsApp": "+17175550231"}, "marisol.teague@example.org"),
    P("owen", "Owen Brackley", ["+17175550241"], {}, "dr.brackley@example.com"),
    P("paulh", "Paul Halloran", ["+17175550251"], {}, "paul.halloran@example.org"),
    P("nell", "Nell Ashgrove", ["+17175550261"], {"WhatsApp": "+17175550261"}, "nell.ashgrove@example.com"),
    P("front", "Corwen Street Dental", ["+17175550200"], {}, "front@corwenstreetdental.example.com"),
]
INVENTED_NAMES = sorted({p.name for p in PEOPLE})
INVENTED_PLACES = ["Corwen Street Dental", "Quarrow Dental Supply", "Teague Practice Services", "Pell Hardware",
                   "Halbrook Federal Bank", "Nettlefield Savings", "Lake Orrin", "Fennick Market", "Birchmoor Lane",
                   "Lake Orrin Cabins", "Tamsworth County"]

PRACTICE = (40.271204, -76.884512)     # Corwen Street Dental, 220 Corwen Street
PRIYA_HOME = (40.289915, -76.861230)
PELL_HOME = (40.255031, -76.902118)
TEAGUE_APT = (40.262200, -76.910045)   # 14 Birchmoor Lane, Apt 2B: Marisol's flat, and Quarrow's "office"
LAKE = (41.302511, -77.612044)         # Lake Orrin Cabins, about 150 km away
MARKET = (40.280120, -76.871533)       # Fennick Market, a busy grocery

LEAVE = (dt.date(2024, 3, 11), dt.date(2024, 3, 22))
# The refunds: (log id, check, date approved, patient on the log, amount). None of these patients is on the roster.
REFUNDS = [("R-1041", 2201, dt.date(2024, 1, 16), "Evan Mardle", 2140.00),
           ("R-1042", 2202, dt.date(2024, 2, 5), "Corinne Spatch", 2980.00),
           ("R-1043", 2203, dt.date(2024, 2, 20), "Tobin Ellery", 1890.00),
           ("R-1044", 2204, dt.date(2024, 3, 13), "Ada Wrenfield", 2460.00),
           ("R-1045", 2205, dt.date(2024, 3, 14), "Silas Murrin", 2310.00),
           ("R-1046", 2206, dt.date(2024, 3, 19), "Hollis Bramm", 2775.00),
           ("R-1047", 2207, dt.date(2024, 4, 9), "Vera Kettlewell", 2845.00),
           ("R-1048", 2208, dt.date(2024, 4, 23), "Ned Fallon", 1240.00)]
LEGIT = ("R-1049", 2209, dt.date(2024, 2, 12), "Paul Halloran", 85.00)
DEPOSITED_BY_PELL = [r for r in REFUNDS if r[1] != 2208]  # 2208 was voided after the complaint
TRANSFERS = [(dt.date(2024, 1, 19), 2000.00), (dt.date(2024, 2, 8), 2900.00), (dt.date(2024, 2, 23), 1800.00),
             (dt.date(2024, 3, 15), 4700.00), (dt.date(2024, 3, 21), 2700.00), (dt.date(2024, 4, 11), 2800.00)]


def _days(a, b):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


def _m(day, h, mi, who, text, deleted="Intact"):
    return (L(day.year, day.month, day.day, h, mi), who, text, deleted, None)


def priya_phone() -> fb.PhoneSpec:
    tracks = []
    for day in _days(dt.date(2024, 1, 2), dt.date(2024, 4, 30)):
        if LEAVE[0] <= day <= LEAVE[1]:
            tracks += [(L(day.year, day.month, day.day, h, 15), LAKE[0] + 0.00002 * (h % 3), LAKE[1], 9) for h in (10, 16, 21)]
            continue
        if day.weekday() < 5:
            tracks += [(L(day.year, day.month, day.day, 9, 5), *PRACTICE, 8), (L(day.year, day.month, day.day, 16, 40), *PRACTICE, 8)]
        tracks += [(L(day.year, day.month, day.day, 21, 0), *PRIYA_HOME, 6)]
    tracks += [(L(2024, 2, 2, 12, 10), *MARKET, 15), (L(2024, 2, 2, 12, 22), MARKET[0], MARKET[1] + 0.00003, 15)]
    nell = [_m(dt.date(2024, 2, 2), 12, 12, "owner", "at Fennick Market, want anything for Sunday?"),
            _m(dt.date(2024, 2, 2), 12, 14, "nell", "lemons and the good bread"),
            _m(dt.date(2024, 3, 11), 14, 30, "owner", "made it to Lake Orrin! no signal at the dock, back on the 22nd"),
            _m(dt.date(2024, 3, 14), 19, 5, "nell", "how's the cabin?"),
            _m(dt.date(2024, 3, 14), 19, 9, "owner", "freezing and perfect. not thinking about work once"),
            _m(dt.date(2024, 3, 22), 18, 40, "owner", "home. unpacking")]
    dorian = [_m(dt.date(2024, 3, 8), 17, 40, "dorian", "before you head up to the lake, leave me your login on a sticky. I need to post the March refunds"),
              _m(dt.date(2024, 3, 8), 17, 46, "owner", "it's in the top drawer. please don't change anything in payroll"),
              _m(dt.date(2024, 3, 25), 9, 2, "owner", "did you change my password back? it won't let me in"),
              _m(dt.date(2024, 3, 25), 9, 20, "dorian", "IT reset everyone's. just use the new one")]
    front = [_m(dt.date(2024, 2, 12), 10, 3, "front", "Paul Halloran called about his $85 refund for the cancelled cleaning, can you check?"),
             _m(dt.date(2024, 2, 12), 10, 30, "owner", "done, check 2209 goes out today")]
    owen = [_m(dt.date(2024, 5, 2), 8, 15, "owen", "Priya, please come to my office at 9. It's about the refunds."),
            _m(dt.date(2024, 5, 2), 8, 17, "owner", "of course. is something wrong?")]
    script = fb.Script(chats=[fb.ScriptChat("WhatsApp", ["nell"], nell), fb.ScriptChat("Native Messages", ["dorian"], dorian),
                              fb.ScriptChat("Native Messages", ["front"], front), fb.ScriptChat("Native Messages", ["owen"], owen)],
                       calls=[(L(2024, 3, 13, 11, 0), "nell", "Outgoing", "Established", 300)],
                       tracks=tracks,
                       contacts=[("Nell", ["+17175550261"], {}), ("Dorian (office)", ["+17175550221"], {}),
                                 ("Front desk", ["+17175550200"], {}), ("Dr Brackley", ["+17175550241"], {})],
                       saved_names={"nell": "Nell", "dorian": "Dorian (office)", "front": "Front desk", "owen": "Dr Brackley"})
    return fb.PhoneSpec("PH1", like="P14", scale=0.002, owner="priya", extraction_date=dt.date(2024, 5, 20),
                        period_days=140, gap=None, contacts=["nell", "dorian", "front", "owen"], seed=701,
                        random_locations=False, script=script, device_name="iPhone (Phone PH1)", os_type="iOS")


def pell_phone() -> fb.PhoneSpec:
    tracks = []
    for day in _days(dt.date(2024, 1, 2), dt.date(2024, 4, 30)):
        if day.weekday() < 5:
            tracks += [(L(day.year, day.month, day.day, 8, 50), *PRACTICE, 8), (L(day.year, day.month, day.day, 17, 30), *PRACTICE, 8)]
        tracks += [(L(day.year, day.month, day.day, 21, 30), *PELL_HOME, 6)]
    tracks += [(L(2024, 2, 2, 12, 30), *MARKET, 15)]
    for _, _, d, _, _ in REFUNDS:  # evenings at Marisol's flat after each approval
        tracks += [(L(d.year, d.month, d.day, 20, 10), *TEAGUE_APT, 8)]
    marisol = []
    for d, amount in TRANSFERS:
        marisol += [_m(d, 19, 5, "owner", "refunds cleared. moving it to the services account tonight"),
                    _m(d, 19, 9, "marisol", "ok. the Quarrow invoice goes out Friday")]
    marisol += [_m(dt.date(2024, 4, 25), 21, 44, "owner", "Brackley is asking about the refund log. delete the Quarrow emails", "Deleted"),
                _m(dt.date(2024, 4, 25), 21, 50, "marisol", "done. all of them")]
    priya = [_m(dt.date(2024, 3, 8), 17, 40, "owner", "before you head up to the lake, leave me your login on a sticky. I need to post the March refunds"),
             _m(dt.date(2024, 3, 8), 17, 46, "priya", "it's in the top drawer. please don't change anything in payroll"),
             _m(dt.date(2024, 3, 25), 9, 2, "priya", "did you change my password back? it won't let me in"),
             _m(dt.date(2024, 3, 25), 9, 20, "owner", "IT reset everyone's. just use the new one")]
    script = fb.Script(chats=[fb.ScriptChat("WhatsApp", ["marisol"], marisol), fb.ScriptChat("Native Messages", ["priya"], priya)],
                       tracks=tracks,
                       contacts=[("M", ["+17175550231"], {}), ("Priya H", ["+17175550211"], {}), ("Dr B", ["+17175550241"], {})],
                       saved_names={"marisol": "M", "priya": "Priya H"})
    return fb.PhoneSpec("PH2", like="P09", scale=0.002, owner="dorian", extraction_date=dt.date(2024, 5, 21),
                        period_days=140, gap=None, contacts=["marisol", "priya"], seed=702, random_locations=False,
                        script=script, device_name="Phone PH2", os_type="Android")


def teague_phone() -> fb.PhoneSpec:
    lines = []
    for d, amount in TRANSFERS:
        lines += [_m(d, 19, 5, "dorian", "refunds cleared. moving it to the services account tonight"),
                  _m(d, 19, 9, "owner", "ok. the Quarrow invoice goes out Friday")]
    lines += [_m(dt.date(2024, 4, 25), 21, 50, "owner", "done. all of them")]
    tracks = [(L(d.year, d.month, d.day, 20, 0), *TEAGUE_APT, 7) for d in _days(dt.date(2024, 1, 2), dt.date(2024, 4, 30))]
    script = fb.Script(chats=[fb.ScriptChat("WhatsApp", ["dorian"], lines)], tracks=tracks,
                       contacts=[("Dorian", ["+17175550221"], {})], saved_names={"dorian": "Dorian"})
    return fb.PhoneSpec("PH3", like="P12", scale=0.002, owner="marisol", extraction_date=dt.date(2024, 5, 22),
                        period_days=140, gap=None, contacts=["dorian"], seed=703, random_locations=False, script=script,
                        device_name="Phone PH3", os_type="Android")


# ---- statements -------------------------------------------------------------------------------------------------

def practice_rows():
    rows = []
    for m in range(1, 5):
        rows += [{"date": dt.date(2024, m, 1), "desc": "CORWEN ST PROPERTIES RENT", "amount": -6200.00},
                 {"date": dt.date(2024, m, 15), "desc": "PAYROLL RUN", "amount": -21480.00},
                 {"date": dt.date(2024, m, 8), "desc": "QUARROW DENTAL SUPPLY INV", "amount": -4600.00},
                 {"date": dt.date(2024, m, 10), "desc": "PELL HARDWARE", "amount": -round(38.40 + 6.15 * m, 2)}]
        for d in (5, 12, 19, 26):
            rows.append({"date": dt.date(2024, m, d), "desc": "PATIENT CARD SETTLEMENT", "amount": round(9120.00 + 113 * d + 71 * m, 2)})
    for rid, chk, d, name, amount in REFUNDS + [LEGIT]:
        if chk == 2208:
            continue
        rows.append({"date": d + dt.timedelta(days=2), "desc": "CHECK %d" % chk, "amount": -amount})
    return rows


def pell_rows():
    rows = []
    for m in range(1, 5):
        rows += [{"date": dt.date(2024, m, 15), "desc": "CORWEN STREET DENTAL PAYROLL", "amount": 2410.00},
                 {"date": dt.date(2024, m, 3), "desc": "BIRCHWOOD TERRACE RENT", "amount": -1280.00}]
    for rid, chk, d, name, amount in DEPOSITED_BY_PELL:
        rows.append({"date": d + dt.timedelta(days=2), "desc": "MOBILE DEP CHK %d CORWEN STREET DENTAL" % chk, "amount": amount})
    for d, amount in TRANSFERS:
        rows.append({"date": d, "desc": "TRANSFER TO TEAGUE PRACTICE SERVICES", "amount": -amount})
    return rows


def priya_rows():
    rows = []
    for m in range(1, 5):
        rows += [{"date": dt.date(2024, m, 15), "desc": "CORWEN STREET DENTAL PAYROLL", "amount": 2080.00},
                 {"date": dt.date(2024, m, 4), "desc": "HALBROOK MORTGAGE", "amount": -1115.00}]
        for d in (7, 14, 21, 28):
            rows.append({"date": dt.date(2024, m, d), "desc": "TAMSWORTH GROCERY", "amount": -round(58.20 + d * 1.1 + m, 2)})
    rows += [{"date": dt.date(2024, 2, 2), "desc": "FENNICK MARKET", "amount": -42.18},
             {"date": dt.date(2024, 3, 11), "desc": "LAKE ORRIN CABINS DEPOSIT", "amount": -380.00},
             {"date": dt.date(2024, 3, 22), "desc": "LAKE ORRIN CABINS BALANCE", "amount": -760.00}]
    return rows


ACCOUNTS = {
    "practice": dict(holder="CORWEN STREET DENTAL PC", account="3310-044719", bank="Halbrook Federal Bank", opening=48210.55,
                     rows=practice_rows),
    "pell": dict(holder="DORIAN PELL", account="5502-097302", bank="Nettlefield Savings", opening=1830.12, rows=pell_rows),
    "halloran": dict(holder="PRIYA HALLORAN", account="5502-115518", bank="Nettlefield Savings", opening=3122.40,
                     rows=priya_rows),
}


def write_statements(out: Path) -> dict:
    info = {}
    for key, acc in ACCOUNTS.items():
        rows, balance, files = sorted(acc["rows"](), key=lambda r: r["date"]), acc["opening"], []
        for m in range(1, 5):
            month = [r for r in rows if r["date"].month == m]
            printed, opening = [], balance
            for r in month:
                balance = round(balance + r["amount"], 2)
                printed.append({"Date": r["date"].strftime("%m/%d/%Y"), "Description": r["desc"],
                                "Amount": f"{r['amount']:.2f}", "Balance": f"{balance:.2f}"})
            first, last = dt.date(2024, m, 1), dt.date(2024, m + 1, 1) - dt.timedelta(days=1)
            opts = dict(opening=opening, start=first, end=last, holder=acc["holder"], account=acc["account"],
                        bank=acc["bank"], page_mark=BANNER, paginate=True, title_case=False)
            path = out / "statements" / key / f"{key}-2024-{m:02d}.pdf"
            path.parent.mkdir(parents=True, exist_ok=True)
            fb.write_statement_pdf(printed, path, **opts)
            files.append(str(path.relative_to(out)))
            if key == "practice" and m == 4:  # the complainant's exhibit: the same April statement again
                dup = out / "statements" / "complainant-exhibits" / "exhibit-b-practice-april-2024.pdf"
                dup.parent.mkdir(parents=True, exist_ok=True)
                fb.write_statement_pdf(printed, dup, **dict(opts, page_mark=BANNER + "   COMPLAINANT'S EXHIBIT B"))
                files.append(str(dup.relative_to(out)))
        info[key] = {"files": files, "rows": len(rows), "closing": balance}
    return info


# ---- documents --------------------------------------------------------------------------------------------------

def documents(out: Path) -> list[str]:
    d = out / "documents"
    d.mkdir(parents=True, exist_ok=True)
    made = []
    total = sum(r[4] for r in REFUNDS)
    dcm.write_text_pdf(d / "complaint-letter-brackley-2024-05-02.pdf", "Complaint to the Tamsworth County Police", (
        "From: Dr Owen Brackley, owner, Corwen Street Dental PC, 220 Corwen Street.\n"
        "Date: 2 May 2024.\n"
        f"Between January and April 2024 the practice paid ${total:,.2f} in patient refund checks that no patient "
        "asked for. Our bookkeeper, Priya Halloran, handles refunds, and the refund log shows her login on every one "
        "of them. I ask the police to investigate her. Our practice manager, Dorian Pell, found the problem when he "
        "reviewed the April log."))
    dcm.write_text_pdf(d / "leave-approval-halloran-2024-03.pdf", "Leave approval", (
        "Employee: Priya Halloran, bookkeeper.\n"
        "Leave requested: Monday 11 March 2024 to Friday 22 March 2024 (ten working days), annual leave.\n"
        "Approved by: Dr Owen Brackley, 26 February 2024.\n"
        "Cover during leave: refunds and payroll queries to Dorian Pell, practice manager."))
    lines = ["For deposit only. Nettlefield Savings, account ending 7302.", ""]
    for rid, chk, day, name, amount in DEPOSITED_BY_PELL:
        lines.append(f"Check {chk}, {day:%d %B %Y}, pay to {name}, ${amount:,.2f}. Endorsed on the back: "
                     "for deposit only, Nettlefield Savings acct ending 7302, mobile deposit.")
    dcm.write_text_pdf(d / "check-copies-2201-2207.pdf", "Bank copies of cleared refund checks", "\n".join(lines))
    dcm.write_text_pdf(d / "quarrow-invoices-2024.pdf", "Quarrow Dental Supply invoices", (
        "Quarrow Dental Supply, 14 Birchmoor Lane, Apt 2B.\n"
        "Invoices Q-311 (January), Q-322 (February), Q-334 (March), Q-347 (April) 2024: 'impression trays and "
        "sundries', $4,600.00 each, payable to Corwen Street Dental's supplier account. No delivery note is attached "
        "to any of them."))
    dcm.write_text_pdf(d / "teague-practice-services-registration.pdf", "Business registration", (
        "Teague Practice Services LLC. Registered agent and sole member: Marisol Teague, 14 Birchmoor Lane, Apt 2B. "
        "Registered 9 January 2024. Trades as: Quarrow Dental Supply."))
    dcm.write_docx(d / "pell-interview-2024-05-10.docx", "Interview of Dorian Pell, 10 May 2024", [
        "Present: Det. R. Imber (synthetic), Dorian Pell.",
        "IMBER: Who approves refunds at the practice?",
        "PELL: Priya does every refund. I never touch the refund screen.",
        "IMBER: Do you know anyone at Quarrow Dental Supply?",
        "PELL: No. They're a supplier, that's all I know.",
        "IMBER: Have you ever used another person's login?",
        "PELL: Never."])
    with open(d / "refund-log-2024.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([BANNER])
        w.writerow(["Refund", "Approved", "Patient", "Amount", "Check", "Approved by user", "Workstation"])
        for rid, chk, day, name, amount in sorted(REFUNDS + [LEGIT], key=lambda r: r[0]):
            ws = "FRONT-2" if rid == LEGIT[0] else "MGR-01"
            w.writerow([rid, day.isoformat(), name, f"{amount:.2f}", chk, "phalloran", ws])
    with open(d / "patient-roster-export.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([BANNER])
        w.writerow(["Patient id", "Name", "Last visit"])
        for k, name in enumerate(["Paul Halloran", "Imogen Tarrant", "Basil Corrow", "Wynn Abernethy", "Lyra Dunmore",
                                  "Otto Prebble", "Fern Gallow", "Rufus Mayle"]):
            w.writerow([f"P-{3100 + k}", name, f"2024-0{1 + k % 4}-1{k}"])
    dcm.write_text_pdf(d / "it-access-review-2024-05-06.pdf", "IT access review", (
        "Workstation MGR-01 is the practice manager's computer in the back office; FRONT-2 is the front desk. "
        "The refund approvals R-1041 to R-1048 were all made from MGR-01. Priya Halloran's computer is FRONT-1. "
        "Remote access to the practice system is not enabled for any user."))
    for p in sorted(d.iterdir()):
        made.append(str(p.relative_to(out)))
    return made


def second_case() -> fb.CaseSpec:
    return fb.CaseSpec(CASE_TITLE, PEOPLE, [priya_phone(), pell_phone(), teague_phone()], ledger=False, seed=70)


def build_second(out: Path) -> dict:
    out = Path(out)
    manifest = fb.build_case(second_case(), out / "phones")
    manifest["statements"] = write_statements(out)
    manifest["documents"] = documents(out)
    manifest["banner"] = BANNER
    (out / "second-manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False))
    return manifest


if __name__ == "__main__":
    m = build_second(Path(sys.argv[1]))
    print(json.dumps({"case": m["case"], "phones": [{k: p.get(k) for k in ("label", "messages")} for p in m["phones"]],
                      "documents": len(m["documents"])}))
