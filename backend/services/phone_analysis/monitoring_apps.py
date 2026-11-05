"""Monitoring apps on a phone, as an indicator with its basis (agent-evidence-rest E; report, coercive control: "an
economic-abuse lane: bank control events beside monitoring-app installs and logins").

The list is a versioned data file, ``data/monitoring_apps.v<N>.json``, the highest version, like the institution
directory; each identifier keeps its source. A case edits it with ``phone_monitoring_app_entries``: a person adds an
identifier with its source, reviews a list entry, or sets one aside for this case with the reason. An edit changes what
is shown at once: nothing here is stored per phone and no analysis run is needed.

A file entry no person has reviewed is still shown, and says so. Unlike the institution directory, which feeds matching
and so waits for review, this list only raises an indicator a person weighs, and hiding it until review would hide the
sign. A match says what the identifier is listed as. It never says who installed the app, who used it, or why, and the
same app can be a parent's or an employer's: every indicator carries those limits. ``bank_control_events`` reads
notices on the phones in the same way: words of a notice, cited, never a finding that someone took control.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text

log = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LABEL = "Indicator, not a finding"
LIMITS = ("An app on this list says what the app is listed as. It does not show who installed it, who used it, or why; "
          "the same app can be a parent's or an employer's, and a listed identifier can be reused or synced from "
          "another device.")
ACTIONS = ("add", "reviewed", "set_aside")
BANK_WORDS = r"\b(?:bank|banking|card|acct|payee|beneficiary|debit|sort code|iban)\b"
CONTROL = [
    ("new_payee", re.compile(r"\b(?:new|added?)\s+(?:a\s+)?(?:payee|beneficiary|recipient)\b|\b(?:payee|beneficiary)\s+"
                             r"(?:was\s+|has been\s+)?added\b", re.I)),
    ("credentials_changed", re.compile(r"\b(?:password|passcode|pin|security details?|memorable word|login details?)\b"
                                       r"[^.\n]{0,40}\b(?:changed|reset|updated)\b", re.I)),
    ("new_device", re.compile(r"\b(?:new|unrecogni[sz]ed)\s+(?:device|phone|browser)\b[^.\n]{0,40}\b(?:added|registered|"
                              r"linked|signed in|logged in|login)\b|\b(?:device|phone)\s+(?:was\s+|has been\s+)?"
                              r"(?:added|registered|linked)\b", re.I)),
    ("card_stopped", re.compile(r"\bcard\b[^.\n]{0,40}\b(?:blocked|frozen|cancell?ed|stopped|replaced)\b", re.I)),
    ("limit_changed", re.compile(r"\b(?:daily |transfer |payment |spending )?limit\b[^.\n]{0,40}\b(?:changed|increased|"
                                 r"reduced|updated)\b", re.I)),
    ("contact_changed", re.compile(r"\b(?:mobile number|phone number|email address|e-mail address|postal address|"
                                   r"address)\b[^.\n]{0,40}\b(?:changed|updated)\b", re.I)),
    ("account_changed", re.compile(r"\b(?:joint holder|signatory|authori[sz]ed user)\b[^.\n]{0,40}\b(?:added|removed)\b|"
                                   r"\baccount\b[^.\n]{0,40}\b(?:closed|frozen|restricted|locked)\b", re.I)),
]
CONTROL_WORDS = {"new_payee": "a new payee", "credentials_changed": "changed sign-in details",
                 "new_device": "a new device", "card_stopped": "a card stopped or replaced",
                 "limit_changed": "a changed limit", "contact_changed": "changed contact details",
                 "account_changed": "a changed account or holder"}
_BANKISH = re.compile(BANK_WORDS, re.I)


class MonitoringError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status_code = status


def load(data_dir=None) -> dict:
    files = sorted(glob.glob(os.path.join(data_dir or DATA_DIR, "monitoring_apps.v*.json")),
                   key=lambda p: int(re.search(r"\.v(\d+)\.json$", p).group(1)))
    if not files:
        return {"version": None, "source": None, "entries": []}
    with open(files[-1], encoding="utf-8") as fh:
        return json.load(fh)


def _edits(session, case_id) -> list:
    from postgres.models.agent_evidence import PhoneMonitoringAppEntry as E
    return list(session.scalars(select(E).where(E.case_id == case_id, E.removed_at.is_(None))
                                .order_by(E.created_at, E.id)))


def effective_list(session, case_id, doc=None) -> dict:
    """``{identifier lower: {identifier, app, type, basis, reviewed, source, set_aside}}`` for this case."""
    doc = doc or load()
    src = doc.get("source") or {}
    base = "On the public list %s (%s, %s)" % (src.get("name"), src.get("license"), src.get("url"))
    out = {}
    for e in doc.get("entries") or []:
        for p in e["packages"]:
            out[p.lower()] = dict(identifier=p, app=e["name"], app_id=e["app_id"], type=e["type"], from_list=True,
                                  reviewed=False, set_aside=False, source=src.get("url"), edit_id=None,
                                  basis=base + "; no person has reviewed this entry.")
    for x in _edits(session, case_id):
        key = x.identifier.lower()
        if x.action == "add":
            out[key] = dict(identifier=x.identifier, app=x.label or x.identifier, app_id=None, type="added in this case",
                            from_list=False, reviewed=True, set_aside=False, source=x.source, edit_id=str(x.id),
                            basis="Added in this case by %s, source: %s. %s" % (x.created_by_name, x.source, x.reason))
        elif key in out:
            out[key] = dict(out[key], edit_id=str(x.id))
            if x.action == "reviewed":
                out[key].update(reviewed=True, basis="%s; reviewed in this case by %s: %s" % (
                    base, x.created_by_name, x.reason))
            else:
                out[key].update(set_aside=True, basis="Set aside in this case by %s: %s" % (x.created_by_name, x.reason))
    return out


def edit(session, *, case_id, identifier, action, reason, reviewer, label=None, source=None) -> dict:
    """A person's edit of the list for this case."""
    from postgres.models.agent_evidence import PhoneMonitoringAppEntry as E
    from services.financial.model_work import is_model
    if reviewer is None or is_model(reviewer):
        raise MonitoringError("A person edits this list.", 403)
    identifier = " ".join(str(identifier or "").split())
    reason = " ".join(str(reason or "").split())
    source = " ".join(str(source or "").split()) or None
    if action not in ACTIONS:
        raise MonitoringError("The edit is add, reviewed or set_aside.")
    if not identifier or len(identifier) > 255:
        raise MonitoringError("Give the app's identifier.")
    if not reason:
        raise MonitoringError("Say why.")
    if action == "add" and not source:
        raise MonitoringError("An added identifier names its source.")
    listed = identifier.lower() in {p.lower() for e in load().get("entries") or [] for p in e["packages"]}
    if action != "add" and not listed:
        raise MonitoringError("That identifier is not on the list.", 404)
    if any(x.identifier.lower() == identifier.lower() for x in _edits(session, case_id)):
        raise MonitoringError("This case already has an edit for that identifier; remove it first.", 409)
    row = E(id=uuid.uuid4(), case_id=case_id, identifier=identifier, label=(label or "").strip()[:255] or None,
            action=action, source=source, reason=reason[:4000], created_by_user_id=reviewer.id,
            created_by_name=reviewer.name)
    session.add(row)
    session.commit()
    return edit_out(row)


def remove(session, *, case_id, edit_id, reviewer) -> dict:
    from postgres.models.agent_evidence import PhoneMonitoringAppEntry as E
    from services.financial.model_work import is_model
    if reviewer is None or is_model(reviewer):
        raise MonitoringError("A person edits this list.", 403)
    row = session.get(E, edit_id)
    if row is None or row.case_id != case_id or row.removed_at is not None:
        raise MonitoringError("Not in this case.", 404)
    row.removed_at, row.removed_by_name = datetime.now(timezone.utc), reviewer.name
    session.commit()
    return edit_out(row)


def edit_out(x) -> dict:
    return dict(id=str(x.id), identifier=x.identifier, label=x.label, action=x.action, source=x.source, reason=x.reason,
                by=x.created_by_name, at=x.created_at.isoformat() if x.created_at else None,
                removed_by=x.removed_by_name, removed_at=x.removed_at.isoformat() if x.removed_at else None)


def list_summary(session, case_id) -> dict:
    doc = load()
    return dict(version=doc.get("version"), source=doc.get("source"), apps=len(doc.get("entries") or []),
                identifiers=sum(len(e["packages"]) for e in doc.get("entries") or []),
                edits=[edit_out(x) for x in _edits(session, case_id)])


def _installed(conn, case_id) -> tuple[list, dict]:
    """Every installed-application record of the active phones, and per phone whether the signal exists."""
    from services.phone_analysis import fields as FV
    phones = FV.active_phones(conn, case_id)
    records, coverage = [], {}
    for ext, label in phones.items():
        found = FV.field_values(conn, ext, ("InstalledApplication",), ("Identifier", "Name", "Version"))
        coverage[ext] = dict(phone=label, apps_read=sum(1 for r in found.values() if r["values"].get("Identifier")),
                             apps_on_phone=FV.type_counts(conn, ext, ("InstalledApplication",)).get(
                                 "InstalledApplication", 0))
        times = FV.times_for(conn, ext, list(found))
        for uid, r in found.items():
            ident = (r["values"].get("Identifier") or [None])[0]
            if ident:
                records.append(dict(record_uid=uid, extraction_id=ext, phone=label, identifier=ident,
                                    name=(r["values"].get("Name") or [None])[0],
                                    deleted_state=r.get("deleted_state"), times=times.get(uid) or {}))
    return records, coverage


def bank_control_events(conn, case_id) -> list:
    """Notices on the phones that say a bank detail changed: notifications, texts and emails whose words match
    ``CONTROL`` and name banking, each cited with its kind. Read by rule, with the sender as the phone records it."""
    from services.phone_analysis import institutions as INST
    from services.phone_analysis import money_signals as MS
    directory = INST.for_case(conn, case_id)
    phones = MS._phone_context(conn, case_id)
    out = []
    for s in MS.read_signals(conn, case_id):
        if s["model_type"] not in ("Notification", "InstantMessage", "Email"):
            continue
        phone = phones.get(s["extraction_id"]) or {}
        if s["model_type"] == "InstantMessage" and MS._is_owner(s.get("sender"), phone.get("owners", ())):
            continue  # the phone's own outgoing message is not a notice
        body = " ".join(str(v) for k, v in s["fields"].items() if k in ("Body", "Subject", "Snippet", "Title"))
        if not body.strip():
            continue
        kinds = [code for code, rx in CONTROL if rx.search(body)]
        if not kinds:
            continue
        sender = s.get("sender") or s["fields"].get("ServiceIdentifier") or s["fields"].get("Source")
        match = MS._institution_for(s, directory, phone.get("country"))
        if match is None and not _BANKISH.search(body):
            continue  # a password notice with no sign of a bank is not a bank event
        out.append(dict(record_uid=s["record_uid"], extraction_id=s["extraction_id"], instant=s["instant"],
                        kinds=kinds, sender=sender, institution=match.display_name if match else None,
                        deleted=s.get("deleted"), model_type=s["model_type"]))
    return out


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _in_window(when, start, end) -> bool:
    if when is None:
        return True  # no time: listed apart, never dropped by a window
    when = when.astimezone(timezone.utc) if getattr(when, "tzinfo", None) else when
    return (start is None or when >= start) and (end is None or when <= end)


def indicators(conn, session, case_id, *, start=None, end=None) -> dict:
    """Every monitoring-app match with its basis and every bank control notice, in one date-ordered lane. ``start`` and
    ``end`` (aware datetimes) leave out what falls outside and count it; an item with no time stays listed."""
    case_uuid = uuid.UUID(str(case_id))
    listed = effective_list(session, case_uuid)
    records, coverage = _installed(conn, case_id)
    apps, set_aside, outside = [], [], 0
    for r in records:
        hit = listed.get(r["identifier"].lower())
        if hit is None:
            continue
        instant = min(r["times"].values()) if r["times"] else None
        item = dict(kind="monitoring_app", rec="rec://%s" % r["record_uid"], phone=r["phone"], identifier=r["identifier"],
                    name_on_phone=r["name"], listed_as=hit["app"], listed_type=hit["type"], basis=hit["basis"],
                    reviewed=hit["reviewed"], source=hit["source"], at=_iso(instant),
                    at_field=min(r["times"], key=r["times"].get) if r["times"] else None,
                    deleted_state=r["deleted_state"], label=LABEL, limits=LIMITS)
        if hit["set_aside"]:
            set_aside.append(item)
        elif _in_window(instant, start, end):
            apps.append(dict(item, _at=instant))
        else:
            outside += 1
    events = []
    labels = {e: c["phone"] for e, c in coverage.items()}
    for e in bank_control_events(conn, case_id):
        if not _in_window(e["instant"], start, end):
            outside += 1
            continue
        events.append(dict(kind="bank_control", rec="rec://%s" % e["record_uid"], phone=labels.get(e["extraction_id"]),
                           notice=", ".join(CONTROL_WORDS[k] for k in e["kinds"]), notice_kinds=e["kinds"],
                           source_record=e["model_type"], sender=e["sender"], institution=e["institution"],
                           at=_iso(e["instant"]), label="The words of a notice on the phone, not a finding",
                           _at=e["instant"]))
    key = lambda x: (x["_at"] is None, x["at"] or "", x["rec"])  # noqa: E731
    lane = sorted(apps + events, key=key)
    for x in lane:
        del x["_at"]
    doc = load()
    apps_read = sum(c["apps_read"] for c in coverage.values())
    apps_on_phones = sum(c.get("apps_on_phone", c["apps_read"]) for c in coverage.values())
    unread = apps_on_phones - apps_read
    compared = ("Compared %d of the %d installed-application records on %d phones with the list%s" % (
        apps_read, apps_on_phones, len(coverage),
        " (%d carry no identifier, so they cannot be compared)" % unread if unread else "")) if listed else (
        "No monitoring-app list is installed and this case adds no identifier, so installed applications were not "
        "compared")
    return dict(label=LABEL, limits=LIMITS, list=dict(version=doc.get("version"), source=doc.get("source")),
                total=len(lane), monitoring_apps=len(apps), bank_control_notices=len(events), items=lane,
                set_aside=set_aside, outside_dates=outside, phones=list(coverage.values()),
                coverage=(compared + ", and read every notification, incoming text and email with the bank-notice "
                          "rule. A notice that names no bank, card or payee and comes from no known institution is "
                          "left out. A phone with no app records shows nothing here; that is no record, not no app."),
                not_read="A statement does not print these events, so they are read from notices on the phones only.")
