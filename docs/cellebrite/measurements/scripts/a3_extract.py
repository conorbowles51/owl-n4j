"""Stage A3 server measurement batch, pass 1 (06 section 5): one read-only streaming pass per report.

usage: python3 -I a3_extract.py <corpus.json> <out_dir> <label> [--markers]

Writes to <out_dir> (the private corpus folder, never the repository):
  <label>.counts.json  per-report counts, already guarded (see below)
  <label>.facts.pkl    private join keys for the cross-phone pass (a3_cross.py): salted hashes, instants,
                       and positions. Never committed, never printed; deleted when the batch is recorded.

Guards (04 section 13, applied to every string that reaches a counts file):
  - a String value is kept only if it matches GUARD_RE and occurs at least 3 times in the report for that
    measure; otherwise it is counted as `<other>`;
  - free-text fields (Body, Subject, Name, Value of TextInput, DeviceName, Account, SSId, BSSId, Url, Title,
    and every identifier) are never written: only presence counts, lengths and shapes;
  - times become shapes, UTC hour histograms, durations or day offsets; coordinates become distances,
    counts and radius histograms;
  - joins across phones use HMAC-SHA256 with a per-batch salt kept in the private folder.
Cellebrite's own type, field and named-set names are schema, not case content, and are written as such.
"""
import array
import bisect
import calendar
import collections
import hashlib
import hmac
import json
import math
import os
import pickle
import re
import subprocess
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET

GUARD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$")
BASIC = {"String", "TimeStamp", "Boolean", "Int64", "Int32", "Double", "TimeSpan", "Guid", "UInt32"}
FIELD_KINDS = ("field", "multiField", "modelField", "multiModelField", "nodeField", "dataField")
TS_RE = re.compile(r"^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(\.(\d+))?(Z|[+-]\d\d:\d\d)?$")
HEADER_IDS = ("IMEI", "ICCID", "IMSI", "MSISDN", "DeviceInfoAndroidID", "Bluetooth MAC Address", "Mac Address",
              "Factory number")
AMOUNT_RE = re.compile(r"(?:[$€£₦]|\b(?:USD|EUR|GBP|NGN|XAF|XOF|MXN|CAD|GHS|KES)\b)\s?\d[\d,.]*\d|\d[\d,.]*\d\s?"
                       r"(?:[$€£₦]|\b(?:USD|EUR|GBP|NGN|XAF|XOF|MXN|CAD|GHS|KES|dollars?)\b)", re.I)
SHORT_CODE_RE = re.compile(r"^\d{3,6}$")
CAMERA_PATH_RE = re.compile(r"(^|/)(dcim|camera)(/|$)", re.I)


def ln(t):
    return t.rsplit("}", 1)[-1]


# ---------------------------------------------------------------- helpers

class Salt:
    def __init__(self, path):
        if not os.path.exists(path):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(fd, os.urandom(32))
            os.close(fd)
        self.key = open(path, "rb").read()

    def h(self, kind, value):
        return hmac.new(self.key, (kind + "\x00" + value).encode("utf-8", "surrogatepass"),
                        hashlib.sha256).digest()[:12]


def ts(text):
    """(epoch seconds as float, offset state) or (None, state)."""
    if not text:
        return None, "empty"
    m = TS_RE.match(text.strip())
    if not m:
        return None, "unparsed"
    if not m.group(9):
        return None, "absent"
    y, mo, d, hh, mi, ss = (int(m.group(i)) for i in range(1, 7))
    frac = float("0." + m.group(8)) if m.group(8) else 0.0
    secs = calendar.timegm((y, mo, d, hh, mi, ss, 0, 0, 0)) + frac
    off = m.group(9)
    if off != "Z":
        sign = 1 if off[0] == "+" else -1
        secs -= sign * (int(off[1:3]) * 3600 + int(off[4:6]) * 60)
    return secs, "explicit"


def ts_shape(text):
    m = TS_RE.match((text or "").strip())
    if not m:
        return "unparsed" if text else "empty"
    off = m.group(9)
    offs = "absent" if not off else ("Z" if off == "Z" else ("+00:00" if off in ("+00:00", "-00:00") else "nonzero"))
    return "frac%d/%s" % (len(m.group(8) or ""), offs)


def log_bucket(x):
    """Bucket of a non-negative duration in seconds: '<0', '0', '1', '2-9', '10-99', ..."""
    if x is None:
        return "none"
    if x < 0:
        return "<0"
    if x < 1:
        return "0"
    if x < 2:
        return "1"
    e = int(math.floor(math.log10(x)))
    lo = 10 ** e
    return "%d-%d" % (lo if e else 2, 10 ** (e + 1) - 1)


def quantiles(sorted_vals, qs=(0.5, 0.9, 0.95, 0.99)):
    n = len(sorted_vals)
    if not n:
        return None
    out = {}
    for q in qs:
        out["p%d" % round(q * 100)] = round(sorted_vals[min(n - 1, int(q * n))], 3)
    out["max"] = round(sorted_vals[-1], 3)
    out["n"] = n
    return out


def haversine(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def fnum(text):
    try:
        v = float(text)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def id_key(identifier):
    """Normalised identifier for joins: digits only when the value is a phone-like number, else casefolded."""
    s = (identifier or "").strip()
    if not s:
        return None
    core = re.sub(r"[\s()+.\-]", "", s.split("@")[0])
    if core.isdigit() and len(core) >= 7:
        return "n:" + core[-10:]
    return "s:" + s.casefold()


class Guarded:
    """Counter of raw string values per measure; written only through the guard."""

    def __init__(self):
        self.c = collections.defaultdict(collections.Counter)

    def add(self, measure, *parts):
        self.c[measure][parts] += 1

    def out(self):
        res = {}
        for measure, cnt in self.c.items():
            occ = collections.Counter()
            for parts, n in cnt.items():
                for p in parts:
                    if isinstance(p, str):
                        occ[p] += n
            g = collections.Counter()
            for parts, n in cnt.items():
                key = []
                for p in parts:
                    if p is None:
                        key.append("<absent>")
                    elif isinstance(p, bool):
                        key.append(str(p))
                    elif isinstance(p, (int, float)):
                        key.append(str(p))
                    elif p.startswith("\x01"):  # a label of our own (bucket names), not a value
                        key.append(p[1:])
                    elif GUARD_RE.match(p) and occ[p] >= 3:
                        key.append(p)
                    else:
                        key.append("<other>")
                g[" | ".join(key)] += n
            res[measure] = dict(sorted(g.items()))
        return res


def L(label):
    """Mark one of our own labels so the guard passes it unchanged."""
    return "\x01" + label


# ---------------------------------------------------------------- records

def conv(m):
    r = {"t": m.get("type"), "id": m.get("id"), "del": m.get("deleted_state"), "fid": m.get("file_id"),
         "f": {}, "k": {}, "m": {}, "jt": []}
    for c in m:
        tag = ln(c.tag)
        if tag in ("field", "multiField"):
            name = c.get("name")
            r["k"][name] = tag
            r["f"][name] = [(v.get("type"), v.text or "", v.get("formattedTimestamp")) for v in c if ln(v.tag) == "value"]
        elif tag in ("modelField", "multiModelField"):
            name = c.get("name")
            r["k"][name] = tag
            r["m"][name] = [conv(x) for x in c if ln(x.tag) == "model"]
        elif tag in ("nodeField", "dataField"):
            r["k"][c.get("name")] = tag
        elif tag == "jumptargets":
            r["jt"] += [(t.get("ismodel"), (t.text or "").strip()) for t in c]
    return r


def fv(r, name):
    v = r["f"].get(name)
    return v[0][1] if v else None


def fvs(r, name):
    return [x[1] for x in r["f"].get(name, [])]


def walk(r, parent=None, field=None):
    yield r, parent, field
    for name, kids in r["m"].items():
        for k in kids:
            yield from walk(k, r, name)


def parties(r, field):
    return r["m"].get(field, [])


def is_true(v):
    return (v or "").strip().lower() == "true"


# ---------------------------------------------------------------- the pass

class Report:
    def __init__(self, label, salt, markers):
        self.label = label
        self.salt = salt
        self.markers = markers
        self.g = Guarded()
        self.c = collections.defaultdict(collections.Counter)  # plain counters with label-only keys
        self.types = collections.Counter()
        self.top_types = collections.Counter()
        self.fields = collections.Counter()
        self.enums = collections.defaultdict(set)
        self.nesting = collections.Counter()
        self.header = {}
        self.header_items = collections.Counter()
        self.extraction_info = []
        self.tz = None
        self.streams = collections.defaultdict(lambda: array.array("d"))
        self.durations = collections.defaultdict(list)
        self.dup = collections.defaultdict(list)
        self.interaction = array.array("d")
        self.power_seq = []
        self.cp_name = collections.Counter()
        self.cp_range = collections.Counter()
        self.cp_styled = collections.Counter()
        self.cp_total = collections.Counter()
        self.files = {}
        self.file_item_names = collections.Counter()
        self.attachment_file_ids = set()
        self.jt_file_ids = set()
        self.facts = {
            "owner_keys": set(), "owner_keys_e164": set(), "party_keys": set(), "msgs": [], "msg_ident": set(), "chat_ids": set(),
            "loc": [], "bssid_obs": [], "cell_obs": [], "keys": collections.defaultdict(set),
            "ident": {}, "sim": set(), "markers": collections.defaultdict(set), "model_ids": set(),
            "md5_all": {}, "md5_attach": set(), "md5_camera": set(), "interaction_days": set(),
            "chat_activity_timed": 0,
        }
        self.chat_stats = collections.Counter()
        self.ident_values = set()
        self.reply_refs = []
        self.body_occ = collections.Counter()

    # ---- seed (02-U2) and time shapes (M3) over every record, nested included
    def seed(self, rec, parent, pfield):
        t = rec["t"]
        self.types[t] += 1
        if parent is not None:
            self.nesting[(parent["t"], pfield, parent["k"].get(pfield), t)] += 1
        for name, vals in rec["f"].items():
            kind = rec["k"][name]
            for vt, text, fmt in vals:
                self.fields[(t, name, kind, vt)] += 1
                if vt == "DecodingSourceOptions":
                    self.enums["DecodingSourceOptions"].add(text.strip())
                elif vt not in BASIC and vt is not None:
                    self.enums[vt].add(text.strip())
                elif vt == "TimeStamp":
                    self.c["m3_shape"][" | ".join((t, name, ts_shape(text)))] += 1
                    if fmt is not None and fmt != text:
                        self.c["m3_text_differs_from_formatted"][t + " | " + name] += 1
                    elif fmt is None:
                        self.c["m3_no_formatted_attribute"][t + " | " + name] += 1
                elif vt == "String":
                    self.codepoints(text)
        if rec["fid"]:
            self.attachment_file_ids.add(rec["fid"])
        for ismodel, target in rec["jt"]:
            if ismodel == "false" and target:
                self.jt_file_ids.add(target)
        self.g.add("m3a_deleted_state", L(t or ""), rec["del"])

    def codepoints(self, text):
        for ch in text:
            o = ord(ch)
            if o < 128:
                self.cp_total["ascii"] += 1
                continue
            self.cp_total["non_ascii"] += 1
            self.cp_range["U+%04X" % (o & ~0x7F)] += 1
            try:
                self.cp_name[unicodedata.name(ch).split(" ")[0]] += 1
            except ValueError:
                self.cp_name["<no name>"] += 1
            if 0x1D400 <= o <= 0x1D7FF:
                self.cp_styled["mathematical_alphanumeric"] += 1
            elif 0xFF01 <= o <= 0xFF5E:
                self.cp_styled["fullwidth_ascii"] += 1
            elif 0x2460 <= o <= 0x24FF:
                self.cp_styled["enclosed_alphanumerics"] += 1
            elif 0x1F150 <= o <= 0x1F169 or 0x1F170 <= o <= 0x1F189:
                self.cp_styled["negative_circled_or_squared_latin"] += 1
            elif 0x1F1E6 <= o <= 0x1F1FF:
                self.cp_styled["regional_indicator"] += 1
            elif 0x1F100 <= o <= 0x1F1FF:
                self.cp_styled["enclosed_alphanumeric_supplement_other"] += 1
            elif o in SMALL_CAPS:
                self.cp_styled["latin_small_capital"] += 1
            elif 0x2070 <= o <= 0x209F:
                self.cp_styled["superscript_subscript"] += 1
            elif 0x2100 <= o <= 0x214F:
                self.cp_styled["letterlike"] += 1
            elif 0x0400 <= o <= 0x04FF:
                self.cp_styled["cyrillic"] += 1
            elif 0x0370 <= o <= 0x03FF:
                self.cp_styled["greek"] += 1
            if unicodedata.normalize("NFKC", ch) != ch:
                self.cp_styled["changed_by_nfkc"] += 1
            if unicodedata.category(ch) in ("Cf", "Cc"):
                self.cp_styled["format_or_control"] += 1

    def stream(self, key, secs):
        if secs is not None:
            self.streams[key].append(secs)

    def interact(self, secs, why):
        if secs is not None:
            self.interaction.append(secs)
            self.c["m12_candidate_interaction_rows"][why] += 1

    # ---- per record handlers
    def handle(self, rec, parent, pfield, top):
        t = rec["t"]
        if self.markers and top:
            vals = sorted("%s=%s" % (n, "|".join(fvs(rec, n))) for n in rec["f"])
            self.facts["markers"][t].add(self.salt.h("marker", t + "\x00" + "\x00".join(vals)))
            if rec["id"]:
                self.facts["model_ids"].add(self.salt.h("id", rec["id"]))
        h = getattr(self, "h_" + (t or ""), None)
        if h:
            h(rec, parent, pfield)

    def h_DeviceEvent(self, r, p, f):
        et, src, val = fv(r, "EventType"), fv(r, "Source"), fv(r, "Value")
        st, _ = ts(fv(r, "StartTime"))
        en, _ = ts(fv(r, "EndTime"))
        shown = L("len:" + log_bucket(len(val))) if (et == "TextInput" and val is not None) else val
        self.g.add("m1_source_eventtype_value", src, et, shown)
        self.g.add("m1_endtime_present", et, L("yes" if fv(r, "EndTime") else "no"))
        if st is not None and en is not None:
            self.g.add("m1_duration_bucket", et, L(log_bucket(en - st)))
        if st is not None:
            self.g.add("m1_source_eventtype_utc_hour", src, et, L("h%02d" % int(st // 3600 % 24)))
        self.stream(("DeviceEvent", src, et), st)
        self.g.add("m2_usermapping", L("DeviceEvent"), fv(r, "UserMapping"))
        if et == "TextInput":
            self.interact(st, "DeviceEvent TextInput")
        if et == "PowerEvent":
            v = (val or "").strip().lower()
            state = "On" if (v == "on" or v.endswith(" on")) else ("Off" if (v == "off" or v.endswith(" off") or "shut" in v) else "unknown")
            if st is not None:
                self.power_seq.append((st, state, "DeviceEvent"))
        if et == "Wipe":
            self.c["m3c_wipe"]["DeviceEvent Wipe"] += 1

    def h_PoweringEvent(self, r, p, f):
        t0, _ = ts(fv(r, "TimeStamp"))
        ev = fv(r, "Event")
        self.stream(("PoweringEvent", fv(r, "Source") or "", ""), t0)
        if t0 is not None:
            self.power_seq.append((t0, ev if ev in ("On", "Off") else "unknown", "PoweringEvent"))

    def h_Location(self, r, p, f):
        src, typ, cat = fv(r, "Source"), fv(r, "Type"), fv(r, "Category")
        coords = [c for c in r["m"].get("Position", []) if c["t"] == "Coordinate"]
        acc = fnum(fv(r, "GpsHorizontalAccuracy"))
        lat = lon = None
        if coords:
            c = coords[0]
            lat, lon = fnum(fv(c, "Latitude")), fnum(fv(c, "Longitude"))
            if acc is None:
                acc = fnum(fv(c, "GpsHorizontalAccuracy"))
        t0, state = ts(fv(r, "TimeStamp"))
        key = (src, typ, cat)
        self.g.add("m5_location_source_type_category", *key)
        if coords:
            self.g.add("m5_location_with_coordinate", *key)
        if acc is not None:
            self.durations["m5_accuracy_m"].append(acc)
        self.g.add("m5_location_precision", fv(r, "Precision"))
        conf = fnum(fv(r, "Confidence"))
        self.c["m5_confidence_bucket"]["none" if conf is None else str(int(conf // 10 * 10))] += 1
        self.c["m5_time_fields"]["TimeStamp " + state] += 1
        self.c["m5_time_fields"]["EndTime " + ("present" if fv(r, "EndTime") else "absent")] += 1
        self.g.add("m5_affiliation_device_account_origin", fv(r, "DeviceLocationAffiliation"),
                   fv(r, "AccountLocationAffiliation"), fv(r, "Origin"))
        self.g.add("m2_location_type_category_precision_source", typ, cat, fv(r, "Precision"), src)
        self.g.add("m2_usermapping", L("Location"), fv(r, "UserMapping"))
        self.stream(("Location", src or "", ""), t0)
        if typ == "Searched":
            self.interact(t0, "Location Type Searched")
        if lat is not None and lon is not None and t0 is not None and not (lat == 0 and lon == 0):
            self.facts["loc"].append((t0, lat, lon, acc, fv(r, "DeviceLocationAffiliation") or ""))

    def h_WirelessNetwork(self, r, p, f):
        src = fv(r, "Source")
        coords = [c for c in r["m"].get("Position", []) if c["t"] == "Coordinate"]
        acc = fnum(fv(coords[0], "GpsHorizontalAccuracy")) if coords else None
        self.g.add("m5_wifi_source", src)
        for name, present in (("BSSId", bool(fv(r, "BSSId"))), ("Position", bool(coords)), ("accuracy", acc is not None),
                              ("TimeStamp", bool(fv(r, "TimeStamp"))), ("LastConnection", bool(fv(r, "LastConnection")))):
            if present:
                self.g.add("m5_wifi_with", src, L(name))
        self.g.add("m2_usermapping", L("WirelessNetwork"), fv(r, "UserMapping"))
        bssid = (fv(r, "BSSId") or "").strip().lower()
        for tf in ("TimeStamp", "LastConnection", "LastAutoConnection"):
            t0, _ = ts(fv(r, tf))
            if tf == "TimeStamp":
                self.stream(("WirelessNetwork", src or "", ""), t0)
            if bssid and t0 is not None:
                self.facts["bssid_obs"].append((self.salt.h("bssid", bssid), t0))
        if bssid:
            self.facts["keys"]["bssid"].add(self.salt.h("bssid", bssid))
        ssid = (fv(r, "SSId") or "").strip()
        if ssid:
            self.facts["keys"]["ssid"].add(self.salt.h("ssid", ssid))

    def h_CellTower(self, r, p, f):
        vals = {n: (fv(r, n) or "").strip() for n in ("MCC", "MNC", "LAC", "CID")}
        self.c["m5_cell_mcc"]["with MCC" if vals["MCC"] else "no MCC"] += 1
        for n in ("MNC", "LAC", "CID"):
            self.c["m5_cell_digits"]["%s %s" % (n, len(vals[n]) if vals[n].isdigit() else ("empty" if not vals[n] else "non-digit"))] += 1
        self.g.add("m5_cell_type", fv(r, "Type"))
        t0, _ = ts(fv(r, "TimeStamp"))
        self.stream(("CellTower", "", ""), t0)
        if all(vals.values()) and t0 is not None:
            self.facts["cell_obs"].append((self.salt.h("cell", "|".join((fv(r, "Type") or "",) + tuple(vals.values()))), t0))

    def h_Journey(self, r, p, f):
        for name, kids in r["m"].items():
            for k in kids:
                self.c["m5_journey_nesting"]["%s (%s) -> %s" % (name, r["k"].get(name), k["t"])] += 1
        t0, _ = ts(fv(r, "StartTime"))
        self.stream(("Journey", fv(r, "Source") or "", ""), t0)

    def h_NetworkUsage(self, r, p, f):
        s, _ = ts(fv(r, "DateStarted"))
        e, _ = ts(fv(r, "DateEnded"))
        mode = fv(r, "UsageMode")
        if s is not None and e is not None:
            self.c["m4_networkusage_bucket_width"][log_bucket(e - s)] += 1
        self.stream(("NetworkUsage", fv(r, "Source") or "", ""), s)
        if mode == "Foreground":
            self.interact(s, "NetworkUsage Foreground")

    def h_AppsUsageLog(self, r, p, f):
        s, _ = ts(fv(r, "StartTime"))
        e, _ = ts(fv(r, "EndTime"))
        if s is not None and e is not None:
            self.c["m4_appsusagelog_duration"][log_bucket(e - s)] += 1
        self.g.add("m2_appsusagelog_source_action", fv(r, "Source"), fv(r, "Action"))
        self.g.add("m2_usermapping", L("AppsUsageLog"), fv(r, "UserMapping"))
        self.stream(("AppsUsageLog", fv(r, "Source") or "", ""), s)
        if fv(r, "Action") == "Launch":
            self.interact(s, "AppsUsageLog Launch")

    def h_ApplicationUsage(self, r, p, f):
        s, _ = ts(fv(r, "StartTime"))
        e, _ = ts(fv(r, "EndTime"))
        if s is not None and e is not None:
            self.c["m4_applicationusage_duration"][log_bucket(e - s)] += 1
        self.stream(("ApplicationUsage", fv(r, "Source") or "", ""), s)
        at = fv(r, "ActiveTime")
        if at and at.strip() not in ("00:00:00", "0", "00:00:00.0000000"):
            self.interact(s, "ApplicationUsage ActiveTime > 0")

    def h_InstalledApplication(self, r, p, f):
        for tf in ("InstallDate", "DeletedDate"):
            t0, _ = ts(fv(r, tf))
            self.interact(t0, "InstalledApplication " + tf)
        for cat in fvs(r, "Categories"):
            self.g.add("s05_installed_app_categories", cat)

    def h_DeviceConnectivity(self, r, p, f):
        nat = fv(r, "ConnectivityNature")
        self.g.add("m2_deviceconnectivity_nature_method_type", nat, fv(r, "ConnectivityMethod"), fv(r, "DeviceType"))
        s, _ = ts(fv(r, "StartTime"))
        self.stream(("DeviceConnectivity", fv(r, "Source") or "", ""), s)
        dn = (fv(r, "DeviceName") or "").strip()
        if dn and s is not None:
            self.durations["_conn"].append((self.salt.h("bt", dn.casefold()), nat or "", s))
        if dn:
            self.facts["keys"]["bluetooth_name"].add(self.salt.h("bt", dn.casefold()))

    def h_RecognizedDevice(self, r, p, f):
        n = (fv(r, "Name") or "").strip()
        if n:
            self.facts["keys"]["bluetooth_name"].add(self.salt.h("bt", n.casefold()))

    def h_UserAccount(self, r, p, f):
        u = (fv(r, "Username") or "").strip()
        if u:
            self.facts["keys"]["account_username"].add(self.salt.h("acct", (fv(r, "ServiceType") or "") + "\x00" + u.casefold()))

    def h_Password(self, r, p, f):
        acc = (fv(r, "Account") or "").strip()
        if acc:
            self.facts["keys"]["saved_login_account"].add(self.salt.h("acct", acc.casefold()))

    def h_Cookie(self, r, p, f):
        d = (fv(r, "Domain") or "").strip().lstrip(".").lower()
        if d:
            self.facts["keys"]["cookie_domain"].add(self.salt.h("dom", d))

    def h_RemoteServiceSession(self, r, p, f):
        ua = (fv(r, "UserAgent") or "").strip()
        if ua:
            self.facts["keys"]["remote_session_user_agent"].add(self.salt.h("ua", ua))

    def h_SIMData(self, r, p, f):
        cat, val = (fv(r, "Category") or ""), (fv(r, "Value") or "").strip()
        self.g.add("s05_simdata_category", cat)
        if val and re.search(r"ICCID|IMSI", cat + " " + (fv(r, "Name") or ""), re.I):
            self.facts["sim"].add(self.salt.h("sim", val))

    def h_ActivitySensorData(self, r, p, f):
        s, _ = ts(fv(r, "From"))
        e, _ = ts(fv(r, "To"))
        if s is not None and e is not None:
            self.c["m4_activitysensordata_to_minus_from"][log_bucket(e - s)] += 1
        self.stream(("ActivitySensorData", fv(r, "Source") or "", ""), s)
        dn = (fv(r, "DeviceName") or "")
        self.c["m9_devicename_tokens"][" ".join(tok for tok in ("Watch", "iPhone", "Phone") if tok.lower() in dn.lower()) or "none"] += 1
        self.g.add("m9_sourcedevicetype", fv(r, "SourceDeviceType"))
        for name, kids in r["m"].items():
            for k in kids:
                self.c["m9_nesting"]["ActivitySensorData.%s -> %s" % (name, k["t"])] += 1
                for n2, k2 in k["m"].items():
                    for kk in k2:
                        self.c["m9_nesting"]["%s.%s -> %s" % (k["t"], n2, kk["t"])] += 1

    def h_ActivitySensorDataMeasurement(self, r, p, f):
        self.g.add("m9_measuredvariabletype", fv(r, "MeasuredVariableType"))

    def h_ActivitySensorDataSample(self, r, p, f):
        s, _ = ts(fv(r, "DateSampled"))
        mvt = fv(p, "MeasuredVariableType") if p else None
        self.g.add("m9_sample_parent_variable", mvt)
        self.stream(("ActivitySensorDataSample", fv(r, "Source") or "", mvt or ""), s)

    def h_Notification(self, r, p, f):
        t0, _ = ts(fv(r, "TimeStamp"))
        self.g.add("m2_notification_status_type", fv(r, "Status"), fv(r, "Type"))
        self.stream(("Notification", fv(r, "Source") or "", ""), t0)
        si = (fv(r, "ServiceIdentifier") or "").strip()
        self.c["s05_m1a"]["notification_records"] += 1
        if si:
            self.ident_values.add(("notif_si", si))
        body = " ".join(x for x in (fv(r, "Subject"), fv(r, "Body")) if x)
        if body and AMOUNT_RE.search(body):
            self.c["s05_m1b_amount_with_currency"]["S1 notification"] += 1

    def h_VisitedPage(self, r, p, f):
        vc = fnum(fv(r, "VisitCount"))
        self.c["m7_visitcount"]["none" if vc is None else ("1" if vc == 1 else ("0" if vc == 0 else log_bucket(vc)))] += 1
        self.c["m7_lastvisited"]["present" if fv(r, "LastVisited") else "absent"] += 1
        self.g.add("m7_visitedpage_source", fv(r, "Source"))
        for u in fvs(r, "UsagePattern"):
            self.g.add("m7_usagepattern", u)
        t0, _ = ts(fv(r, "LastVisited"))
        self.stream(("VisitedPage", fv(r, "Source") or "", ""), t0)
        self.interact(t0, "VisitedPage LastVisited")
        self.c["s05_m9a"]["pages"] += 1
        if fv(r, "Title"):
            self.c["s05_m9a"]["pages with title"] += 1
        if vc is not None:
            self.c["s05_m9a"]["pages with visit count"] += 1

    def h_SearchedItem(self, r, p, f):
        t0, _ = ts(fv(r, "TimeStamp"))
        self.g.add("m2_searcheditem_source_origin_hastime", fv(r, "Source"), fv(r, "Origin"), L("time" if fv(r, "TimeStamp") else "no time"))
        self.g.add("m7_searcheditem_source_hastime", fv(r, "Source"), L("time" if fv(r, "TimeStamp") else "no time"))
        self.stream(("SearchedItem", fv(r, "Source") or "", ""), t0)
        self.interact(t0, "SearchedItem TimeStamp")
        self.c["s05_m9a"]["searches with time" if fv(r, "TimeStamp") else "searches without time"] += 1

    def h_LogEntry(self, r, p, f):
        t0, _ = ts(fv(r, "TimeStamp"))
        self.stream(("LogEntry", fv(r, "Source") or "", ""), t0)

    def h_SocialMediaActivity(self, r, p, f):
        t0, _ = ts(fv(r, "TimeStamp"))
        self.stream(("SocialMediaActivity", fv(r, "Source") or "", ""), t0)
        at = fv(r, "SocialActivityType")
        if at == "CheckIn":
            self.c["s05_m10"]["check-ins"] += 1
            if any(k["t"] in ("Coordinate", "Location") for kids in r["m"].values() for k in kids):
                self.c["s05_m10"]["check-ins with a nested place"] += 1
        self.g.add("s05_m10_social_activity_type", at)

    def h_CalendarEntry(self, r, p, f):
        self.c["s05_m10"]["calendar entries"] += 1
        if fv(r, "Location"):
            self.c["s05_m10"]["calendar entries with location"] += 1

    def h_Note(self, r, p, f):
        self.c["s05_m10"]["notes"] += 1

    def h_Contact(self, r, p, f):
        if top_level(p):
            self.c["s05_m11a"]["contacts"] += 1
            if fv(r, "TimeCreated"):
                self.c["s05_m11a"]["with TimeCreated"] += 1
            if fv(r, "TimeModified"):
                self.c["s05_m11a"]["with TimeModified"] += 1

    def h_ChatActivity(self, r, p, f):
        t0, _ = ts(fv(r, "SystemMessageTimeStamp"))
        self.c["s05_m4c"]["chat activity records"] += 1
        if t0 is not None:
            self.c["s05_m4c"]["timed chat activity"] += 1
            self.facts["chat_activity_timed"] += 1
        self.g.add("s05_chatactivity_action", fv(r, "Action"))

    def h_ReplyMessageData(self, r, p, f):
        self.reply_refs.append(("reply", (fv(r, "OriginalMessageID") or "").strip()))

    def h_QuotedMessageData(self, r, p, f):
        self.reply_refs.append(("quote", (fv(r, "OriginalMessageID") or "").strip()))

    def h_Party(self, r, p, f):
        ident = (fv(r, "Identifier") or "").strip()
        k = id_key(ident)
        owner = fv(r, "IsPhoneOwner")
        if k:
            self.facts["party_keys"].add(self.salt.h("id", k))
            if is_true(owner):
                self.facts["owner_keys"].add(self.salt.h("id", k))
                if k.startswith("n:"):
                    self.facts["owner_keys_e164"].add(self.salt.h("id", k))
        dates = [n for n in ("DateRead", "DateDelivered", "DatePlayed") if fv(r, n)]
        if dates and p is not None:
            self.g.add("m6_party_dates", L(p["t"] or ""), fv(p, "Source"), fv(r, "Role"), owner,
                       L("+".join(dates)), L(self.direction(p)[0] if p["t"] == "InstantMessage" else "n/a"))
        for n in ("DateRead", "DatePlayed"):
            t0, _ = ts(fv(r, n))
            if t0 is not None and is_true(owner):
                self.interact(t0, "Party %s owner" % n)

    def direction(self, msg):
        frm = parties(msg, "From")
        if frm:
            o = fv(frm[0], "IsPhoneOwner")
            if is_true(o):
                return "outgoing", "from_owner"
            if (o or "").strip().lower() == "false":
                return "incoming", "from_not_owner"
        folder = (fv(msg, "Folder") or "").strip()
        if folder == "Sent":
            return "outgoing", "folder_sent"
        st = (fv(msg, "Status") or "").strip()
        if st in ("Sent", "Unsent"):
            return "outgoing", "status_sent"
        if folder == "Inbox":
            return "incoming", "folder_inbox"
        return "unknown", "none"

    def h_InstantMessage(self, r, p, f):
        d, basis = self.direction(r)
        t0, _ = ts(fv(r, "TimeStamp"))
        frm = parties(r, "From")
        owner_from = fv(frm[0], "IsPhoneOwner") if frm else None
        self.g.add("m2_instantmessage_folder_status_platform_fromowner_type", fv(r, "Folder"), fv(r, "Status"),
                   fv(r, "Platform"), owner_from, fv(r, "Type"))
        self.c["m4_direction_basis"][basis] += 1
        self.stream(("InstantMessage", fv(r, "Source") or "", ""), t0)
        if d == "outgoing" and (fv(r, "Platform") or "Unknown") in ("Mobile", "Unknown"):
            self.interact(t0, "InstantMessage outgoing")
        body = fv(r, "Body") or ""
        sender = (fv(frm[0], "Identifier") or "").strip() if frm else ""
        recips = sorted((fv(x, "Identifier") or "").strip() for x in parties(r, "To"))
        if t0 is not None:
            self.dup[("message", d, sender, tuple(recips),
                      hashlib.sha256(unicodedata.normalize("NFC", body).encode("utf-8", "surrogatepass")).digest())].append(t0)
        # 05 measures
        mtype = fv(r, "Type") or "<absent>"
        self.c["s05_messages"]["total"] += 1
        self.c["s05_messages"]["type " + mtype] += 1
        sdd = fv(r, "SelfDestructDuration")
        if sdd is not None:
            self.c["s05_m3b"]["SelfDestructDuration present"] += 1
            if sdd.strip() not in ("00:00:00", "0", ""):
                self.c["s05_m3b"]["SelfDestructDuration non-zero"] += 1
        for lab in fvs(r, "Label"):
            self.g.add("s05_m3b_label", lab)
        dr = fv(r, "DeletionReason")
        if dr:
            self.g.add("s05_m3c_deletionreason", dr)
        if fv(r, "DateDeleted"):
            self.c["s05_m3c_deletionreason"]["DateDeleted present"] += 1
        smsc = (fv(r, "SMSC") or "").strip()
        if smsc:
            self.c["s05_smsc"]["with SMSC"] += 1
            if sender and smsc == sender:
                self.c["s05_smsc"]["SMSC equals sender"] += 1
        if mtype in ("Sms", "Mms") and SHORT_CODE_RE.match(sender or ""):
            self.c["s05_shortcode"]["short-code sender messages"] += 1
            if AMOUNT_RE.search(body):
                self.c["s05_m1b_amount_with_currency"]["S2 short-code SMS"] += 1
        if mtype == "AppMessage" and AMOUNT_RE.search(body):
            self.c["s05_m1b_amount_with_currency"]["S9 app message"] += 1
        ident = (fv(r, "Identifier") or "").strip()
        if ident:
            self.facts["msg_ident"].add((fv(r, "Source") or "", self.salt.h("mid", ident)))
            self.ident_values.add(("msg_ident", ident))
        nb = " ".join(body.casefold().split())
        if len(nb) >= 10 and t0 is not None:
            self.body_occ[nb] += 1
            self.facts["msgs"].append((self.salt.h("body", nb), t0, d, r["del"] or "", mtype, fv(r, "Platform") or "",
                                       fv(r, "Source") or ""))
        elif nb:
            self.c["s05_x3_short_bodies"]["short or untimed"] += 1
        # M-4a: owner read and played on incoming
        if d == "incoming":
            self.c["s05_m4a"]["incoming"] += 1
            own = [x for x in parties(r, "To") if is_true(fv(x, "IsPhoneOwner"))]
            if any(fv(x, "DateRead") for x in own):
                self.c["s05_m4a"]["incoming with owner DateRead"] += 1
            if any(fv(x, "DatePlayed") for x in own):
                self.c["s05_m4a"]["incoming with owner DatePlayed"] += 1

    def h_Email(self, r, p, f):
        t0, _ = ts(fv(r, "TimeStamp"))
        self.g.add("m2_email_folder_status", fv(r, "Folder"), fv(r, "Status"))
        self.stream(("Email", fv(r, "Source") or "", ""), t0)
        frm = parties(r, "From")
        o = fv(frm[0], "IsPhoneOwner") if frm else None
        d = "outgoing" if is_true(o) else ("incoming" if (o or "").lower() == "false" else "unknown")
        sender = (fv(frm[0], "Identifier") or "").strip() if frm else ""
        recips = sorted((fv(x, "Identifier") or "").strip() for x in parties(r, "To"))
        content = (fv(r, "Subject") or "") + "\x00" + (fv(r, "Body") or "")
        if t0 is not None:
            self.dup[("email", d, sender, tuple(recips),
                      hashlib.sha256(unicodedata.normalize("NFC", content).encode("utf-8", "surrogatepass")).digest())].append(t0)
        if AMOUNT_RE.search(content):
            self.c["s05_m1b_amount_with_currency"]["S3 email"] += 1

    def h_Call(self, r, p, f):
        t0, _ = ts(fv(r, "TimeStamp"))
        d = fv(r, "Direction") or "unknown"
        st = fv(r, "Status") or ""
        self.stream(("Call", fv(r, "Source") or "", ""), t0)
        if d == "Outgoing" or (d == "Incoming" and st in ("Established", "Rejected")):
            self.interact(t0, "Call %s %s" % (d, st if d == "Incoming" else "any"))
        ps = parties(r, "Parties")
        snd = sorted((fv(x, "Identifier") or "").strip() for x in ps if fv(x, "Role") == "From")
        rcv = sorted((fv(x, "Identifier") or "").strip() for x in ps if fv(x, "Role") == "To")
        if t0 is not None:
            self.dup[("call", d, tuple(snd), tuple(rcv), (fv(r, "Duration") or "") + "|" + st)].append(t0)

    def h_Chat(self, r, p, f):
        msgs = r["m"].get("Messages", [])
        ctype = fv(r, "ChatType") or "<absent>"
        cid = (fv(r, "Id") or "").strip()
        if cid:
            self.facts["chat_ids"].add((fv(r, "Source") or "", self.salt.h("chat", cid)))
        n = len(msgs)
        deleted = sum(1 for m in msgs if (m["del"] or "") == "Deleted")
        self.c["s05_m3e"]["chats"] += 1
        if n >= 20:
            self.c["s05_m3e"]["chats with >= 20 messages"] += 1
            if deleted:
                self.c["s05_m3e"]["chats with >= 20 messages and >= 1 deleted"] += 1
        if ctype == "OneOnOne":
            seq = sorted((ts(fv(m, "TimeStamp"))[0], self.direction(m)[0]) for m in msgs if ts(fv(m, "TimeStamp"))[0] is not None)
            pairs = sum(1 for a, b in zip(seq, seq[1:]) if a[1] == "incoming" and b[1] == "outgoing")
            if pairs >= 10:
                self.c["s05_m4b"]["one-to-one chats with >= 10 reply pairs"] += 1
            self.c["s05_m4b"]["one-to-one chats"] += 1
        if ctype == "Group":
            self.c["s05_m4c"]["group chats"] += 1
            if any(is_true(fv(x, "IsGroupAdmin")) for x in r["m"].get("Participants", [])):
                self.c["s05_m4c"]["group chats with an admin flag"] += 1
        t0, _ = ts(fv(r, "StartTime"))

    def h_Attachment(self, r, p, f):
        if r["fid"]:
            self.attachment_file_ids.add(r["fid"])

    # ---- files (03 20.5, 05 M-8a)
    def file(self, el, root):
        fid = el.get("id")
        items = {}
        for md in el:
            if ln(md.tag) == "metadata":
                for it in md:
                    if ln(it.tag) == "item":
                        items[it.get("name")] = (it.text or "").strip()
                        self.file_item_names[it.get("name")] += 1
        cat = items.get("Tags") or "<none>"
        lp = items.get("Local Path") or ""
        md5 = (items.get("MD5") or "").lower()
        name = el.get("name") or lp.rsplit("/", 1)[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "(none)"
        if not re.match(r"^[a-z0-9]{1,6}$", ext):
            ext = "<other>"
        self.files[fid] = (cat, md5, lp)
        self.g.add("d7_category_extension", cat, ext)
        camera = bool(CAMERA_PATH_RE.search(lp.replace("\\", "/"))) or bool(items.get("EXIFCameraMaker") or items.get("EXIFCameraModel"))
        if md5:
            h = self.salt.h("md5", md5)
            self.facts["md5_all"][h] = cat
            if camera:
                self.facts["md5_camera"].add(h)
        if cat in ("Audio", "Video") and lp:
            self.media_probe(os.path.join(root, lp.replace("\\", "/")), cat)

    def media_probe(self, path, cat):
        if not os.path.isfile(path):
            self.c["d7_media"]["%s | not on disk" % cat] += 1
            return
        try:
            p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=format_name:stream=codec_type,codec_name",
                                "-of", "json", path], capture_output=True, text=True, timeout=20)
            info = json.loads(p.stdout or "{}")
        except (subprocess.TimeoutExpired, ValueError):
            self.c["d7_media"]["%s | probe failed" % cat] += 1
            return
        fmt = (info.get("format") or {}).get("format_name") or "unrecognised"
        codecs = ",".join(sorted("%s:%s" % (s.get("codec_type"), s.get("codec_name")) for s in info.get("streams", []))) or "no streams"
        self.c["d7_media"]["%s | %s | %s" % (cat, fmt, codecs)] += 1

    # ---- end of report
    def finish(self, root_attrs):
        out = {"label": self.label}
        # header (01, D3, M11)
        hdr = self.header
        out["header_items_present"] = dict(sorted(self.header_items.items()))
        out["extraction_info"] = self.extraction_info
        dz = [x.strip().lstrip("_") for x in hdr.get("Time zone settings (ID)", [])]
        ex = (self.tz or {}).get("selectedTimeZone")
        exn = ex.lstrip("_") if ex else None
        out["d3_zone"] = {
            "device_setting_present": bool(dz and dz[0]),
            "examiner_zone_present": bool(exn),
            "comparison": ("both absent" if not dz and not exn else "device setting absent" if not dz or not dz[0]
                           else "examiner zone absent" if not exn else ("equal" if dz[0].strip() == exn else "different")),
            "device_settings_count": len(dz),
            "device_settings_all_equal": len(set(x.strip() for x in dz)) <= 1,
            "convert_to_utc": (self.tz or {}).get("enableAutomaticallyConvertToUTC"),
            "daylight_savings": (self.tz or {}).get("enableDaylightSavings"),
        }
        self.facts["zone_pair"] = (dz, ex)
        # seed (D2)
        out["seed"] = {
            "types": dict(sorted(self.types.items())),
            "fields": [[t, f, k, vt, n] for (t, f, k, vt), n in sorted(self.fields.items(), key=lambda x: tuple(map(str, x[0])))],
            "named_sets": {k: sorted(v) for k, v in sorted(self.enums.items())},
            "nesting": [[a, b, c, d, n] for (a, b, c, d), n in sorted(self.nesting.items(), key=lambda x: tuple(map(str, x[0])))],
        }
        # duplicates (03 20.1)
        dupres = collections.Counter()
        for (kind, *_), inst in self.dup.items():
            if len(inst) < 2:
                continue
            inst.sort()
            for tol, name in ((0.0, "exact"), (1.0, "1s"), (2.0, "2s")):
                groups = 0
                members = 0
                i = 0
                while i < len(inst):
                    j = i
                    while j + 1 < len(inst) and inst[j + 1] - inst[j] <= tol + 1e-9:
                        j += 1
                    if j > i:
                        groups += 1
                        members += j - i + 1
                    i = j + 1
                dupres["%s | %s | groups" % (kind, name)] += groups
                dupres["%s | %s | records" % (kind, name)] += members
            secs = collections.Counter(int(x) for x in inst)
            dupres["%s | same second | groups" % kind] += sum(1 for v in secs.values() if v > 1)
            near = sum(1 for a, b in zip(inst, inst[1:]) if 2.0 < b - a <= 60.0)
            dupres["%s | equal key, 2-60 s apart | adjacent pairs" % kind] += near
        out["d4_duplicates"] = dict(sorted(dupres.items()))
        out["d4_events_with_instant"] = {k: sum(len(v) for kk, v in self.dup.items() if kk[0] == k) for k in ("message", "email", "call")}
        # code points (03 20.6)
        out["d6_codepoints"] = {"totals": dict(self.cp_total), "styled": dict(sorted(self.cp_styled.items())),
                                "by_name_first_word": dict(sorted(self.cp_name.items())),
                                "by_128_range": dict(sorted(self.cp_range.items()))}
        # files (03 20.5, 05 M-8a)
        attach = (self.attachment_file_ids | self.jt_file_ids) & set(self.files)
        for fid in attach:
            md5 = self.files[fid][1]
            if md5:
                self.facts["md5_attach"].add(self.salt.h("md5", md5))
        out["s05_m8a"] = {"tagged files": len(self.files), "attachment-linked files": len(attach),
                          "attachment-linked with MD5": len(self.facts["md5_attach"]),
                          "camera-path or camera-EXIF files with MD5": len(self.facts["md5_camera"])}
        out["file_metadata_item_names"] = {k: v for k, v in sorted(self.file_item_names.items()) if k and GUARD_RE.match(k)}
        # M-3d reply and quote references
        idents = {v for k, v in self.ident_values if k == "msg_ident"}
        m3d = collections.Counter()
        for kind, ref in self.reply_refs:
            m3d[kind + " records"] += 1
            if ref:
                m3d[kind + " with OriginalMessageID"] += 1
                m3d[kind + (" referencing an Identifier on the phone" if ref in idents else " referencing no Identifier on the phone")] += 1
        out["s05_m3d"] = dict(m3d)
        out["s05_m1a_distinct_service_identifiers"] = len({v for k, v in self.ident_values if k == "notif_si"})
        out["s05_x3_body_occurrence"] = {"distinct bodies >= 10 chars": len(self.body_occ),
                                         "occurring <= 3 times": sum(1 for v in self.body_occ.values() if v <= 3)}
        # streams (M4), power (M8), extraction edges (M11), daily coverage (M12)
        out.update(self.time_measures())
        out["guarded"] = self.g.out()
        out["counts"] = {k: dict(sorted(v.items())) for k, v in sorted(self.c.items()) if v}
        out["d1_root_attributes"] = root_attrs
        return out

    def time_measures(self):
        res = {}
        starts = [x for x in (parse_header_dt(v) for v in self.header.get("DeviceInfoExtractionStartDateTime", [])) if x is not None]
        ends = [x for x in (parse_header_dt(v) for v in self.header.get("DeviceInfoExtractionEndDateTime", [])) if x is not None]
        start = min(starts) if starts else None
        end = max(ends) if ends else None
        self.c["m11_header_values"]["start values"] = len(self.header.get("DeviceInfoExtractionStartDateTime", []))
        self.c["m11_header_values"]["start values parsed"] = len(starts)
        self.c["m11_header_values"]["start values distinct instants"] = len(set(starts))
        # M4
        m4 = {}
        all_inst = array.array("d")
        fam_first_last = {}
        after = collections.Counter()
        for key, arr in self.streams.items():
            vals = sorted(arr)
            all_inst.extend(vals)
            fam = family(key[0])
            if vals:
                lo, hi = fam_first_last.get(fam, (vals[0], vals[-1]))
                fam_first_last[fam] = (min(lo, vals[0]), max(hi, vals[-1]))
            if start is not None:
                after[fam] += len(vals) - bisect.bisect_right(vals, start)
            gaps = sorted(b - a for a, b in zip(vals, vals[1:]))
            by_hour = collections.defaultdict(list)
            for a, b in zip(vals, vals[1:]):
                by_hour[int(a // 3600 % 24)].append(b - a)
            label = key
            entry = {"events": len(vals), "gap_seconds": quantiles(gaps)}
            entry["gap_p50_p95_by_utc_hour"] = {"h%02d" % h: [round(sorted(v)[len(v) // 2], 1), round(sorted(v)[min(len(v) - 1, int(0.95 * len(v)))], 1)]
                                                for h, v in sorted(by_hour.items())}
            m4[label] = entry
        occ = collections.Counter()
        for key, e in m4.items():
            for part in key[1:]:
                occ[part] += e["events"]
        guarded = {}
        for key, e in m4.items():
            parts = [key[0]] + [p if (not p or (GUARD_RE.match(p) and occ[p] >= 3)) else "<other>" for p in key[1:]]
            lab = " | ".join(x for x in parts if x)
            if lab in guarded:  # several guarded-out sources share one label: keep counts, drop their gap figures
                g0 = guarded[lab]
                guarded[lab] = {"events": g0["events"] + e["events"], "gap_seconds": None, "merged_streams": g0.get("merged_streams", 1) + 1}
            else:
                guarded[lab] = e
        res["m4_streams"] = guarded
        # DeviceConnectivity Paired StartTime gap to the next Connected event of the same device name
        conn = collections.defaultdict(list)
        for h, nat, s in self.durations.get("_conn", []):
            conn[h].append((s, nat))
        pg = collections.Counter()
        for h, evs in conn.items():
            evs.sort()
            for i, (s, nat) in enumerate(evs):
                if nat == "Paired":
                    nxt = next((s2 for s2, n2 in evs[i + 1:] if n2 == "Connected"), None)
                    pg[log_bucket(nxt - s) if nxt is not None else "no later Connected"] += 1
        res["m4_paired_to_next_connected"] = dict(pg)
        acc = sorted(self.durations.get("m5_accuracy_m", []))
        res["m5_accuracy_m_quantiles"] = quantiles(acc)
        # M5: BSSIDs with a GPS observation within 5 minutes on 2 or more days
        res["m5_bssid_gps_days"] = bssid_gps_days(self.facts["bssid_obs"], self.facts["loc"])
        # M8 power sequences
        seq = sorted(self.power_seq)
        pc = collections.Counter()
        all_sorted = sorted(all_inst)
        for (t1, s1, _), (t2, s2, _) in zip(seq, seq[1:]):
            pc["%s after %s" % (s2, s1)] += 1
        gaps_before_on = []
        for t0, s, _ in seq:
            if s == "On":
                i = bisect.bisect_left(all_sorted, t0)
                if i > 0:
                    gaps_before_on.append(t0 - all_sorted[i - 1])
        res["m8_power"] = {"events": collections.Counter(s + " " + src for _, s, src in seq), "sequences": dict(pc),
                           "gap_before_on_seconds": dict(collections.Counter(log_bucket(g) for g in gaps_before_on))}
        # M11
        m11 = {"extraction_start_parsed": start is not None, "extraction_end_parsed": end is not None,
               "extraction_duration_hours": round((end - start) / 3600, 2) if (start is not None and end is not None) else None,
               "family_first_last_days_from_start": {}, "events_after_extraction_start": dict(after)}
        if start is not None:
            for fam, (lo, hi) in sorted(fam_first_last.items()):
                m11["family_first_last_days_from_start"][fam] = [round((lo - start) / 86400, 1), round((hi - start) / 86400, 1)]
        sel = collections.Counter()
        for info in self.extraction_info:
            for k in ("IsSelectiveExtraction", "IsPartialData", "IsStoppedByUser"):
                sel["%s=%s" % (k, info.get(k))] += 1
        m11["selection_attributes"] = dict(sel)
        res["m11"] = m11
        # M12 (UTC days; the device zone is not applied at this stage)
        res["m12"] = daily_coverage(self.interaction, self.streams)
        self.facts["interaction_days"] = {int(t // 86400) for t in self.interaction}
        self.facts["interaction_bins"] = {int(t // 900) for t in self.interaction}
        return res


SMALL_CAPS = {0x1D00, 0x0299, 0x1D04, 0x1D05, 0x1D07, 0xA730, 0x0262, 0x029C, 0x026A, 0x1D0A, 0x1D0B, 0x029F,
              0x1D0D, 0x0274, 0x1D0F, 0x1D18, 0x0280, 0xA731, 0x1D1B, 0x1D1C, 0x1D20, 0x1D21, 0x028F, 0x1D22}

FAMILY = {"DeviceEvent": "device_events", "PoweringEvent": "power", "AppsUsageLog": "app_usage",
          "ApplicationUsage": "app_usage", "NetworkUsage": "network_usage", "InstantMessage": "messages",
          "Call": "calls", "VisitedPage": "web", "SearchedItem": "search", "Location": "locations",
          "Journey": "locations", "WirelessNetwork": "wifi", "CellTower": "cell", "DeviceConnectivity": "connectivity",
          "ActivitySensorData": "sensors", "ActivitySensorDataSample": "sensors", "Notification": "notifications",
          "LogEntry": "logs", "Email": "email", "SocialMediaActivity": "social"}
OBSERVING = {"device_events": 7200, "connectivity": 7200, "sensors": 3600}


def family(t):
    return FAMILY.get(t, "other")


def top_level(parent):
    return parent is None


def parse_header_dt(text):
    """Extraction start and end in the header use `M/DD/YYYY HH:MM:SS AM -HH:MM` or ISO; None otherwise."""
    if not text:
        return None
    s = text.strip()
    v, st = ts(s)
    if v is not None:
        return v
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4}) (\d{1,2}):(\d\d):(\d\d)(?: ?([AP]M))? ?(?:\(?(?:UTC|GMT)?([+-]\d{1,2})(?::?(\d\d))?\)?)?$", s)
    if not m:
        return None
    mo, d, y, hh, mi, ss = (int(m.group(i)) for i in range(1, 7))
    if mo > 12 or d > 31:
        return None  # not month/day/year
    if m.group(7):
        hh = hh % 12 + (12 if m.group(7) == "PM" else 0)
    if not m.group(8):
        return None  # no offset: not placed in time (01 section 9.4)
    secs = calendar.timegm((y, mo, d, hh, mi, ss, 0, 0, 0))
    sign = 1 if m.group(8)[0] == "+" else -1
    return secs - sign * (int(m.group(8)[1:]) * 3600 + int(m.group(9) or 0) * 60)


def bssid_gps_days(bssid_obs, loc):
    """Per phone: BSSIDs with at least one GPS observation within 5 minutes on 2 or more distinct UTC days,
    at accuracy <= 100 m and at comparison radius (2 x accuracy) <= 100 m (04 section 6.2)."""
    pts = sorted((t, a) for t, lat, lon, a, aff in loc if a is not None)
    times = [p[0] for p in pts]
    res = {}
    for name, limit in (("accuracy_le_100m", 100.0), ("radius_2x_le_100m", 50.0)):
        days = collections.defaultdict(set)
        for h, t in bssid_obs:
            i = bisect.bisect_left(times, t - 300)
            while i < len(pts) and pts[i][0] <= t + 300:
                if pts[i][1] <= limit:
                    days[h].add(int(t // 86400))
                    break
                i += 1
        res[name] = sum(1 for v in days.values() if len(v) >= 2)
    res["distinct_bssids_with_time"] = len({h for h, _ in bssid_obs})
    return res


def daily_coverage(interaction, streams):
    days_inter = collections.defaultdict(set)
    for t in interaction:
        days_inter[int(t // 86400)].add(int(t // 3600 % 24))
    # observed hours: hours covered >= 50 minutes by observed segments of observing streams (04 5.3 defaults)
    covered = collections.defaultdict(float)
    for key, arr in streams.items():
        fam = family(key[0])
        if fam == "network_usage":
            max_gap = 3600 * 1.1  # provisional: bucket width + 10 percent, refined from M4
        else:
            max_gap = OBSERVING.get(fam)
        if not max_gap:
            continue
        vals = sorted(arr)
        if not vals:
            continue
        seg_lo = seg_hi = vals[0]
        segs = []
        for v in vals[1:]:
            if v - seg_hi <= max_gap:
                seg_hi = v
            else:
                segs.append((seg_lo, seg_hi))
                seg_lo = seg_hi = v
        segs.append((seg_lo, seg_hi))
        for lo, hi in segs:
            h = int(lo // 3600)
            while h * 3600 < hi:
                a, b = max(lo, h * 3600), min(hi, (h + 1) * 3600)
                if b > a:
                    covered[(key, h)] += b - a
                h += 1
    hour_obs = collections.defaultdict(float)
    for (key, h), secs in covered.items():
        hour_obs[h] = max(hour_obs[h], secs)
    observed_hours = {h for h, s in hour_obs.items() if s >= 3000}
    obs_per_day = collections.Counter(h // 24 for h in observed_hours)
    rich_days = {d for d, n in obs_per_day.items() if n >= 12}
    out = {"days_with_candidate_interaction": len(days_inter), "days_with_12_or_more_observed_hours": len(rich_days),
           "observed_hours_total": len(observed_hours)}
    for th in (0.05, 0.10, 0.20):
        if not rich_days:
            out["quiet_run_at_%.2f" % th] = None
            continue
        f = [sum(1 for d in rich_days if h in days_inter.get(d, ())) / len(rich_days) for h in range(24)]
        best = (0, None)
        for s in range(24):
            n = 0
            while n < 24 and f[(s + n) % 24] <= th:
                n += 1
            if n > best[0]:
                best = (n, s)
        out["quiet_run_at_%.2f" % th] = {"hours": best[0], "start_utc_hour": best[1]} if best[0] >= 3 else {"hours": best[0], "start_utc_hour": None}
    return out


def run(label, spec, out_dir, salt, markers):
    root = spec["root"]
    xml = os.path.join(root, spec["report"])
    rep = Report(label, salt, markers)
    t_start = time.monotonic()
    stack = []
    els = []
    root_attrs = {}
    with open(xml, "rb") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = ln(el.tag)
            if ev == "start":
                if not stack:
                    root_attrs = {k: el.get(k) for k in ("reportVersion", "extractionType", "NodeCount", "ModelCount")}
                stack.append(tag)
                els.append(el)
                if tag == "extractionInfo":
                    rep.extraction_info.append({k: el.get(k) for k in ("IsPartialData", "IsSelectiveExtraction", "IsStoppedByUser", "type")})
                continue
            stack.pop()
            els.pop()
            parent = stack[-1] if stack else None
            if tag == "model" and parent == "modelType":
                rec = conv(el)
                for r, p, f in walk(rec):
                    rep.seed(r, p, f)
                    rep.handle(r, p, f, p is None)
                rep.top_types[rec["t"]] += 1
                el.clear()
                els[-1].remove(el)
            elif tag == "file" and parent == "taggedFiles":
                rep.file(el, root)
                el.clear()
                els[-1].remove(el)
            elif tag == "item" and parent == "metadata" and "taggedFiles" not in stack and "decodedData" not in stack:
                name = el.get("name")
                rep.header_items[name] += 1
                rep.header.setdefault(name, []).append((el.text or "").strip())
                if name in HEADER_IDS and (el.text or "").strip():
                    rep.facts["ident"].setdefault(name, set()).add(salt.h("hdr:" + name, (el.text or "").strip()))
            elif tag == "timeZoneConfigurations":
                rep.tz = dict(el.attrib)
            elif tag in ("modelType", "taggedFiles", "decodedData", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
            elif parent in ("extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
                els[-1].remove(el)
    out = rep.finish(root_attrs)
    out["top_level_types"] = dict(sorted(rep.top_types.items()))
    with open(os.path.join(out_dir, label + ".counts.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=lambda o: dict(o) if isinstance(o, collections.Counter) else str(o))
    facts = dict(rep.facts)
    facts["keys"] = dict(facts["keys"])
    facts["markers"] = dict(facts["markers"])
    with open(os.path.join(out_dir, label + ".facts.pkl"), "wb") as fh:
        pickle.dump(facts, fh, protocol=4)
    os.chmod(os.path.join(out_dir, label + ".facts.pkl"), 0o600)
    import resource
    print(json.dumps({"label": label, "records_top": sum(rep.top_types.values()), "files": len(rep.files),
                      "seconds": round(time.monotonic() - t_start, 1),
                      "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}), flush=True)


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    out_dir = argv[1]
    os.makedirs(out_dir, exist_ok=True)
    salt = Salt(os.path.join(out_dir, "salt.bin"))
    for label in argv[2].split(","):
        run(label, corpus[label], out_dir, salt, "--markers" in argv)


if __name__ == "__main__":
    main(sys.argv[1:])
