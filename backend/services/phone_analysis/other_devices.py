"""Approach 6: other devices and accounts in play (docs/cellebrite/05 section 9; unit 05-S9b, cb-gated-spread).

Which other devices (Bluetooth peers, WiFi networks), accounts, saved logins and services each phone shows contact
with, when each was first and last seen, and which of them more than one phone in the case shares.

Built on every case with no count gate (Neil 2026-11-04: "If there are any payment matches at all they should be
mentioned. With a signal strength showing the user how well matched something is and how heavily substantiated. We
don't want to miss things based on an arbitrary cutoff."). The old build gate (5 strong shared keys in a case) is
gone: every key on two or more phones is listed, with its strength and the reasons for it, and the screen states the
true counts by strength.

Kinds:

- ``shared_key``: one key on two or more phones of the case (9.3 step 2). Never merged into an identity and never
  added into a total of anything else (05 3.5; decision 3 of the brief).
- ``service_without_app``: a service the phone shows by cookie, saved login or account where no installed
  application for it exists (9.3 step 3). On a phone without ``InstalledApplication`` records the comparison is not
  made and the phone's inventory says so.
- ``remote_session``: a remote service session (9.3 step 4), the user agent read by the offline rule in
  ``user_agent_family``.
- ``phone_inventory``: per phone, distinct keys by kind with first and last seen (9.3 step 1, 9.4 "devices and
  accounts panel per phone").

Keys (9.3 step 1; normalised inside the backend):

- ``wifi_bssid``: ``WirelessNetwork.BSSId``, lower case colon form; ``ssid``: ``WirelessNetwork.SSId`` as written,
  case folded (a network name, many places share one).
- ``bluetooth_address``: a hardware address (``xx:xx:xx:xx:xx:xx``) in a ``RecognizedDevice``'s nested identifiers;
  ``bluetooth_name``: ``DeviceConnectivity.DeviceName`` and ``RecognizedDevice.Name``, case folded. The natures
  (Connected, Detected, Disconnected, Paired) are kept per phone: a peer only ever Detected is "nearby, not
  connected" (9.5).
- ``owner_number``, ``iccid``, ``imsi``, ``account``, ``saved_login``: read by approach 5's ``device_users.markers``
  (reused, not duplicated).
- ``service``: the registrable domain of ``Cookie.Domain``, ``Password.Service`` / ``Server`` where it is a host
  name, ``UserAccount.ServiceIdentifier`` where it is a host name (``registrable_domain``: the last two labels, or
  three when the second-level label is a common public second level such as ``co.uk``; a rule of thumb, no public
  suffix list is installed on the server).

Strength of a shared key (one scale with approach 1's matches: strong, moderate, weak, faint; a rule computes it,
never a model). Reasons come in two parts, as approach 1's: ``match`` (how well the keys match) and
``substantiation`` (how much each phone holds behind it).

- Match: a hardware or subscriber identifier (BSSID, Bluetooth address, owner number, ICCID, IMSI) is ``strong``
  (05 9.3 step 2: "strong for BSSID and Bluetooth address"); a username on one named service (account, saved login)
  is ``moderate`` (05 19.S8-c "medium"); a name or a service domain (SSID, Bluetooth name, service) is ``weak`` (9.3
  step 2: "weak for names and SSIDs (common names)").
- One level lower, never below faint: a Bluetooth key that some phone only detected nearby and never connected to;
  a weak key that more than half of the case's phones hold when the case has three or more phones (a common name).
  These two adjustments are rules of thumb: no measurement sets them.

Every list states its total. The records behind one result are stored up to ``RECORDS_PER_PHONE`` per phone, and
the result states every phone's full count.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from sqlalchemy import text

from services.phone_analysis import fields as FV

CODE = "other_devices"
VERSION = "6.2"
PARAMETERS = {}
VERSION_SOURCES = ("device_users",)  # approach 5's markers are read as they are
KINDS = ("shared_key", "service_without_app", "remote_session", "phone_inventory")
LEVELS = ("strong", "moderate", "weak", "faint")
SUPPORTS = ("match_identifier", "match_username", "match_name", "records_each_side", "connected_each_side",
            "service_present", "no_app_found", "session_recorded", "inventory")
UNDERCUTS = ("detected_not_connected", "names_not_unique", "ssid_repeats", "common_key", "synced_account",
             "app_match_by_name", "no_app_data", "user_agent_rule")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
RECORDS_PER_PHONE = 50
RULE_OF_THUMB = ("The strength levels are rules of thumb: a hardware identifier matches strongly, a username on one "
                 "service moderately, a name weakly; no measurement on this case set them.")
STRENGTH_RULE = {"strong": "a hardware or subscriber identifier", "moderate": "a username on one named service",
                 "weak": "a name or a service domain", "faint": "a name only nearby or common to most phones"}

# kind -> (match level, words singular, words plural)
KEY_KINDS = {
    "wifi_bssid": ("strong", "WiFi access point (BSSID)", "WiFi access points (BSSID)"),
    "bluetooth_address": ("strong", "Bluetooth device address", "Bluetooth device addresses"),
    "owner_number": ("strong", "owner phone number", "owner phone numbers"),
    "iccid": ("strong", "SIM card number (ICCID)", "SIM card numbers (ICCID)"),
    "imsi": ("strong", "SIM subscriber number (IMSI)", "SIM subscriber numbers (IMSI)"),
    "account": ("moderate", "account username on one service", "account usernames on one service"),
    "saved_login": ("moderate", "saved-login account on one service", "saved-login accounts on one service"),
    "ssid": ("weak", "WiFi network name (SSID)", "WiFi network names (SSID)"),
    "bluetooth_name": ("weak", "Bluetooth device name", "Bluetooth device names"),
    "service": ("weak", "service (web domain)", "services (web domains)"),
}
# shown on screen: the key's value is shown for networks, devices and services, not for numbers, SIMs or usernames
# (those are compared inside the backend and opened from the records, as approach 5 does)
SHOW_VALUE = ("wifi_bssid", "bluetooth_address", "ssid", "bluetooth_name", "service")
SIGNALS = [
    {"code": "networks", "label": "WiFi networks"},
    {"code": "bluetooth", "label": "Bluetooth devices"},
    {"code": "accounts", "label": "Accounts, saved logins or SIM and number records"},
    {"code": "services", "label": "Web services (cookies, saved logins, accounts)"},
    {"code": "apps", "label": "Installed applications"},
]
_last = {"counts": {}}
_MAC = re.compile(r"\b([0-9a-f]{2}(?:[:-][0-9a-f]{2}){5})\b", re.I)
_HEX = re.compile(r"[^0-9a-f]")
_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
# common public second-level labels (a rule of thumb; no public suffix list on the server)
_SECOND_LEVEL = {"co", "com", "net", "org", "gov", "ac", "edu", "ltd", "plc", "me", "gob", "nic"}
CONNECTED = ("Connected", "Paired", "Disconnected")


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def norm_bssid(v):
    h = _HEX.sub("", str(v or "").lower())
    return ":".join(h[i:i + 2] for i in range(0, 12, 2)) if len(h) == 12 and h != "0" * 12 else None


def registrable_domain(v):
    """The registrable domain of a host name or URL (rule of thumb), or None when it is not a host name."""
    s = str(v or "").strip().lower()
    if not s:
        return None
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s).split("/", 1)[0].split(":", 1)[0].lstrip(".")
    if not _HOST.match(s) or re.fullmatch(r"[0-9.]+", s):
        return None
    parts = s.split(".")
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def user_agent_family(ua):
    """(device family, OS) from a user agent by a fixed offline rule (no parser library is installed); either may be
    None."""
    s = str(ua or "")
    os_ = None
    for pat, name in ((r"iPhone|iPad|iOS", "iOS"), (r"Android", "Android"), (r"Windows", "Windows"),
                      (r"Mac OS X|Macintosh", "macOS"), (r"CrOS", "ChromeOS"), (r"Linux", "Linux")):
        if re.search(pat, s):
            os_ = name
            break
    fam = None
    for pat, name in ((r"iPad", "Tablet"), (r"Tablet", "Tablet"), (r"iPhone|Mobile|Android", "Phone"),
                      (r"Windows|Macintosh|X11|CrOS", "Computer")):
        if re.search(pat, s):
            fam = name
            break
    return fam, os_


def _digest(kind, n):
    return hashlib.sha256(("%s|%s" % (kind, n)).encode()).hexdigest()


class _Inv:
    """One phone's keys: ``{(kind, digest): {"display", "records": [(uid, field)], "natures", "first", "last",
    "events"}}``."""

    def __init__(self):
        self.keys = {}

    def add(self, kind, normalised, display, uid, field, nature=None, when=None):
        if not normalised:
            return
        k = (kind, _digest(kind, normalised))
        item = self.keys.get(k)
        if item is None:
            item = self.keys[k] = {"display": display, "records": [], "natures": set(), "first": None, "last": None,
                                   "events": 0}
        item["events"] += 1
        if uid and (uid, field) not in item["records"]:
            item["records"].append((uid, field))
        if nature:
            item["natures"].add(nature)
        if when is not None:
            item["first"] = when if item["first"] is None or when < item["first"] else item["first"]
            item["last"] = when if item["last"] is None or when > item["last"] else item["last"]


def _first_time(times, uid, names):
    for n in names:
        t = (times.get(uid) or {}).get(n)
        if t is not None:
            return t
    return None


def inventory(conn, ext) -> tuple:
    """(``_Inv``, facts) for one phone. Facts: ``has_apps``, app names and identifiers (folded), sessions."""
    from services.phone_analysis import device_users as U
    inv = _Inv()
    # approach 5's markers (owner number, ICCID, IMSI, account, saved login): reused as they are
    for (kind, digest), uids in U.markers(conn, ext).items():
        if kind == "wifi_bssid":
            continue  # read below with the network's times and name
        item = inv.keys.setdefault((kind, digest), {"display": None, "records": [], "natures": set(), "first": None,
                                                     "last": None, "events": 0})
        item["events"] += len(uids)
        for u in uids:
            if u and (u, kind) not in item["records"]:
                item["records"].append((u, {"account": "Username", "saved_login": "Account"}.get(kind, kind)))
    wifi = FV.field_values(conn, ext, ("WirelessNetwork",), ("BSSId", "SSId"))
    wt = FV.times_for(conn, ext, list(wifi), ("LastConnection", "TimeStamp", "LastAutoConnection"))
    ssid_bssids = defaultdict(set)
    for uid, v in wifi.items():
        when = _first_time(wt, uid, ("LastConnection", "TimeStamp", "LastAutoConnection"))
        bssids = [b for b in (norm_bssid(x) for x in v["values"].get("BSSId", ())) if b]
        for b in bssids:
            inv.add("wifi_bssid", b, b, uid, "BSSId", when=when)
        for s in v["values"].get("SSId", ()):
            s2 = (s or "").strip()
            if s2:
                inv.add("ssid", s2.casefold(), s2, uid, "SSId", when=when)
                ssid_bssids[_digest("ssid", s2.casefold())].update(bssids)
    conn_recs = FV.field_values(conn, ext, ("DeviceConnectivity",),
                                ("DeviceName", "ConnectivityMethod", "ConnectivityNature", "DeviceType"))
    ct = FV.times_for(conn, ext, list(conn_recs), ("StartTime",))
    for uid, v in conn_recs.items():
        method = (v["values"].get("ConnectivityMethod") or [""])[0]
        if method and method.lower() != "bluetooth":
            continue  # WiFi connectivity events are networks, read from WirelessNetwork
        nature = (v["values"].get("ConnectivityNature") or [None])[0]
        for name in v["values"].get("DeviceName", ()):
            n = (name or "").strip()
            if n:
                inv.add("bluetooth_name", n.casefold(), n, uid, "DeviceName", nature=nature,
                        when=_first_time(ct, uid, ("StartTime",)))
    rec = FV.field_values(conn, ext, ("RecognizedDevice",), ("Name",))
    for uid, v in rec.items():
        for name in v["values"].get("Name", ()):
            n = (name or "").strip()
            if n:
                inv.add("bluetooth_name", n.casefold(), n, uid, "Name", nature="Recognized")
    if rec:
        # nested identifiers of recognised devices: any hardware address among their values
        for r in conn.execute(text(
                "SELECT c.document_index, c.ordinal, c.body::text AS b, p.ordinal AS parent FROM phone_records c JOIN "
                "phone_records p ON p.extraction_id = c.extraction_id AND p.document_index = c.document_index AND "
                "p.ordinal = c.top_ordinal WHERE c.extraction_id = :e AND p.model_type = 'RecognizedDevice' AND "
                "c.ordinal <> p.ordinal"), {"e": str(ext)}):
            from services.phone import ids
            puid = str(ids.record_uid(ext, r.document_index, r.parent))
            for mac in _MAC.findall(r.b or ""):
                n = norm_bssid(mac)
                if n:
                    inv.add("bluetooth_address", n, n, puid, "DeviceIdentifiers", nature="Recognized")
    services = defaultdict(set)  # digest -> sources
    for uid, v in FV.field_values(conn, ext, ("Cookie",), ("Domain",)).items():
        for d in v["values"].get("Domain", ()):
            rd = registrable_domain(d)
            if rd:
                inv.add("service", rd, rd, uid, "Domain")
                services[_digest("service", rd)].add("cookie")
    for uid, v in FV.field_values(conn, ext, ("Password",), ("Service", "Server")).items():
        for f in ("Service", "Server"):
            for d in v["values"].get(f, ()):
                rd = registrable_domain(d)
                if rd:
                    inv.add("service", rd, rd, uid, f)
                    services[_digest("service", rd)].add("saved login")
    for uid, v in FV.field_values(conn, ext, ("UserAccount",), ("ServiceIdentifier", "ServiceType")).items():
        for f in ("ServiceIdentifier", "ServiceType"):
            for d in v["values"].get(f, ()):
                rd = registrable_domain(d)
                if rd:
                    inv.add("service", rd, rd, uid, f)
                    services[_digest("service", rd)].add("account")
    apps = FV.field_values(conn, ext, ("InstalledApplication",), ("Identifier", "Name"))
    app_words = set()
    for v in apps.values():
        for f in ("Identifier", "Name"):
            for x in v["values"].get(f, ()):
                app_words.update(w for w in re.split(r"[^a-z0-9]+", (x or "").casefold()) if len(w) >= 3)
    sessions = FV.field_values(conn, ext, ("RemoteServiceSession",), ("UserAgent", "DeviceType", "Account"))
    st = FV.times_for(conn, ext, list(sessions), ("DateStarted",))
    return inv, {"has_apps": bool(apps), "app_count": len(apps), "app_words": app_words, "services": services,
                 "ssid_bssids": ssid_bssids, "sessions": sessions, "session_times": st}


def _connected(natures):
    return bool(set(natures) & set(CONNECTED)) or "Recognized" in natures or not natures


def grade(kind, per_phone, case_phones) -> tuple:
    """(level, match reasons, substantiation reasons, undercut codes) for one shared key. ``per_phone``: list of
    inventory items, one per phone holding the key."""
    base = KEY_KINDS[kind][0]
    level = LEVELS.index(base)
    match = ["Same %s on %d phones: %s, matched by %s." % (KEY_KINDS[kind][1], len(per_phone), base,
                                                            STRENGTH_RULE[base])]
    subst = ["Records or events behind it on each phone: %s." % ", ".join(str(i["events"]) for i in per_phone)]
    under = []
    if kind in ("bluetooth_name", "bluetooth_address"):
        nearby = sum(1 for i in per_phone if i["natures"] and not _connected(i["natures"]))
        if nearby:
            level = min(level + 1, 3)
            match.append("One level lower: on %d of the phones it was only detected nearby, never connected." % nearby)
            under.append("detected_not_connected")
        else:
            subst.append("Connected, paired or recognised on every phone holding it.")
    if base == "weak" and case_phones >= 3 and len(per_phone) * 2 > case_phones:
        level = min(level + 1, 3)
        match.append("One level lower: %d of the case's %d phones hold it, a common %s." % (
            len(per_phone), case_phones, KEY_KINDS[kind][1]))
        under.append("common_key")
    if kind in ("bluetooth_name", "ssid"):
        under.append("names_not_unique" if kind == "bluetooth_name" else "ssid_repeats")
    if kind in ("account", "saved_login"):
        under.append("synced_account")
    return LEVELS[level], match, subst, under


UNDERCUT_WORDS = {
    "detected_not_connected": "Detected is not connected: Bluetooth scans list devices that were only nearby.",
    "names_not_unique": "Device names are set by their owners and are not unique.",
    "ssid_repeats": "Network names repeat across places; only the access point (BSSID) identifies one network.",
    "common_key": "Most phones of the case hold it, so it says little about any one pair.",
    "synced_account": "An account or saved login can be synced from another device.",
    "app_match_by_name": "Apps are matched to the service by words in their name or identifier, a rule of thumb.",
    "no_app_data": "This phone's extraction holds no installed applications, so the comparison is not made.",
    "user_agent_rule": "The device family and system are read from the user agent by a fixed rule.",
}


def coverage(conn, case_id) -> dict:
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        n = FV.type_counts(conn, ext, ("WirelessNetwork", "DeviceConnectivity", "RecognizedDevice", "UserAccount",
                                       "Password", "SIMData", "Cookie", "InstalledApplication"))
        phones[ext] = {"label": label, "signals": {
            "networks": {"carries_signal": n.get("WirelessNetwork", 0) > 0, "records": n.get("WirelessNetwork", 0)},
            "bluetooth": {"carries_signal": (n.get("DeviceConnectivity", 0) + n.get("RecognizedDevice", 0)) > 0,
                          "records": n.get("DeviceConnectivity", 0) + n.get("RecognizedDevice", 0)},
            "accounts": {"carries_signal": (n.get("UserAccount", 0) + n.get("Password", 0) + n.get("SIMData", 0)) > 0,
                         "records": n.get("UserAccount", 0) + n.get("Password", 0) + n.get("SIMData", 0)},
            "services": {"carries_signal": (n.get("Cookie", 0) + n.get("Password", 0) + n.get("UserAccount", 0)) > 0,
                         "records": n.get("Cookie", 0) + n.get("Password", 0) + n.get("UserAccount", 0)},
            "apps": {"carries_signal": n.get("InstalledApplication", 0) > 0,
                     "records": n.get("InstalledApplication", 0)}}}
    return {"phones": phones, "signals": SIGNALS}


def _anchor(conn, ext):
    r = next(iter(conn.execute(text("SELECT record_uid::text FROM pv_record WHERE extraction_id = :e ORDER BY ordinal "
                                    "LIMIT 1"), {"e": ext})), None)
    return r[0] if r else None


def _iso(t):
    return t.isoformat() if t is not None else None


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    phones = FV.active_phones(conn, case_id)
    ids_ = sorted(phones, key=lambda e: (str(phones[e]), e))
    invs, facts = {}, {}
    for i, e in enumerate(ids_):
        if ctx is not None:
            ctx.progress(i, len(ids_), phones[e])
            if ctx.cancelled():
                break
        invs[e], facts[e] = inventory(conn, e)
    out = []
    anchors = {e: _anchor(conn, e) for e in invs}
    # ---- per phone: inventory, services without an app, remote sessions
    for e in ids_:
        if e not in invs:
            continue
        inv, f = invs[e], facts[e]
        by_kind = defaultdict(int)
        nearby = 0
        for (kind, _), item in inv.keys.items():
            by_kind[kind] += 1
            if kind == "bluetooth_name" and item["natures"] and not _connected(item["natures"]):
                nearby += 1
        firsts = [i["first"] for i in inv.keys.values() if i["first"] is not None]
        lasts = [i["last"] for i in inv.keys.values() if i["last"] is not None]
        if anchors[e]:
            out.append({
                "kind": "phone_inventory", "strength": "listed",
                "measures": {"phone_label": phones[e], "keys_by_kind": dict(by_kind),
                             "bluetooth_nearby_only": nearby, "apps_compared": f["has_apps"],
                             "installed_apps": f["app_count"], "sessions": len(f["sessions"]),
                             "first": _iso(min(firsts) if firsts else None), "last": _iso(max(lasts) if lasts else None),
                             "no_app_words": None if f["has_apps"] else UNDERCUT_WORDS["no_app_data"]},
                "directions": {"supports": [_d("inventory", "%d %s." % (n, KEY_KINDS[k][1 if n == 1 else 2]))
                                            for k, n in sorted(by_kind.items())],
                               "undercuts": ([_d("detected_not_connected", "%d Bluetooth devices only nearby, not "
                                                 "connected." % nearby)] if nearby else []) +
                                            ([] if f["has_apps"] else [_d("no_app_data", UNDERCUT_WORDS["no_app_data"])])},
                "period_start": min(firsts) if firsts else None, "period_end": max(lasts) if lasts else None,
                "records": [{"extraction_id": e, "record_uid": anchors[e], "field_path": "phone:inventory",
                             "role": "phone"}]})
        if f["has_apps"]:
            for (kind, dg), item in sorted(inv.keys.items(), key=lambda kv: kv[1]["display"] or ""):
                if kind != "service":
                    continue
                label = item["display"].split(".")[-2] if "." in item["display"] else item["display"]
                if label in f["app_words"]:
                    continue
                src = sorted(f["services"].get(dg, ()))
                level = "moderate" if ("saved login" in src or "account" in src) else "weak"
                counts["service_without_app"] += 1
                out.append({
                    "kind": "service_without_app", "strength": level,
                    "measures": {"phone_label": phones[e], "service": item["display"], "sources": src,
                                 "records": len(item["records"]),
                                 "reasons": {"match": ["No installed application's name or identifier holds the word "
                                                       "'%s'." % label],
                                             "substantiation": ["Present by %s, %d records: %s." % (
                                                 " and ".join(src), len(item["records"]),
                                                 "a saved login or account is moderate" if level == "moderate" else
                                                 "a cookie alone is weak")]}},
                    "directions": {"supports": [_d("service_present", "Present by %s." % " and ".join(src)),
                                                _d("no_app_found", "No installed app found for it among %d." %
                                                   f["app_count"])],
                                   "undercuts": [_d("app_match_by_name", UNDERCUT_WORDS["app_match_by_name"])]},
                    "period_start": None, "period_end": None,
                    "records": [{"extraction_id": e, "record_uid": u, "field_path": fld, "role": "service"}
                                for u, fld in item["records"][:RECORDS_PER_PHONE]]})
        for uid, v in sorted(f["sessions"].items()):
            ua = (v["values"].get("UserAgent") or [None])[0]
            fam, os_ = user_agent_family(ua)
            when = (f["session_times"].get(uid) or {}).get("DateStarted")
            counts["remote_session"] += 1
            out.append({
                "kind": "remote_session", "strength": "listed",
                "measures": {"phone_label": phones[e], "device_family": fam, "os": os_,
                             "device_type": (v["values"].get("DeviceType") or [None])[0], "started": _iso(when)},
                "directions": {"supports": [_d("session_recorded", "A session of another device on an account of "
                                               "this phone is recorded.")],
                               "undercuts": [_d("user_agent_rule", UNDERCUT_WORDS["user_agent_rule"])]},
                "period_start": when, "period_end": when,
                "records": [{"extraction_id": e, "record_uid": uid, "field_path": "UserAgent", "role": "session"}]})
    # ---- across phones
    holders = defaultdict(list)
    for e in ids_:
        for k in (invs.get(e) or _Inv()).keys:
            holders[k].append(e)
    n_phones = len(ids_)
    for (kind, dg), exts in sorted(holders.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if len(exts) < 2:
            continue
        if kind == "ssid":
            # a network name explained by a shared access point on the same phones is said in that row, not twice
            sets = [facts[e]["ssid_bssids"].get(dg, set()) for e in exts]
            if all(sets) and set.intersection(*sets):
                counts["ssid_with_shared_bssid"] += 1
                continue
        items = [invs[e].keys[(kind, dg)] for e in exts]
        level, match, subst, under = grade(kind, items, n_phones)
        recs = []
        for e, item in zip(exts, items):
            for i, (u, fld) in enumerate(item["records"][:RECORDS_PER_PHONE]):
                recs.append({"extraction_id": e, "record_uid": u, "field_path": fld, "role": "key_" + kind})
            if anchors.get(e):
                recs.append({"extraction_id": e, "record_uid": anchors[e], "field_path": "shared:%s:%s" %
                             (kind, dg[:16]), "role": "phone"})
        firsts = [i["first"] for i in items if i["first"] is not None]
        lasts = [i["last"] for i in items if i["last"] is not None]
        display = next((i["display"] for i in items if i["display"]), None) if kind in SHOW_VALUE else None
        per = [{"extraction_id": e, "phone_label": phones[e], "records": len(i["records"]), "events": i["events"],
                "natures": sorted(i["natures"]),
                "nearby_only": bool(i["natures"]) and not _connected(i["natures"]),
                "first": _iso(i["first"]), "last": _iso(i["last"]),
                "records_shown": min(len(i["records"]), RECORDS_PER_PHONE)} for e, i in zip(exts, items)]
        counts["shared_" + level] += 1
        counts["shared_%s_%s" % (kind, level)] += 1
        out.append({
            "kind": "shared_key", "strength": level,
            "measures": {"key_kind": kind, "key_words": KEY_KINDS[kind][1], "value": display,
                         "phone_count": len(exts), "phones": per, "case_phone_count": n_phones,
                         "reasons": {"match": match, "substantiation": subst},
                         "rule_of_thumb": RULE_OF_THUMB},
            "directions": {"supports": [_d({"strong": "match_identifier", "moderate": "match_username"}.get(
                KEY_KINDS[kind][0], "match_name"), m) for m in match[:1]] + [_d("records_each_side", s) for s in subst],
                "undercuts": [_d(u, UNDERCUT_WORDS[u]) for u in under]},
            "period_start": min(firsts) if firsts else None, "period_end": max(lasts) if lasts else None,
            "records": recs})
    if ctx is not None:
        ctx.progress(len(ids_), len(ids_))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
