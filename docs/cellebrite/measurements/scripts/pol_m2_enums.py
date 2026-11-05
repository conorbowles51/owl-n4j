"""M2 (04 section 13): the value sets the mapping rows depend on.

usage: python3 -I pol_m2_enums.py <corpus.json> <out.json> [P01,P02,...]

<corpus.json> maps a label to {"root", "report"} (the private corpus map; never committed). Each named report is
streamed with iterparse, one at a time. The result for each label replaces that label's entry in <out.json> (other
labels are kept), so a run can be split.

Measures, per report: UserMapping per type; Location Type, Category, Precision, Source; AppsUsageLog Source x Action;
SearchedItem Source x Origin x has TimeStamp; Email Folder x Status x From party IsPhoneOwner x has TimeStamp;
InstantMessage Folder x Status x Platform x From party IsPhoneOwner x Type; what each folder's name says (FOLDER_WORDS)
as booleans; Notification Status x Type;
DeviceConnectivity Nature x Method x DeviceType; the written shape of ApplicationUsage's durations, zero or not, and
which of its time fields a record carries, and EndTime minus StartTime.

Counts only (04 section 13 guards): a String value is written only if it matches GUARD_RE and occurs at least 3 times
in the report for that measure, else `<other>`. A mail folder can be named by its owner, so `pol_m2_commit.py` keeps
a folder value in the committed file only when it is on at least two reports of different cases.
"""
import collections
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

GUARD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$")
WANTED = {"Location", "AppsUsageLog", "SearchedItem", "Email", "InstantMessage", "Notification", "DeviceConnectivity",
          "ApplicationUsage"}
# what a mail or message folder's name says, as booleans: the name itself may be the owner's own, so it is not written
FOLDER_WORDS = (("sent", ("sent", "enviad", "envoy", "gesendet", "inviat", "verzonden")), ("draft", ("draft", "borrador", "brouillon", "entwu", "bozza")),
                ("outbox", ("outbox", "bandeja de salida", "boite d'envoi", "postausgang")),
                ("inbox", ("inbox", "bandeja de entrada", "recibidos", "eingang", "boite de reception")),
                ("trash", ("trash", "deleted", "bin", "papelera", "corbeille", "papierkorb", "eliminad")),
                ("spam", ("spam", "junk")), ("archive", ("archive", "all mail", "archivo", "todos")),
                ("important", ("important", "starred", "flagged")))
SPAN_RE = re.compile(r"^(?:(\d+)\.)?(\d+):(\d\d):(\d\d)(?:\.\d+)?$")


def ln(t):
    return t.rsplit("}", 1)[-1]


def conv(m):
    r = {"t": m.get("type"), "f": {}, "m": {}}
    for c in m:
        tag = ln(c.tag)
        if tag in ("field", "multiField"):
            r["f"][c.get("name")] = [v.text or "" for v in c if ln(v.tag) == "value"]
        elif tag in ("modelField", "multiModelField"):
            r["m"][c.get("name")] = [conv(x) for x in c if ln(x.tag) == "model"]
    return r


def fv(r, name):
    v = r["f"].get(name)
    return v[0] if v else None


def owner_from(rec):
    """True/False when the record's From party states IsPhoneOwner, else the marker for absent."""
    kids = rec["m"].get("From") or []
    if not kids:
        return "\x01<no From party>"
    v = fv(kids[0], "IsPhoneOwner")
    return "\x01<no IsPhoneOwner>" if v is None else "\x01From owner " + ("True" if v == "True" else "False")


def shape(text):
    if text is None:
        return "\x01<absent>"
    return "\x01" + re.sub(r"\d", "9", text.strip())[:24]


def folder_kind(name):
    if name is None:
        return "\x01<absent>"
    low = name.lower()
    hit = [k for k, words in FOLDER_WORDS if any(w in low for w in words)]
    return "\x01" + ("+".join(hit) if hit else "<no system word>")


def width(a, b):
    """EndTime minus StartTime in seconds, or None."""
    fmt = re.compile(r"^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)")
    ma, mb = fmt.match(a or ""), fmt.match(b or "")
    if not ma or not mb:
        return None
    import calendar
    ta = calendar.timegm(tuple(int(x) for x in ma.groups()) + (0, 0, 0))
    tb = calendar.timegm(tuple(int(x) for x in mb.groups()) + (0, 0, 0))
    return tb - ta


def span(text):
    """A TimeSpan's seconds, or None when it is not written as one."""
    if text is None:
        return None
    m = SPAN_RE.match(text.strip())
    if m:
        d, h, mi, s = m.groups()
        return int(d or 0) * 86400 + int(h) * 3600 + int(mi) * 60 + int(s)
    try:
        return float(text)
    except ValueError:
        return None


class Guarded:
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
                    elif p.startswith("\x01"):
                        key.append(p[1:])
                    elif GUARD_RE.match(p) and occ[p] >= 3:
                        key.append(p)
                    else:
                        key.append("<other>")
                g[" | ".join(key)] += n
            res[measure] = dict(sorted(g.items()))
        return res


def one(r, g):
    t = r["t"]
    g.add("usermapping_by_type", "\x01" + t, fv(r, "UserMapping"))
    if t == "Location":
        for f in ("Type", "Category", "Precision", "Source"):
            g.add("location_" + f.lower(), fv(r, f))
    elif t == "AppsUsageLog":
        g.add("appsusagelog_source_x_action", fv(r, "Source"), fv(r, "Action"))
    elif t == "SearchedItem":
        g.add("searcheditem_source_x_origin_x_timestamp", fv(r, "Source"), fv(r, "Origin"),
              "\x01TimeStamp" if fv(r, "TimeStamp") else "\x01no TimeStamp")
    elif t == "Email":
        g.add("email_folder_x_status_x_from_x_timestamp", fv(r, "Folder"), fv(r, "Status"), owner_from(r),
              "\x01TimeStamp" if fv(r, "TimeStamp") else "\x01no TimeStamp")
        g.add("email_source", fv(r, "Source"))
        g.add("email_foldertoken_x_status_x_from", folder_kind(fv(r, "Folder")), fv(r, "Status"), owner_from(r))
    elif t == "InstantMessage":
        g.add("im_folder_x_status_x_platform_x_from_x_type", fv(r, "Folder"), fv(r, "Status"), fv(r, "Platform"),
              owner_from(r), fv(r, "Type"))
        g.add("im_foldertoken_x_status_x_from_x_platform", folder_kind(fv(r, "Folder")), fv(r, "Status"), owner_from(r), fv(r, "Platform"))
    elif t == "Notification":
        g.add("notification_status_x_type", fv(r, "Status"), fv(r, "Type"))
    elif t == "DeviceConnectivity":
        g.add("deviceconnectivity_nature_x_method_x_devicetype", fv(r, "Nature"), fv(r, "Method"), fv(r, "DeviceType"))
    elif t == "ApplicationUsage":
        for f in ("ActiveTime", "BackgroundTime", "LastUsageDuration"):
            v = fv(r, f)
            secs = span(v)
            state = "<absent>" if v is None else "unreadable" if secs is None else "zero" if secs == 0 else "above zero"
            g.add("appusage_duration_shape", "\x01" + f, shape(v), "\x01" + state)
        w = width(fv(r, "StartTime"), fv(r, "EndTime"))
        g.add("appusage_end_minus_start_s", "\x01none" if w is None else "\x01%d" % w)
        g.add("appusage_source", fv(r, "Source"))
        g.add("appusage_time_fields",
              *("\x01%s %s" % (f, "yes" if fv(r, f) else "no") for f in ("StartTime", "EndTime", "LastLaunch")),
              "\x01ActiveTime " + ("yes" if (span(fv(r, "ActiveTime")) or 0) > 0 else "no"))


def walk(r):
    yield r
    for kids in r["m"].values():
        for k in kids:
            yield from walk(k)


def measure(xml):
    g = Guarded()
    stack, els = [], []
    started = time.monotonic()
    with open(xml, "rb") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = ln(el.tag)
            if ev == "start":
                stack.append(tag)
                els.append(el)
                continue
            stack.pop()
            els.pop()
            parent = stack[-1] if stack else None
            if tag == "model" and parent == "modelType":
                rec = conv(el)
                for r in walk(rec):
                    if r["t"] in WANTED:
                        one(r, g)
                    elif fv(r, "UserMapping") is not None:
                        g.add("usermapping_by_type", "\x01" + r["t"], fv(r, "UserMapping"))
                el.clear()
                els[-1].remove(el)
            elif tag in ("modelType", "taggedFiles", "decodedData"):
                el.clear()
            elif parent in ("taggedFiles", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
                els[-1].remove(el)
    out = g.out()
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


def main(corpus, out_path, only):
    reports = json.load(open(corpus, encoding="utf-8"))
    res = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {"measure": "M2", "reports": {}}
    for label in only or sorted(reports):
        e = reports[label]
        res["reports"][label] = measure(os.path.join(e["root"], e["report"]))
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, sort_keys=True)
        os.replace(tmp, out_path)
        print(label, res["reports"][label]["seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3].split(",") if len(sys.argv) > 3 else None)
