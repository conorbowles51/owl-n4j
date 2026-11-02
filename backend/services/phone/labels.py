"""Who a participant is, on every phone line (docs/cellebrite/03 section 3.3; tests A1, A2, C-6, P-3).

Every label carries a name (or the explicit no-name form) and an identifier (or the owner form):

- ``Maria Lopez (+1 202-555-0143)``; ``Maria L (WhatsApp id 5521...@s.whatsapp.net)`` in full; an email as is;
- ``(no name on this phone) (+1 202-555-0143)``;
- ``Owner of C3: Name (+1 202-555-0100)``; ``Owner of C3 (number not in the extraction)``; an owner a person set
  carries ``Owner set by a person``;
- an identifier that could not be normalised is the captured value verbatim.

Phone view (default): the name the phone the record came from holds (its contact name, else the name in the record).
Case view: the reviewed person (dossier) name, with each phone's name in ``case_names``. The view changes labels
only, never rows or counts (D-8). On screen the arrow is drawn ``→``; in copied text and exports it is ``->``
(D-10).
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from services.phone import identities, readings

NO_NAME = "(no name on this phone)"
ARROW_TEXT = "->"
OWNER_SET_BADGE = "Owner set by a person"
APP_WORDS = {"whatsapp": "WhatsApp", "telegram": "Telegram", "signal": "Signal", "facebook": "Facebook",
             "messenger": "Messenger", "instagram": "Instagram", "skype": "Skype", "viber": "Viber",
             "snapchat": "Snapchat", "wechat": "WeChat", "line": "LINE", "apple": "Apple", "google": "Google"}
SENDER_ROLES = ("sender", "caller", "author", "original_sender")
RECIPIENT_ROLES = ("recipient", "cc", "bcc", "callee")


class LabelContext:
    """Everything a case's labels need, read once per request."""

    def __init__(self, conn, case_id, names_mode="phone"):
        self.conn, self.case_id, self.mode = conn, str(case_id), names_mode
        self.phone_labels = readings.phone_labels(conn, case_id)
        self.owners = {}
        for (ext,) in conn.execute(text("SELECT id FROM phone_extractions WHERE case_id = :c"), {"c": case_id}):
            o = identities.owner(conn, ext)
            self.owners[str(ext)] = {"keys": list(o.get("owner_identity_keys") or []),
                                     "basis": o.get("owner_basis"),
                                     "names": [c["name"] for c in o.get("candidates", [])
                                               if c["candidate_kind"] == "name" and c.get("name")]}
        self._ident, self._names, self._all_names, self._persons = {}, {}, defaultdict(list), {}

    # ---- loading -------------------------------------------------------------------------------------------------
    def load(self, keys):
        keys = sorted({k for k in keys if k and k not in self._ident})
        if not keys:
            return
        for r in self.conn.execute(text(
                "SELECT identity_key, kind, subkind, value_display, person_id FROM pv_identity WHERE case_id = :c AND "
                "identity_key = ANY(:k)"), {"c": self.case_id, "k": keys}):
            self._ident[r.identity_key] = dict(r._mapping)
        for k in keys:
            self._ident.setdefault(k, None)
        for r in self.conn.execute(text(
                "SELECT identity_key, extraction_id, name, basis, is_phone_name, occurrences FROM pv_identity_name "
                "WHERE case_id = :c AND identity_key = ANY(:k) ORDER BY is_phone_name DESC, occurrences DESC, name"),
                {"c": self.case_id, "k": keys}):
            ext = str(r.extraction_id)
            if r.is_phone_name and (r.identity_key, ext) not in self._names:
                self._names[(r.identity_key, ext)] = (r.name, r.basis)
        persons = {i["person_id"] for i in self._ident.values() if i and i.get("person_id")} - set(self._persons)
        if persons:
            for pid, name in self.conn.execute(text(
                    "SELECT id, display_name FROM case_profiles WHERE case_id = :c AND id = ANY(:p)"),
                    {"c": self.case_id, "p": list(persons)}):
                self._persons[pid] = name

    def owner_keys(self, extraction_id) -> list:
        return self.owners.get(str(extraction_id), {}).get("keys", [])

    def phone_label(self, extraction_id) -> str:
        return self.phone_labels.get(str(extraction_id), "Phone")

    # ---- one label -----------------------------------------------------------------------------------------------
    def label(self, extraction_id, *, identity_key=None, name_in_record=None, identifier_raw=None,
              is_phone_owner=None, role=None) -> dict:
        ext = str(extraction_id)
        owner = self.owners.get(ext, {"keys": [], "basis": None, "names": []})
        is_owner = bool(is_phone_owner) or role == "owner_implicit" or (identity_key in owner["keys"] if identity_key
                                                                         else False)
        key = identity_key
        if is_owner and not key and owner["keys"]:
            key = owner["keys"][0]
        self.load([key])
        ident = self._ident.get(key) if key else None
        phone_name = self._names.get((key, ext)) if key else None
        name, basis = None, "none"
        if phone_name:
            name, basis = phone_name[0], "contact_on_this_phone" if phone_name[1] in ("contact", "contact_entry") \
                else "name_in_record"
        elif name_in_record:
            name, basis = name_in_record, "name_in_record"
        elif is_owner and owner["names"]:
            name, basis = owner["names"][0], "name_in_record"
        case_names = []
        if self.mode == "case" and ident and ident.get("person_id") and ident["person_id"] in self._persons:
            name, basis = self._persons[ident["person_id"]], "case_person"
            self._load_all_names(key)
            case_names = [{"phone_label": self.phone_label(e), "name": n} for e, n in self._all_names[key]]
        if ident:
            identifier = {"kind": ident["kind"], "display": ident["value_display"], "subkind": ident.get("subkind"),
                          "captured": identifier_raw, "normalised": True}
        elif identifier_raw:
            identifier = {"kind": "other", "display": identifier_raw, "subkind": None, "captured": identifier_raw,
                          "normalised": False}
        else:
            identifier = None
        return {"identity_key": key, "name": name, "name_basis": basis, "identifier": identifier,
                "is_owner": is_owner, "owner_basis": owner["basis"] if is_owner else None,
                "phone_label": self.phone_label(ext) if is_owner else None, "case_names": case_names}

    def _load_all_names(self, key):
        if key in self._all_names:
            return
        for r in self.conn.execute(text(
                "SELECT extraction_id, name FROM pv_identity_name WHERE case_id = :c AND identity_key = :k AND "
                "is_phone_name ORDER BY extraction_id"), {"c": self.case_id, "k": key}):
            self._all_names[key].append((str(r.extraction_id), r.name))


def identifier_text(identifier) -> str | None:
    if not identifier:
        return None
    display = identifier["display"]
    if identifier["kind"] == "app_user":
        app = APP_WORDS.get((identifier.get("subkind") or "").split("_")[0].lower(), None)
        return "%s id %s" % (app, display) if app else "app id %s" % display
    return display


def label_text(label: dict) -> str:
    """The text form of one label (03 section 3.3 table); the same on screen, in copy and in exports."""
    ident = identifier_text(label.get("identifier"))
    name = label.get("name")
    if label.get("is_owner"):
        who = "Owner of %s" % (label.get("phone_label") or "this phone")
        if label.get("owner_basis") == "manual":
            who += " [%s]" % OWNER_SET_BADGE
        if not ident:
            return "%s%s (number not in the extraction)" % (who, ": %s" % name if name else "")
        return "%s: %s (%s)" % (who, name, ident) if name else "%s (%s)" % (who, ident)
    if not ident:
        return "%s (no identifier recorded)" % (name or NO_NAME)
    return "%s (%s)" % (name or NO_NAME, ident)


def line_text(sender: dict | None, recipients: list) -> str:
    """``Name (number) -> Name (number), Name (number)``."""
    left = label_text(sender) if sender else "(sender not recorded)"
    right = ", ".join(label_text(r) for r in recipients) if recipients else "(recipient not recorded)"
    return "%s %s %s" % (left, ARROW_TEXT, right)
