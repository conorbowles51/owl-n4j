"""Build the phone registry seed (02 section 3.5) from the committed structural catalogues.

    python scripts/phone_registry_seed_build.py --measurements ../docs/cellebrite/measurements \
        --counter-dir /mnt/owl-data/cellebrite-corpus/counter --out services/phone/data/registry_seed_2026-10-29.json

Inputs, structure only:

- ``catalogue-14-phones.json`` (14 server reports) and ``catalogue-local-samples.json`` (the local C3, C9, C8):
  17 documents, kept separate (3.5 step 1). Types, typed field rows and named-set values (steps 2 to 4).
- ``a3/summary.json``: the 95 nesting relations measured on the 14 server reports (step 6), unioned with the 47
  measured on C3, C9, C8 (3.6, ``LOCAL_NESTING`` below).
- ``--counter-dir``: the element counter's per-path outputs for the 14 server reports (01 section 8; kept on the
  server, never committed). Two things the catalogue could not record come from them (02 decision 40):
  the attribute names of ``model``, ``extractionInfo``, ``project``, ``file`` and ``value`` (step 7; the Mac
  ``c*.json`` files the spec names are not on the server, plan decision 2), and the field combinations that carry
  no typed value anywhere, which ``catalog.py`` skips by construction: fields only ever ``<empty/>``
  (value type ``(empty)``) and ``nodeField``/``dataField`` children with no typed value (``(none)``).

The output holds names, kinds, value types, counts and named-set vocabulary only; no path, no String, time,
number or GUID from a report (the U2 test scans it).
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os

BASIC = ("String", "TimeStamp", "TimeSpan", "Guid", "Boolean", "Int32", "Int64", "Double", "UInt32")
FIELD_KINDS = ("field", "multiField", "modelField", "multiModelField", "nodeField", "dataField")
VALUE_FIELD_KINDS = ("field", "multiField", "nodeField", "dataField")
ATTRIBUTE_ELEMENTS = ("model", "extractionInfo", "project", "file", "value")

# 02 section 3.6: the 47 relations measured on C3, C9, C8 (parent, field, kind, child).
_M, _MM = "modelField", "multiModelField"
LOCAL_NESTING = [
    ("Call", "Parties", _MM, "Party"),
    ("CalendarEntry", "Attendees", _MM, "Party"),
    ("Chat", "Participants", _MM, "Party"), ("Chat", "Messages", _MM, "InstantMessage"),
    ("Chat", "ActivityLog", _MM, "ChatActivity"), ("Chat", "Photos", _MM, "ContactPhoto"),
    ("ChatActivity", "Participant", _M, "Party"),
    ("Contact", "Entries", _MM, "PhoneNumber"), ("Contact", "Entries", _MM, "UserID"),
    ("Contact", "Entries", _MM, "EmailAddress"), ("Contact", "Entries", _MM, "ProfilePicture"),
    ("Contact", "Entries", _MM, "WebAddress"),
    ("Contact", "Addresses", _MM, "StreetAddress"), ("Contact", "Photos", _MM, "ContactPhoto"),
    ("Contact", "AdditionalInfo", _MM, "KeyValueModel"),
    ("DeviceEvent", "Additional_Info", _MM, "KeyValueModel"),
    ("Email", "From", _M, "Party"), ("Email", "To", _MM, "Party"), ("Email", "Cc", _MM, "Party"),
    ("Email", "Attachments", _MM, "Attachment"),
    ("FileDownload", "AdditionalInfo", _MM, "KeyValueModel"), ("FileUpload", "AdditionalInfo", _MM, "KeyValueModel"),
    ("FileUpload", "Owner", _M, "Party"),
    ("InstantMessage", "From", _M, "Party"), ("InstantMessage", "Attachment", _M, "Attachment"),
    ("InstantMessage", "To", _MM, "Party"), ("InstantMessage", "Attachments", _MM, "Attachment"),
    ("InstantMessage", "MessageExtraData", _MM, "MessageLabel"),
    ("InstantMessage", "MessageExtraData", _MM, "ReplyMessageData"),
    ("InstantMessage", "MessageExtraData", _MM, "ForwardedMessageData"),
    ("InstantMessage", "MessageExtraData", _MM, "QuotedMessageData"),
    ("InstantMessage", "SharedContacts", _MM, "Contact"),
    ("Location", "Position", _M, "Coordinate"), ("Location", "Address", _M, "StreetAddress"),
    ("WirelessNetwork", "Position", _M, "Coordinate"),
    ("NetworkUsage", "AdditionalInfo", _MM, "KeyValueModel"),
    ("RecognizedDevice", "AdditionalInfo", _MM, "KeyValueModel"),
    ("RecognizedDevice", "DeviceIdentifiers", _MM, "KeyValueModel"),
    ("SocialMediaActivity", "Author", _M, "Party"), ("SocialMediaActivity", "ParentPost", _M, "SocialMediaActivity"),
    ("SocialMediaActivity", "Attachments", _MM, "Attachment"),
    ("UserAccount", "Entries", _MM, "PhoneNumber"), ("UserAccount", "Entries", _MM, "UserID"),
    ("UserAccount", "Entries", _MM, "EmailAddress"), ("UserAccount", "Entries", _MM, "ProfilePicture"),
    ("UserAccount", "Photos", _MM, "ContactPhoto"), ("UserAccount", "AdditionalInfo", _MM, "KeyValueModel"),
]

ACKNOWLEDGED_DRIFT = {
    "type_name": "ChatActivity", "field_name": "SystemMessageId", "field_kind": "field", "value_type": "String",
    "previous": ["Guid"],
    "reason": "Seen in the catalogue: String 25 values, Guid 277 values, across 6 reports",
}


def _documents(measurements):
    docs = []
    for name in ("catalogue-14-phones.json", "catalogue-local-samples.json"):
        with open(os.path.join(measurements, name)) as fh:
            docs.extend(json.load(fh)["phones"])
    return docs


def _seg(seg):
    base = seg.split("[", 1)[0]
    name = seg[len(base) + 1:-1] if "[" in seg else None
    return base, name


def counter_structure(counter_dir):
    """Attribute names per element, and per (type, field, kind) the child element names, over the 14 reports."""
    attrs = collections.defaultdict(set)
    children = collections.defaultdict(lambda: collections.defaultdict(set))  # (t, f, k) -> child -> reports
    files = sorted(f for f in glob.glob(os.path.join(counter_dir, "P*-lxml.json")) if not f.endswith("lxml2.json"))
    for fn in files:
        report = os.path.basename(fn).split("-", 1)[0]
        with open(fn) as fh:
            paths = json.load(fh)["paths"]
        for p, c in paths.items():
            segs = [_seg(s) for s in p.split("/")]
            base = [s[0] for s in segs]
            if base[-1] in ATTRIBUTE_ELEMENTS and (base[-1] != "value" or (len(base) > 1 and base[-2] in FIELD_KINDS)):
                attrs[base[-1]].update(c["attributes"])
            if len(segs) >= 3 and base[-2] in VALUE_FIELD_KINDS and base[-3] == "model":
                key = (segs[-3][1], segs[-2][1], base[-2])
                children[key][base[-1]].add(report)
    return {k: sorted(v) for k, v in attrs.items()}, children, len(files)


def build(measurements, counter_dir):
    docs = _documents(measurements)
    types = collections.OrderedDict()
    for d in docs:
        for t, n in d["model_types"].items():
            row = types.setdefault(t, {"type_name": t, "seed_report_count": 0, "seed_record_count": 0})
            row["seed_report_count"] += 1
            row["seed_record_count"] += n
    fields = {}
    for d in docs:
        for t, f, k, counts in d["catalog"]:
            for vt, n in counts.items():
                row = fields.setdefault((t, f, k, vt), {
                    "type_name": t, "field_name": f, "field_kind": k, "value_type": vt,
                    "is_named_set": vt not in BASIC, "seed_value_count": 0, "seed_report_count": 0, "basis": "catalogue"})
                row["seed_value_count"] += n
                row["seed_report_count"] += 1
    sets = {}
    for d in docs:
        for s, vals in d["enums"].items():
            if s in BASIC:
                continue
            for v in vals:
                sets.setdefault((s, v), {"set_name": s, "value": v, "note": None})
    sets[("DecodingSourceOptions", "Decoding")] = {
        "set_name": "DecodingSourceOptions", "value": "Decoding",
        "note": "From the C3, C9, C8 stream measurement (02 section 2); catalog.py skips this type"}
    sets[("@decoding_confidence", "High")] = {
        "set_name": "@decoding_confidence", "value": "High",
        "note": "Pseudo-set of the model attribute decoding_confidence (02 section 5.2); High only, measured"}
    with open(os.path.join(measurements, "a3", "summary.json")) as fh:
        server_nesting = json.load(fh)["seed_02_U2"]["total"]["nesting_relations_list"]
    nesting = {}
    for rel in LOCAL_NESTING:
        nesting[tuple(rel)] = {"basis": ["local_samples"]}
    for rel in server_nesting:
        nesting.setdefault(tuple(rel), {"basis": []})
        if "server_reports" not in nesting[tuple(rel)]["basis"]:
            nesting[tuple(rel)]["basis"].append("server_reports")
    attributes, children, n_counter = ({}, {}, 0) if not counter_dir else counter_structure(counter_dir)
    typed = {k[:3] for k in fields}
    for (t, f, k), kids in sorted(children.items()):
        if (t, f, k) in typed or "value" in kids:
            continue
        reports = set().union(*kids.values())
        vt = "(empty)" if (k in ("field", "multiField") and set(kids) == {"empty"}) else "(none)"
        if t not in types:
            raise SystemExit("counter type %s not in the catalogue" % t)
        fields[(t, f, k, vt)] = {"type_name": t, "field_name": f, "field_kind": k, "value_type": vt,
                                 "is_named_set": False, "seed_value_count": 0, "seed_report_count": len(reports),
                                 "basis": "counter"}
    return {
        "source": ("Structure only. Catalogues of 17 report documents (14 server reports and the 3 local samples) "
                   "read 2026-10-29; nesting from 02 section 3.6 and the A3 server batch; attribute names and the "
                   "fields with no typed value from the element counter on the 14 server reports (02 decision 40)."),
        "counter_reports": n_counter,
        "types": list(types.values()),
        "fields": [fields[k] for k in sorted(fields)],
        "set_values": [sets[k] for k in sorted(sets)],
        "nesting": [{"parent_type": p, "field_name": f, "field_kind": k, "child_type": c, "basis": v["basis"]}
                    for (p, f, k, c), v in sorted(nesting.items())],
        "attributes": [{"element": e, "attribute": a} for e in sorted(attributes) for a in attributes[e]],
        "acknowledged_flags": [dict(ACKNOWLEDGED_DRIFT, flag_kind="new_value_type")],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--measurements", required=True)
    ap.add_argument("--counter-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    seed = build(a.measurements, a.counter_dir)
    with open(a.out, "w") as fh:
        json.dump(seed, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    print({k: len(v) for k, v in seed.items() if isinstance(v, list)})


if __name__ == "__main__":
    main()
