"""Institution directory (docs/cellebrite/05 section 4.3.1): reviewed reference data naming financial institutions by
the channels a phone shows them through (app package, web domain, SMS sender, email domain).

The directory is a versioned data file, ``data/institution_directory.v<N>.json``; the highest version is used. An
entry is used only when a person has reviewed it: ``review.reviewed_by`` names a person (never a model) with
``reviewed_on``. A model may draft entries; a drafted entry carries ``review.reviewed_by = null`` and is never used
for matching (05 4.3.1 decision; the same rule as reviewed mappings, plan 6.5). The directory holds no evidence and no
case identifiers.

A person can also say in one case "this sender is this institution" (``phone_institution_aliases``, with a reason).
An alias names a directory entry, reviewed or drafted: the person's decision in the case is the review for that
channel value in that case. A drafted entry's parse templates are still not used (generic parse only).

Matching (4.3.1): an app package matches exactly; a web or email domain matches the entry's registrable domain or any
host under it, after lowercasing (``m.bank.example`` matches ``bank.example``; ``notbank.example`` does not); a short
code matches exact digits within the phone's country (unknown country: matched with ``country_unknown``); an
alphanumeric sender matches case-insensitively and exactly.
"""
from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass, field

from sqlalchemy import text

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
# a reviewer who is a model: a name made only of model or vendor words ("ChatGPT", "Claude 3", "GitHub Copilot",
# "Llama reviewer"); a person's name that contains one ("Claude Smith", "Ai Tanaka") is a person
_PRODUCTS = re.compile(r"(chatgpt|gpt[\w.-]*|claude[\w.-]*|openai|deepseek[\w.-]*|anthropic|gemini[\w.-]*|copilot|"
                       r"llama[\w.-]*|mistral[\w.-]*|grok[\w.-]*|llm|chatbot|bot|assistant|model)$", re.I)
_FILLER = re.compile(r"(\d[\w.]*|v\d[\w.]*|ai|github|microsoft|google|meta|xai|the|by|reviewer|review|pro|flash|"
                     r"opus|sonnet|haiku|fable|turbo|mini|large|small|instruct|chat)$", re.I)


class _ModelNames:
    """``search(name)``: truthy when the name is a model's, not a person's."""

    @staticmethod
    def search(name):
        words = re.findall(r"[\w.-]+", name or "")
        return bool(words) and any(_PRODUCTS.match(w) for w in words) and \
            all(_PRODUCTS.match(w) or _FILLER.match(w) for w in words)


MODEL_NAMES = _ModelNames()
KINDS = ("bank", "card_issuer", "payment_app", "remittance", "exchange", "crypto_exchange", "lender")
CHANNELS = ("app_package", "web_domain", "sms_sender", "email_domain")
_override = {"entries": None}


class DirectoryError(ValueError):
    pass


@dataclass(frozen=True)
class Match:
    institution_id: str
    display_name: str
    kind: str
    channel: str            # app_package | web_domain | sms_sender | email_domain
    via: str                # directory | alias
    reviewed: bool          # the entry itself is reviewed (its templates may be used)
    entry: dict = field(compare=False, repr=False, default_factory=dict)
    country_unknown: bool = False


def reviewed(entry: dict) -> bool:
    r = entry.get("review") or {}
    who = (r.get("reviewed_by") or "").strip()
    return bool(who) and bool(r.get("reviewed_on") or r.get("reviewed_at")) and not MODEL_NAMES.search(who)


def _validate(entry: dict, where: str) -> dict:
    for k in ("institution_id", "display_name", "kind"):
        if not str(entry.get(k) or "").strip():
            raise DirectoryError("%s: an entry needs %s" % (where, k))
    if not entry["institution_id"].startswith("inst:"):
        raise DirectoryError("%s: institution_id starts with inst:" % where)
    if entry["kind"] not in KINDS:
        raise DirectoryError("%s: kind is one of %s" % (where, ", ".join(KINDS)))
    who = ((entry.get("review") or {}).get("reviewed_by") or "").strip()
    if who and MODEL_NAMES.search(who):
        raise DirectoryError("%s: reviewed_by names a model (%s); only a person can review" % (where, who))
    for d in entry.get("currencies") or []:
        if not re.fullmatch(r"[A-Z]{3}", d):
            raise DirectoryError("%s: currencies are ISO 4217 codes" % where)
    return entry


def load(data_dir: str | None = None) -> dict:
    """``{"version", "sha256", "entries": [all entries], "reviewed": [used entries]}``."""
    import hashlib
    if _override["entries"] is not None:
        entries = [_validate(dict(e), "test entry %d" % i) for i, e in enumerate(_override["entries"])]
        raw = json.dumps(entries, sort_keys=True).encode()
        version = "test"
    else:
        files = sorted(glob.glob(os.path.join(data_dir or DATA_DIR, "institution_directory.v*.json")),
                       key=lambda p: int(re.search(r"\.v(\d+)\.json$", p).group(1)))
        if not files:
            return {"version": None, "sha256": None, "entries": [], "reviewed": []}
        with open(files[-1], "rb") as fh:
            raw = fh.read()
        doc = json.loads(raw)
        version = doc.get("version") or os.path.basename(files[-1])
        entries = [_validate(e, "%s entry %d" % (os.path.basename(files[-1]), i))
                   for i, e in enumerate(doc.get("entries") or [])]
    ids = [e["institution_id"] for e in entries]
    if len(ids) != len(set(ids)):
        raise DirectoryError("two entries share an institution_id")
    return {"version": version, "sha256": hashlib.sha256(raw).hexdigest(), "entries": entries,
            "reviewed": [e for e in entries if reviewed(e)]}


def use_entries(entries):
    """Tests: replace the directory with these entries (``None`` restores the data file)."""
    _override["entries"] = entries


def host_of(value: str | None) -> str | None:
    """The lowercased host of a URL, an email address or a bare domain (leading dots and a port removed)."""
    v = (value or "").strip().lower()
    if not v:
        return None
    if "@" in v and "://" not in v:
        v = v.rsplit("@", 1)[1]
    v = re.sub(r"^[a-z][a-z0-9+.-]*://", "", v)
    v = v.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    v = v.rsplit("@", 1)[-1].split(":", 1)[0].strip(".")
    return v if re.fullmatch(r"[a-z0-9.-]+\.[a-z0-9-]+", v) else None


def under(host: str | None, domain: str) -> bool:
    d = domain.strip().lower().strip(".")
    return bool(host) and (host == d or host.endswith("." + d))


def _short_code(sender: str) -> str | None:
    d = re.sub(r"[\s-]", "", sender or "")
    return d if re.fullmatch(r"\d{3,8}", d) else None


def _alphanumeric(sender: str) -> str | None:
    s = (sender or "").strip()
    return s.casefold() if re.fullmatch(r"(?=.*[A-Za-z])[A-Za-z0-9 ._&'-]{2,15}", s) else None


def sender_kind(sender: str | None) -> str | None:
    """``short_code`` or ``alphanumeric`` for an institution-style SMS sender; ``None`` for a personal number, an
    email address or nothing (05 test 5: the sender, never the SMSC, is the key)."""
    if not sender or "@" in sender:
        return None
    if _short_code(sender):
        return "short_code"
    if _alphanumeric(sender):
        return "alphanumeric"
    return None


class Directory:
    """The reviewed entries plus one case's aliases, with a match per channel."""

    def __init__(self, loaded: dict, aliases=()):
        self.loaded = loaded
        self.by_id = {e["institution_id"]: e for e in loaded["entries"]}
        self.used = loaded["reviewed"]
        self.aliases = {}
        for a in aliases:
            e = self.by_id.get(a["institution_id"])
            if e is not None:
                self.aliases[(a["channel"], a["value_normalised"])] = e

    def _m(self, e, channel, via, **kw):
        return Match(e["institution_id"], e["display_name"], e["kind"], channel, via, reviewed(e), e, **kw)

    def _alias(self, channel, value):
        e = self.aliases.get((channel, value))
        return self._m(e, channel, "alias") if e is not None else None

    def by_package(self, package: str | None):
        p = (package or "").strip()
        if not p:
            return None
        hit = self._alias("app_package", p.lower())
        if hit:
            return hit
        for e in self.used:
            if p in (e.get("app_packages") or []):
                return self._m(e, "app_package", "directory")
        return None

    def by_domain(self, value: str | None, channel="web_domain"):
        host = host_of(value)
        if not host:
            return None
        for (ch, v), e in self.aliases.items():
            if ch == channel and under(host, v):
                return self._m(e, channel, "alias")
        key = "email_domains" if channel == "email_domain" else "web_domains"
        for e in self.used:
            domains = list(e.get(key) or []) + (list(e.get("web_domains") or []) if channel == "email_domain" else [])
            if any(under(host, d) for d in domains):
                return self._m(e, channel, "directory")
        return None

    def by_sms_sender(self, sender: str | None, country: str | None):
        kind = sender_kind(sender)
        if kind is None:
            return None
        value = _short_code(sender) if kind == "short_code" else _alphanumeric(sender)
        hit = self._alias("sms_sender", value)
        if hit:
            return hit
        for e in self.used:
            for s in e.get("sms_senders") or []:
                if kind == "short_code" and _short_code(s.get("sender")) == value:
                    if country is None:
                        return self._m(e, "sms_sender", "directory", country_unknown=True)
                    if (s.get("country") or "").upper() == country.upper():
                        return self._m(e, "sms_sender", "directory")
                elif kind == "alphanumeric" and _alphanumeric(s.get("sender")) == value:
                    return self._m(e, "sms_sender", "directory")
        return None


def aliases(conn, case_id) -> list:
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT institution_id, channel, value_normalised, reason, actor, created_at FROM phone_institution_aliases "
        "WHERE case_id = :c ORDER BY channel, value_normalised"), {"c": str(case_id)})]


def normalise_alias(channel: str, value: str) -> str:
    if channel == "app_package":
        v = (value or "").strip().lower()
    elif channel in ("web_domain", "email_domain"):
        v = host_of(value) or ""
    elif channel == "sms_sender":
        v = _short_code(value) or _alphanumeric(value) or ""
    else:
        raise DirectoryError("A channel is one of %s." % ", ".join(CHANNELS))
    if not v:
        raise DirectoryError("That value cannot be read as a %s." % channel.replace("_", " "))
    return v


def add_alias(conn, case_id, *, institution_id, channel, value, reason, actor) -> dict:
    """A person's "this sender is this institution" in one case, with a reason. Replaces an earlier alias of the same
    channel value in the case."""
    import uuid
    if not (reason or "").strip():
        raise DirectoryError("Say why, in your own words.")
    if institution_id not in {e["institution_id"] for e in load()["entries"]}:
        raise DirectoryError("That institution is not in the directory.")
    v = normalise_alias(channel, value)
    conn.execute(text(
        "INSERT INTO phone_institution_aliases (id, case_id, institution_id, channel, value_normalised, reason, actor) "
        "VALUES (:i, :c, :inst, :ch, :v, :r, :a) ON CONFLICT (case_id, channel, value_normalised) DO UPDATE SET "
        "institution_id = EXCLUDED.institution_id, reason = EXCLUDED.reason, actor = EXCLUDED.actor, created_at = now()"),
        {"i": uuid.uuid4(), "c": str(case_id), "inst": institution_id, "ch": channel, "v": v, "r": reason.strip(),
         "a": actor})
    return {"institution_id": institution_id, "channel": channel, "value_normalised": v}


def for_case(conn, case_id) -> Directory:
    return Directory(load(), aliases(conn, case_id))
