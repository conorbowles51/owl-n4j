"""Seed the demo case's person-built items through the app's own routes, as the jobs login (lx-demo D).

    python3 evidence-engine/tests/phone/demo_seed.py stage1                 # dossiers, tasks, deadline, notes
    python3 evidence-engine/tests/phone/demo_seed.py stage2 [--draft]       # theories, pins, the proffer interview
                                                                            # (--draft: AI claim drafting from it)
    python3 evidence-engine/tests/phone/demo_seed.py machine-text           # the Media screen's batch reading:
                                                                            # image text and voice-note transcripts

Stage 1 needs nothing uploaded; stage 2 runs after the documents, statements and phones are read. Each step reads
first and adds only what is missing, so a rerun changes nothing. Every item is labelled as a seed entry. Drafted
claims and machine text stay labelled as model readings: nothing here confirms anything.

Signs in once with /root/.config/loupe-jobs/login (never printed) and keeps the token in a mode-600 file
($LX_DEMO_TOKEN, default ~/.cache/lx-demo-token.json), signing in again once on a 401. Demo case only.
"""
import json, os, sys, urllib.request, urllib.error

LOGIN = "/root/.config/loupe-jobs/login"
CACHE = os.environ.get("LX_DEMO_TOKEN", os.path.expanduser("~/.cache/lx-demo-token.json"))
C = "b75f3f2c-ffa1-4260-8fe9-6f5db4e9d4df"  # CASES.demo in frontend_v2/journeys/lib.mjs
SEED = "Seed entry for the demo case (lx-demo)."
STATE = os.environ.get("LX_DEMO_SEED_STATE", os.path.expanduser("~/.cache/lx-demo-seed.json"))
def login_fields():
    f = {}
    for line in open(LOGIN):
        if "=" in line:
            k, v = line.split("=", 1); f[k.strip()] = v.strip()
    return f

BASE = login_fields()["url"].rstrip("/")

def _signin():
    f = login_fields()
    req = urllib.request.Request(BASE + "/api/auth/login", data=json.dumps({"username": f["email"], "password": f["password"]}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    body = json.load(urllib.request.urlopen(req, timeout=60))
    tok = body.get("access_token")
    if not tok:
        raise SystemExit("sign-in gave no token (second step?)")
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    fd = os.open(CACHE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, json.dumps({"token": tok}).encode()); os.close(fd)
    return tok

def token():
    try:
        return json.load(open(CACHE))["token"]
    except Exception:
        return _signin()

def call(method, path, body=None, raw=None, ctype="application/json", retry=True):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + token(), **({"Content-Type": ctype} if data is not None else {})})
    try:
        r = urllib.request.urlopen(req, timeout=300)
        txt = r.read()
        return r.status, (json.loads(txt) if txt and txt[:1] in b"[{" else txt.decode(errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry:
            _signin(); return call(method, path, body, raw, ctype, retry=False)
        return e.code, e.read().decode(errors="replace")[:2000]

def ok(s, r, what):
    if s not in (200, 201):
        raise SystemExit(f"{what}: {s} {str(r)[:300]}")
    return s, r


def stage1():
    out = {}
    # Dossiers: one per person, with numbers, e-mails and addresses (all invented)
    people = [
        ("Mateo Ruiz", "Defendant. Owner of Ruiz Auto & Tire (garage and tow truck).",
         [("phone", "Mobile", "+1 443 555 0112"), ("email", "Personal", "mateo.ruiz@example.com"),
          ("address", "Garage", "Ruiz Auto & Tire, 4410 Calder Mill Road"), ("phone", "Garage", "+1 410 555 0110")]),
        ("Travis Kell", "State's cooperator (CW-1). Former shift supervisor at Brightwater Logistics, fired 20 April 2024. Tenant of bay 4.",
         [("phone", "Mobile", "+1 410 555 0121"), ("email", "Personal", "travis.kell@example.net"),
          ("address", "Home", "Larkmont Apartments 3C, 18 Wexmoor Court")]),
        ("Desmond Okafor", "Night loader at Brightwater Logistics. Two numbers and a Telegram account.",
         [("phone", "Mobile 1", "+1 410 555 0141"), ("phone", "Mobile 2", "+1 443 555 0142"), ("email", "Personal", "d.okafor@example.org")]),
        ("Brianna Cole", "Travis Kell's girlfriend. Storage unit 212 at Stowell Self Storage is in her name.",
         [("phone", "Mobile", "+1 443 555 0151"), ("email", "Personal", "bri.cole@example.com")]),
        ("Lena Marsh", "Contract night guard at Brightwater Logistics; the State's eyewitness.",
         [("phone", "Mobile", "+1 410 555 0161"), ("email", "Personal", "lena.marsh@example.net")]),
        ("Gary Penn", "Owner of Penn's Used Tools, Tessaly Quarry Lane.",
         [("phone", "Mobile", "+1 410 555 0171"), ("email", "Shop", "penn.tools@example.com"),
          ("address", "Shop", "Penn's Used Tools, 61 Tessaly Quarry Lane")]),
    ]
    s, r = ok(*call("GET", f"/api/dossiers?case_id={C}"), "list dossiers")
    have = {d.get("display_name"): d["id"] for d in r.get("dossiers", [])}
    out["dossiers"] = {}
    for name, summary, contacts in people:
        if name not in have:
            s, r = ok(*call("POST", "/api/dossiers", {"case_id": C, "display_name": name, "summary": summary + " " + SEED,
                                                       "contacts": [{"kind": k, "label": l, "value": v} for k, l, v in contacts]}),
                      f"dossier {name}")
            have[name] = r["id"]
        out["dossiers"][name] = have[name]

    # Tasks
    s, r = ok(*call("GET", f"/api/workspace/{C}/tasks"), "list tasks")
    titles = {t["title"] for t in r.get("tasks", [])}
    for title, desc in [("Subpoena Stowell Self Storage for unit 212", "Rental file, gate log and card on file. " + SEED),
                        ("Interview Harold Vint about the 12 April tow", "Confirm call time 22:31 and that Mateo stayed until 01:15. " + SEED),
                        ("Request the seventh extraction (E-7) from the State", "The discovery index lists E-7, a second handset from Kell's vehicle; disc 2 holds E-1 to E-6. " + SEED)]:
        if title not in titles:
            ok(*call("POST", f"/api/workspace/{C}/tasks", {"title": title, "description": desc}), f"task {title}")

    # Deadline
    s, r = ok(*call("GET", f"/api/cases/{C}/deadlines"), "list deadlines")
    if not any(d["name"].startswith("Motion to suppress") for d in r.get("deadlines", [])):
        ok(*call("POST", f"/api/cases/{C}/deadlines", {"name": "Motion to suppress and discovery motion due", "due_date": "2024-08-16"}), "deadline")

    # Notes
    s, r = ok(*call("GET", f"/api/notebook/{C}/notes"), "list notes")
    bodies = {n.get("title") for n in r.get("notes", [])}
    for title, body in [("Bay 4 lease predates the thefts", "Kell has rented bay 4 since 1 October 2023 at $650 a month. The State calls these payments the cooperator's cut. " + SEED),
                        ("Glovebox phone timing", "Check where the prepaid phone was before 8 June, the day Mateo towed Kell's car with Kell in the cab. " + SEED)]:
        if title not in bodies:
            ok(*call("POST", f"/api/notebook/{C}/notes", {"title": title, "body": body, "tags": ["demo-seed"]}), f"note {title}")

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(out, open(STATE, "w"), indent=1)
    print(json.dumps(out))


def stage2():
    D = json.load(open(STATE))["dossiers"]
    log = {}
    s, r = call("GET", f"/api/evidence?case_id={C}")
    ev = {f["original_filename"]: f["id"] for f in r["files"]}
    def E(name):
        return next(v for k, v in ev.items() if k.endswith(name))
    rows = []
    for off in range(0, 3000, 500):
        s, r = call("GET", f"/api/financial/ledger?case_id={C}&limit=500&offset={off}")
        rows += r.get("transactions", [])
        if len(r.get("transactions", [])) < 500:
            break
    def T(desc, date=None):
        for t in rows:
            if desc in (t.get("description") or "") and (date is None or t.get("transaction_date", "").startswith(date)):
                return str(t["key"])
        return None
    s, r = call("GET", f"/api/phones?case_id={C}")
    PH = {p["device"]["model"].split("PH")[1][0]: p["extraction_id"] for p in r["phones"]}

    def link(tt, tid, rel, label):
        return {"target_type": tt, "target_id": tid, "relationship": rel, "target_label": label} if tid else None

    theories = [
        ("T1 State's theory: Mateo Ruiz fenced the goods in bay 4",
         "The State says the goods went to bay 4 of Ruiz Auto & Tire after each theft and Mateo sold them on; the $650 monthly payments were his cut; the glovebox phone was his. " + SEED,
         [link("evidence", E("kell-proffer-transcript-2024-06-20.docx"), "supports", "Kell's proffer"),
          link("evidence", E("marsh-handwritten-statement-2024-06-12.pdf"), "supports", "Marsh's written statement"),
          link("evidence", E("state-cell-site-report.pdf"), "supports", "Cell-site opinion"),
          link("financial_transaction", T("KELL T BAY 4 RENT", "2024-04"), "supports", "$650 credit, 1 April"),
          link("evidence", E("bay4-lease-2023-10-01.pdf"), "contradicts", "Bay 4 lease from October 2023"),
          link("evidence", E("tow-invoice-1187-2024-04-12.pdf"), "contradicts", "Tow job on night N2"),
          link("evidence", E("er-discharge-2024-05-04.pdf"), "contradicts", "Emergency department on night N3"),
          link("evidence", E("search-inventory-ruiz-garage-2024-06-14.pdf"), "contradicts", "No stolen property in the garage"),
          link("phone_extraction", PH.get("1"), "contradicts", "Mateo's phone: no contact with Okafor")]),
        ("T2 Defence theory: Kell's operation; the glovebox phone entered the truck on 8 June",
         "Kell ran the thefts with Okafor and paid the guard; the goods went to storage unit 212 and through Penn's shop. The prepaid phone was Kell's: it sat with his phone in May and June and reached the tow truck when Mateo towed Kell's car on 8 June. " + SEED,
         [link("phone_extraction", PH.get("3"), "supports", "Glovebox phone"),
          link("phone_extraction", PH.get("2"), "supports", "Kell's phone"),
          link("evidence", E("tow-invoice-1242-2024-06-08.pdf"), "supports", "Tow of Kell's car, 8 June"),
          link("evidence", E("stowell-rental-agreement-unit-212.pdf"), "supports", "Unit 212 paid by Kell's card"),
          link("financial_transaction", T("CASH DEPOSIT BR 031"), "supports", "Cash deposit after N3"),
          link("financial_transaction", T("POCKETWIRE TO LENA MARSH", "2024-06"), "supports", "Payment to Marsh after N5"),
          link("phone_extraction", PH.get("5"), "supports", "Brianna's photos in unit 212"),
          link("evidence", E("state-cell-site-report.pdf"), "context", "Sector also covers Kell's apartment"),
          link("evidence", E("kell-proffer-transcript-2024-06-20.docx"), "contradicts", "Kell says the phone was Mateo's")]),
        ("T3 Desmond Okafor as the inside man",
         "Okafor's badge was in on every theft night, he set each night with Kell in the 'night crew' group and received $1,200 two days after each. " + SEED,
         [link("evidence", E("brightwater-badge-log-2024.csv"), "supports", "Badge B-20417 on every night"),
          link("phone_extraction", PH.get("4"), "supports", "Okafor's phone"),
          link("financial_transaction", T("POCKETWIRE TO DESMOND OKAFOR", "2024-03"), "supports", "$1,200 after N1"),
          link("dossier", D["Desmond Okafor"], "context", "Okafor's dossier"),
          link("evidence", E("kell-proffer-transcript-2024-06-20.docx"), "contradicts", "Kell: nobody at the warehouse helped")]),
    ]
    s, r = call("GET", f"/api/workspace/{C}/entries?entry_type=theory")
    have = {e.get("title") for e in r.get("entries", [])}
    log["theories"] = []
    for title, body, links in theories:
        links = [l for l in links if l]
        if title in have:
            continue
        s, r = call("POST", f"/api/workspace/{C}/entries", {"entry_type": "theory", "title": title, "body": body, "tags": ["demo-seed"], "links": links})
        log["theories"].append((title[:3], s, len(links), str(r)[:200] if s >= 300 else r.get("id")))

    # pins
    s, r = call("GET", f"/api/workspace/{C}/pinned")
    pinned = {str(p.get("item_id") or p.get("id")) for p in r.get("pinned_items", [])}
    for name in ("discovery-index-state.pdf", "state-cell-site-report.pdf", "kell-proffer-transcript-2024-06-20.docx"):
        if E(name) not in pinned:
            log.setdefault("pins", []).append(call("POST", f"/api/workspace/{C}/pinned?item_id={E(name)}")[0])

    # the proffer as an interview on Kell's dossier, then AI claim drafting from the document
    s, d = call("GET", f"/api/dossiers/{D['Travis Kell']}")
    interviews = d.get("interviews", []) if isinstance(d, dict) else []
    if not interviews:
        s, r = call("POST", f"/api/dossiers/{D['Travis Kell']}/interviews", {"interview_date": "2024-06-20", "participants": ["ASA M. Thorne", "Det. Sgt. P. Grennan", "Travis Kell", "counsel"],
                     "status": "completed", "working_notes": "Proffer session; transcript in evidence. " + SEED,
                     "evidence_links": [{"target_type": "evidence", "target_id": E("kell-proffer-transcript-2024-06-20.docx")}]})
        log["interview"] = (s, str(r)[:300])
        interviews = [r] if s in (200, 201) else []
    if interviews and "--draft" in sys.argv:
        s, r = call("POST", f"/api/pattern/{C}/claim-drafts", {"dossier_id": D["Travis Kell"], "subject": {"kind": "dossier", "dossier_id": D["Travis Kell"]},
                     "document_ids": [E("kell-proffer-transcript-2024-06-20.docx")]})
        log["draft"] = (s, str(r)[:600])
    print(json.dumps(log, indent=1, default=str))


def machine_text():
    for kind in ("transcript", "ocr"):
        s, r = call("POST", "/api/phones/media/derive-batches/describe", {"case_id": C, "kind": kind})
        print(kind, s, json.dumps(r)[:300])
        if s == 200 and r.get("eligible"):
            s, r = call("POST", "/api/phones/media/derive-batches",
                        {"case_id": C, "kind": kind, "scope_words": "All phones in the demo case (lx-demo seed)"})
            print(kind, s, json.dumps(r)[:300])


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    {"stage1": stage1, "stage2": stage2, "machine-text": machine_text}.get(step, lambda: sys.exit(__doc__))()
