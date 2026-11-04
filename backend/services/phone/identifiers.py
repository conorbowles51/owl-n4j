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


# ---- Bluetooth identity (cb-coloc-rest B; 04 section 8.4 "the other phone's own Bluetooth identity") -------------

MAC_SHAPE = re.compile(r"^[0-9A-Fa-f]{2}([:\-. ]?[0-9A-Fa-f]{2}){5}$")
# The report header items that state the phone's own Bluetooth identity: the adapter address (Android
# ``Bluetooth MAC Address``, both platforms ``DeviceInfoBluetoothDeviceAddress``) and the name it advertises (Android
# ``DeviceInfoBluetoothDeviceName``; on an iPhone the Bluetooth name is the device name, ``DeviceInfoDeviceName``, read
# only when the report states no ``DeviceInfoBluetoothDeviceName``).
BLUETOOTH_HEADER_ITEMS = (("Bluetooth MAC Address", "bluetooth_address"),
                          ("DeviceInfoBluetoothDeviceAddress", "bluetooth_address"),
                          ("DeviceInfoBluetoothDeviceName", "bluetooth_name"),
                          ("DeviceInfoDeviceName", "bluetooth_name"))


def bluetooth_address(raw) -> Optional[str]:
    """``aa:bb:cc:dd:ee:ff`` for a written 48-bit address (colons, dashes, dots or none), else None."""
    s = str(raw or "").strip()
    if not MAC_SHAPE.match(s):
        return None
    h = re.sub(r"[^0-9a-f]", "", s.lower())
    if h in ("000000000000", "ffffffffffff") or h == "02" + "0" * 10:  # placeholders, never a device
        return None
    return ":".join(h[i:i + 2] for i in range(0, 12, 2))


def bluetooth_name(raw) -> Optional[str]:
    """A Bluetooth device name compared as written, after Unicode compatibility folding, case and spacing."""
    s = " ".join(unicodedata.normalize("NFKC", str(raw or "")).casefold().split())
    return s or None


def bluetooth(raw, subkind) -> Optional[Identifier]:
    """The phone's own Bluetooth address or name as an identity (kind ``other``; never a person)."""
    if subkind == "bluetooth_address":
        v = bluetooth_address(raw)
    elif subkind == "bluetooth_name":
        v = bluetooth_name(raw)
    else:
        raise ValueError(subkind)
    if v is None:
        return None
    return Identifier("other", subkind, v, str(raw).strip(), "other:%s:%s" % (subkind, v), None)


def bluetooth_peer(raw):
    """``("bluetooth_address", v)`` when a peer's written name is an address, else ``("bluetooth_name", v)``, or
    None: how a peer record on one phone is compared with another phone's own identity."""
    a = bluetooth_address(raw)
    if a:
        return ("bluetooth_address", a)
    n = bluetooth_name(raw)
    return ("bluetooth_name", n) if n else None
