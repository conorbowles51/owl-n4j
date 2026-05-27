"""P2 — Forensic per-device export straight from the Cellebrite report XML.

WHY (2026-05-26): the Neo4j ingest collapses every sighting of a phone number
into ONE phone-keyed Person whose `name` is set ON CREATE only — so the first
saved name wins and all other names (other devices, SIMs, contact-vs-message
parties) are discarded at ingest (neo4j_writer._ensure_person, ~line 504).
There is no alias field, so those names are GONE from the graph. The report XML
is the source of truth. This script reads it directly (reusing the validated
parser, NO graph) and emits, PER DEVICE, an un-conflated forensic export:

  contacts.csv      one row per Contact record, exact Name + every number/email,
                    Source (phone book / SIM / app) + Account. No merge, no dedup.
  numbers_used.csv  identifiers that carry REAL traffic (the device's actually-
                    used SIMs/accounts + every counterparty), with sent/recv/call
                    counts and first/last-seen — "definitely used" = has traffic,
                    not merely listed in device-info (which over-harvests).
  aliases.csv       per identifier, EVERY distinct name it was ever saved/shown
                    as on this device — the conflation P3 will preserve, surfaced
                    now from real data ("all aliases for one number" view).
  comms.csv         ALL messages + calls, one row each: timestamp, direction
                    (owner-sent = Outgoing), app, counterparty identifier +
                    name-as-recorded, body/duration, folder, status.
  summary.txt       device identity (IMEI/MSISDN/IMSI/ICCID), owner numbers by
                    traffic, totals.

The number is always carried ALONGSIDE the name (requirement 6), and direction
is taken from the per-message IsPhoneOwner flag Cellebrite stamps on the sender
(requirement 5), falling back to the SMS Folder.

Run:
  sudo -u conorbowles51 venv/bin/python scripts/forensic_export.py [LABEL ...]
LABELS = C1 C1b C2 C3 C4 C5 C6 C7 C8 C9  (default: all). Output: data/forensic_export/<LABEL>/
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.append(str(ROOT / "ingestion" / "scripts"))

from cellebrite.parser import CellebriteXMLParser  # noqa: E402

CASE_DIR = ROOT / "ingestion" / "data" / "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"

# label -> report XML (the 10 devices). Discovered 2026-05-26.
REPORTS = {
    "C1":  "220049582_06305320_C1_2023-01-20_Report/220049582_06305320_C1_2023-01-20_Report_2025-03-18_Report.xml",
    "C1b": "C1-06304890_2022-11-15_Report/C1-06304890_2022-11-15_Report_2022-11-16_Report.xml",
    "C2":  "220049582_06306207_C2_2022-12-12_Report/220049582_06306207_C2_2022-12-12_Report_2025-03-19_Report.xml",
    "C3":  "220049582_06306208_C3_2022-12-12_Report/220049582_06306208_C3_2022-12-12_Report_2025-03-19_Report.xml",
    "C4":  "2026-05-04.12-40-21/220049582_06306369_C4_2022-12-12_Report/220049582_06306369_C4_2022-12-12_Report_2026-05-04_Report.xml",
    "C5":  "220049582_06306946_C5_2022-12-15_Report/220049582_06306946_C5_2022-12-15_Report_2025-03-19_Report.xml",
    "C6":  "220049582_06306962_C6_2022-12-14_Report/220049582_06306962_C6_2022-12-14_Report_2026-05-12_Report.xml",
    "C7":  "220049582_06306964_C7_2022-12-17_Report/220049582_06306964_C7_2022-12-17_Report_2026-05-04_Report.xml",
    "C8":  "C8 XMLReport/220049582_06308586_C8_2023-01-18_Report (1)/220049582_06308586_C8_2023-01-18_Report (1)_2026-05-06_Report.xml",
    "C9":  "220029502_06310028_C9_2023-03-02_Report/220029502_06310028_C9_2023-03-02_Report_2025-03-20_Report.xml",
}

_TS_FIELDS = ("TimeStamp", "Timestamp", "StartTime", "DateDelivered", "Date",
              "TimeCreated", "LastActivity", "EndTime")


def _ts(model):
    for f in _TS_FIELDS:
        v = model.get_field(f)
        if v:
            return v
    return ""


def _entries(contact):
    """(phones, emails, user_ids) exactly as listed on a Contact, no canonicalising."""
    phones, emails, uids = [], [], []
    for e in contact.multi_model_fields.get("Entries", []):
        et = e.model_type or ""
        val = e.get_field("Value") or e.get_field("Identifier")
        if not val:
            continue
        if et == "PhoneNumber":
            phones.append(val)
        elif et == "EmailAddress":
            emails.append(val)
        elif et == "UserID":
            uids.append(val)
        else:
            cat = (e.get_field("Category") or "").lower()
            (emails if "mail" in cat else phones).append(val)
    return phones, emails, uids


class DeviceExport:
    def __init__(self, label, xml_path):
        self.label = label
        self.xml_path = xml_path
        self.parser = CellebriteXMLParser(str(xml_path))
        self.report = self.parser.parse_header()
        # per-identifier traffic + names seen
        self.sent = defaultdict(int)      # owner-sent messages keyed by owner id
        self.recv = defaultdict(int)      # messages received from this id
        self.calls = defaultdict(int)
        self.names = defaultdict(set)     # id -> {every name seen}
        self.first = {}                   # id -> earliest ts
        self.last = {}                    # id -> latest ts
        self.owner_traffic = defaultdict(int)  # ids flagged IsPhoneOwner
        self.outdir = ROOT / "data" / "forensic_export" / label
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.n_contacts = self.n_msgs = self.n_calls = 0

    def _seen(self, ident, name, ts):
        if not ident:
            return
        if name:
            self.names[ident].add(name)
        if ts:
            if ident not in self.first or ts < self.first[ident]:
                self.first[ident] = ts
            if ident not in self.last or ts > self.last[ident]:
                self.last[ident] = ts

    def run(self):
        cw = csv.writer(open(self.outdir / "contacts.csv", "w", newline=""))
        cw.writerow(["contact_name", "phone_numbers", "emails", "user_ids",
                     "source", "account", "type", "group"])
        mw = csv.writer(open(self.outdir / "comms.csv", "w", newline=""))
        mw.writerow(["timestamp", "kind", "direction", "app",
                     "counterparty_number", "counterparty_name", "owner_id",
                     "body_or_duration", "folder", "status"])

        for batch in self.parser.stream_models(batch_size=500):
            for m in batch:
                t = m.model_type
                if t == "Contact":
                    self._contact(m, cw)
                elif t == "Call":
                    self._call(m, mw)
                elif t == "InstantMessage":
                    self._msg(m, mw)
                elif t == "Chat":
                    parts = m.get_parties("Participants")
                    chat_name = m.get_field("Name") or ""
                    # counterparty(ies) = non-owner participants. 1:1 chat → the
                    # other party; group chat (>2) → the chat name/thread.
                    non_owner = [p for p in parts if not p.is_phone_owner and p.identifier]
                    for msg in m.multi_model_fields.get("Messages", []):
                        self._msg(msg, mw, chat_non_owner=non_owner,
                                  chat_name=chat_name, chat_size=len(parts))
                elif t == "Email":
                    self._email(m, mw)
        self._numbers_and_aliases()
        self._summary()

    def _contact(self, m, cw):
        name = m.get_field("Name") or ""
        phones, emails, uids = _entries(m)
        cw.writerow([name, " | ".join(phones), " | ".join(emails), " | ".join(uids),
                     m.get_field("Source") or "", m.get_field("Account") or "",
                     m.get_field("Type") or "", m.get_field("Group") or ""])
        for p in phones:
            self._seen(p, name, "")
        self.n_contacts += 1

    def _call(self, m, mw):
        ts = _ts(m)
        direction = m.get_field("Direction") or ""
        dur = m.get_field("Duration") or ""
        app = m.get_field("Source") or "Phone"
        frm = m.get_party("From")
        to = m.get_party("To")
        # owner side vs counterparty
        owner_party = frm if (frm and frm.is_phone_owner) else (to if (to and to.is_phone_owner) else None)
        cp = to if owner_party is frm else frm
        if owner_party and owner_party.identifier:
            self.owner_traffic[owner_party.identifier] += 1
            self._seen(owner_party.identifier, owner_party.name, ts)
        cp_id = cp.identifier if cp else ""
        cp_nm = cp.name if cp else ""
        if cp_id:
            self.calls[cp_id] += 1
            self._seen(cp_id, cp_nm, ts)
        mw.writerow([ts, "call", direction, app, cp_id, cp_nm,
                     owner_party.identifier if owner_party else "", dur, "", m.get_field("Status") or ""])
        self.n_calls += 1

    def _msg(self, m, mw, chat_non_owner=None, chat_name="", chat_size=0):
        ts = _ts(m)
        app = m.get_field("Source") or m.get_field("SourceApplication") or ""
        folder = m.get_field("Folder") or ""
        body = (m.get_field("Body") or "").replace("\n", " ").replace("\r", " ")
        frm = m.get_party("From")
        to = m.get_party("To")
        # direction: owner-sent = Outgoing (per-message IsPhoneOwner flag), else folder
        if frm and frm.is_phone_owner:
            direction = "Outgoing"
        elif folder in ("Sent", "Outbox"):
            direction = "Outgoing"
        elif folder == "Inbox":
            direction = "Incoming"
        elif frm and frm.identifier:
            direction = "Incoming"
        else:
            direction = ""
        if direction == "Outgoing":
            owner_party, cp = frm, to
        else:
            owner_party, cp = to, frm
        if owner_party and owner_party.identifier and owner_party.is_phone_owner:
            self.owner_traffic[owner_party.identifier] += 1
            self._seen(owner_party.identifier, owner_party.name, ts)
        cp_id = cp.identifier if cp else ""
        cp_nm = cp.name if cp else ""
        # App messages (WhatsApp/Telegram) carry only a From party — for the
        # owner's OUTGOING messages the To is empty. Recover the counterparty
        # from the parent Chat: the non-owner participant(s). Group chats (>2)
        # → label by chat name/thread so the row still attributes correctly.
        if not cp_id and chat_non_owner is not None:
            if chat_size > 2:
                cp_id = "(group) " + (chat_name or f"{chat_size}-party chat")
                cp_nm = chat_name or "(group chat)"
            elif len(chat_non_owner) == 1:
                cp_id = chat_non_owner[0].identifier
                cp_nm = chat_non_owner[0].name or ""
        if cp_id:
            if direction == "Outgoing":
                self.sent[cp_id] += 1
            else:
                self.recv[cp_id] += 1
            self._seen(cp_id, cp_nm, ts)
        mw.writerow([ts, "message", direction, app, cp_id, cp_nm,
                     owner_party.identifier if owner_party else "",
                     body[:500], folder, m.get_field("Status") or ""])
        self.n_msgs += 1

    def _email(self, m, mw):
        ts = _ts(m)
        frm = m.get_party("From")
        to = m.get_party("To")
        cp = frm if not (frm and frm.is_phone_owner) else to
        cp_id = cp.identifier if cp else ""
        cp_nm = cp.name if cp else ""
        if cp_id:
            self._seen(cp_id, cp_nm, ts)
        mw.writerow([ts, "email", "", "Email", cp_id, cp_nm, "",
                     (m.get_field("Subject") or "")[:200], "", ""])

    def _numbers_and_aliases(self):
        # every id that touched traffic
        ids = set(self.sent) | set(self.recv) | set(self.calls) | set(self.owner_traffic)
        nw = csv.writer(open(self.outdir / "numbers_used.csv", "w", newline=""))
        nw.writerow(["identifier", "is_owner", "owner_sent", "msgs_sent_to",
                     "msgs_recv_from", "calls", "names_seen", "first_seen", "last_seen"])
        for i in sorted(ids, key=lambda x: -(self.owner_traffic.get(x, 0) + self.sent.get(x, 0) + self.recv.get(x, 0) + self.calls.get(x, 0))):
            nw.writerow([i, "Y" if self.owner_traffic.get(i) else "",
                         self.owner_traffic.get(i, 0), self.sent.get(i, 0),
                         self.recv.get(i, 0), self.calls.get(i, 0),
                         " | ".join(sorted(self.names.get(i, []))),
                         self.first.get(i, ""), self.last.get(i, "")])
        aw = csv.writer(open(self.outdir / "aliases.csv", "w", newline=""))
        aw.writerow(["identifier", "distinct_name_count", "all_names_seen"])
        for i in sorted(self.names, key=lambda x: -len(self.names[x])):
            nm = sorted(n for n in self.names[i] if n)
            if nm:
                aw.writerow([i, len(nm), " | ".join(nm)])

    def _summary(self):
        di = self.report.device_info
        owners = sorted(((i, n) for i, n in self.owner_traffic.items() if n > 0),
                        key=lambda kv: -kv[1])
        with open(self.outdir / "summary.txt", "w") as f:
            f.write(f"DEVICE {self.label} — {self.report.report_name}\n")
            f.write(f"  IMEI:  {di.imei}\n")
            f.write(f"  MSISDN (device-info, over-harvested): {di.msisdn}\n")
            f.write(f"  IMSI:  {getattr(di, 'imsi', None)}\n")
            f.write(f"  ICCID: {di.iccid}\n")
            f.write(f"  model: {di.device_model}  os: {di.os_type}\n\n")
            f.write("OWNER NUMBERS/ACCOUNTS BY ACTUAL TRAFFIC (IsPhoneOwner-flagged sends):\n")
            for ident, n in owners[:15]:
                names = " | ".join(sorted(self.names.get(ident, []))) or "(no name)"
                f.write(f"  {ident:<28} owner-sent={n:<8} names: {names}\n")
            f.write(f"\nTOTALS: contacts={self.n_contacts}  messages={self.n_msgs}  calls={self.n_calls}\n")
        print(f"[{self.label}] contacts={self.n_contacts} msgs={self.n_msgs} "
              f"calls={self.n_calls} -> {self.outdir}")


def main():
    labels = [a for a in sys.argv[1:] if a in REPORTS] or list(REPORTS)
    for label in labels:
        xml = CASE_DIR / REPORTS[label]
        if not xml.exists():
            print(f"[{label}] MISSING xml: {xml}")
            continue
        DeviceExport(label, xml).run()


if __name__ == "__main__":
    main()
