"""Identifier normalisation (docs/cellebrite/02 section 8.2): one function, ``classify``.

Rules, first match wins: P1 WhatsApp user JID (a valid number's JID is that number's identity), P2 WhatsApp
group JID (never a person), E1 email, P3 a written number, P4 a short code, A1 an app user, N1 a display name only
(no identity). Raw values are never discarded: the sighting keeps ``identifier_raw``.
"""
from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple, Optional

from services.phone import numbers

JID_USER = re.compile(r"^\+?(\d{7,15})@(s\.whatsapp\.net|c\.us)$", re.I)
JID_GROUP = re.compile(r"^.+@g\.us$", re.I)
NUMBER_SHAPE = re.compile(r"^[\d+()\-./ ]+$")
SHORT_CODE = re.compile(r"^\d{3,8}$")


class Identifier(NamedTuple):
    kind: str
    subkind: Optional[str]
    value_normalised: str
    value_display: str
    identity_key: str
    region_basis: Optional[str]


def slug(text):
    s = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"[^0-9a-z]+", "-", s).strip("-")


def classify(raw, *, context=None, region="US", region_basis="assumed_default") -> Optional[Identifier]:
    """``context``: {"app": the top-level record's Source, "category": UserID.Category, "name_only": bool}."""
    ctx = context or {}
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip()
    m = JID_USER.match(s)
    if m:  # P1
        e164, display, valid, _ = numbers.parse("+" + m.group(1), None, "explicit_plus")
        if valid:
            return Identifier("phone", "whatsapp_jid", e164, display, "phone:" + e164, "explicit_plus")
        v = s.lower()
        return Identifier("app_user", "whatsapp_jid", v, s, "app:whatsapp:jid:" + v, None)
    if JID_GROUP.match(s):  # P2
        v = s.lower()
        return Identifier("other", "group", v, s, "other:whatsapp_group:" + v, None)
    e = s[7:] if s.lower().startswith("mailto:") else s
    if e.count("@") == 1 and "." in e.split("@")[1] and not any(c.isspace() for c in e):  # E1
        v = e.lower()
        return Identifier("email", None, v, v, "email:" + v, None)
    if not any(c.isalpha() for c in s) and NUMBER_SHAPE.match(s):
        digits = re.sub(r"\D", "", s)
        if 7 <= len(digits) <= 17:  # P3
            e164, display, valid, basis = numbers.parse(s, region, region_basis)
            if valid:
                return Identifier("phone", None, e164, display, "phone:" + e164, basis)
            return Identifier("other", "digits_unverified", digits, s, "other:digits:" + digits, basis)
        if SHORT_CODE.match(s):  # P4
            return Identifier("other", "short_code", s, s, "other:short_code:" + s, None)
    if ctx.get("name_only"):  # N1
        return None
    namespace = slug(ctx.get("app")) or "unknown-app"  # A1
    label = slug(ctx.get("category")) or "id"
    v = s
    if label == "username":
        v = v.casefold().lstrip("@")
    return Identifier("app_user", label, v, s, "app:%s:%s:%s" % (namespace, label, v), None)
