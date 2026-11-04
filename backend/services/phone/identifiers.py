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


# A phone's factory-default Bluetooth name is its product or model name, which every phone of that model shares
# (followups m110415502629705; measured 4 Nov: 2 of the 3 live phones stating their own Bluetooth name advertise
# one, "galaxy a02s" and "moto g play - 2023"). Such a name is never compared: a scan that saw any phone of that
# model would otherwise read as this phone. A brand or product word followed only by model tokens (a token with a
# digit, a single letter, or a model word) is a default; a name with any other word ("Sam's iPhone") is not.
_DEFAULT_BRANDS = (
    "iphone", "ipad", "ipod", "apple watch", "airpods", "galaxy", "samsung galaxy", "samsung", "pixel",
    "google pixel", "moto", "motorola", "redmi", "xiaomi", "oneplus", "huawei", "honor", "oppo", "vivo", "realme",
    "nokia", "lg", "xperia", "sony xperia", "android", "nothing phone", "tcl", "zte", "alcatel")
_DEFAULT_MODEL_WORDS = frozenset((
    "pro", "max", "plus", "mini", "ultra", "lite", "note", "edge", "play", "power", "stylus", "fold", "flip", "fe",
    "se", "xl", "xr", "xs", "x", "e", "a", "s", "z", "g", "tab", "touch", "nord", "neo", "prime", "go", "core",
    "mate", "nova", "reno", "find", "5g", "4g", "lte", "-", "+"))


def default_device_name(name, models=()) -> bool:
    """True when a Bluetooth name (``bluetooth_name`` form) is a factory default: one of the phone's own model names
    from its report header (``models``, compared in the same form), or a product name such as "iphone" or
    "galaxy s21 ultra"."""
    n = bluetooth_name(name)
    if not n:
        return False
    if n in {bluetooth_name(m) for m in models if m}:
        return True
    for brand in sorted(_DEFAULT_BRANDS, key=len, reverse=True):
        if n == brand or n.startswith(brand + " "):
            rest = n[len(brand):].replace("(", " ").replace(")", " ").split()
            return all(any(ch.isdigit() for ch in t) or t in _DEFAULT_MODEL_WORDS or len(t) == 1 for t in rest)
    return False


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
