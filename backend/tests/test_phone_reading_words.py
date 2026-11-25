"""Readings as plain sentences (Phones › Set up): no prompt names a type or field as the report spells it, every
part says what changes if it is wrong, and the sentences come from the reading's own mapping data."""
from __future__ import annotations

import itertools
import re

from services.phone import reading_words as W

PARTS = ("event_time", "meaning", "end_time", "role", "owner_implicit", "text", "thread", "record", "activity",
         "attribution")
# conditions as the catalogue writes them (every field/op pair on the live readings, 25 Nov 2026)
CONDS = [{"name": "direction", "op": "eq", "value": "incoming"}, {"name": "party_is_owner", "op": "eq", "value": False},
         {"field": "Direction", "op": "eq", "value": "Outgoing"}, {"field": "Status", "op": "eq", "value": "Rejected"},
         {"field": "EventType", "op": "eq", "value": "AirplaneMode"},
         {"field": "Status", "op": "in", "value": ["Missed", "NotEstablishedUnknownReason"]},
         {"field": "Platform", "op": "in", "value": ["Mobile", "Unknown"]}, {"field": "UsageMode", "op": "eq", "value": "Background"},
         {"field": "Value", "op": "eq", "value": "Locked"}, {"field": "Platform", "op": "absent"},
         {"field": "ConnectivityNature", "op": "eq", "value": "Paired"}, {"field": "EndTime", "op": "absent"},
         {"field": "DeviceLocationAffiliation", "op": "eq", "value": "Synced"}, {"field": "Folder", "op": "contains_any", "value": ["draft"]},
         {"field": "Source", "op": "in", "value": ["Find My", "WhatsApp"]}, {"field": "Action", "op": "eq", "value": "Launch"},
         {"field": "ActiveTime", "op": "gt", "value": 0}, {"field": "Type", "op": "eq", "value": "Searched"},
         {"field": "SomeNewField", "op": "eq", "value": "X"}, {"field": "SomeNewField", "op": "absent"}]
RAW = set(W.NOUNS) | set(W.FIELDS) | {c.get("field") for c in CONDS if c.get("field")} | {"SomeNewField", "NewType"}


def _evidence(part, type_name, field, cond):
    row = {"predicates": [cond] if cond and "field" in cond else [], "context": [cond] if cond and "name" in cond else []}
    if part == "meaning":
        return {"row": dict(row, outputs={"semantics": "event_instant", "meaning": "When the message was sent"}),
                "fields": [{"field": field}]}
    if part == "activity":
        return {"row": dict(row, outputs={"class": "interaction", "actor": "owner"})}
    if part == "attribution":
        return {"row": dict(row, outputs={"flag": "synced_from_account"})}
    return {"choice": {"event_time": field, "end_time": {"field": field}, "role": "sender", "text": [field, "Unlisted"],
                       "thread": {"strategy": "field", "group_field": "Folder"}, "record": "message"}.get(part),
            "fields": [{"field": field}]}


def _raw_names(s):
    """Report identifiers in a sentence: any listed type or field as spelt (case-sensitive), a run-together word,
    an underscore, a dotted rule id or a comparison operator."""
    hits = [n for n in RAW if re.search(r"(?<![\w“])%s(?![\w”])" % re.escape(n), s) and (len(re.findall("[A-Z]", n)) > 1 or n in s.split())]
    hits += re.findall(r"\b\w*[a-z][A-Z]\w*\b", s.replace("WiFi", "wifi"))
    hits += re.findall(r"\w_\w|\w\.\w|\b(?:eq|gt|absent|contains_any)\b|\[", s)
    return hits


def test_no_prompt_names_a_type_or_field_as_the_report_spells_it():
    types = list(W.NOUNS) + ["NewType"]
    fields = list(W.FIELDS) + ["SomeNewField"]
    n = 0
    for part, t, f, cond in itertools.product(PARTS, types, fields[::7] + ["SomeNewField"], CONDS + [None]):
        out = W.plain("C1", part, t, "%s.role.From" % t, _evidence(part, t, f, cond))
        n += 1
        assert not _raw_names(out["sentence"]), (part, t, f, cond, out["sentence"])
        assert out["if_wrong"].startswith("If this is wrong, "), out
        assert "C1" in out["sentence"] and out["sentence"].endswith(".")
    assert n > 10000


def test_the_old_summary_form_is_gone():
    old = "In each instant message, the party marked from is the sender."
    out = W.plain("C1", "role", "InstantMessage", "InstantMessage.role.From", {"choice": "sender"})
    assert out["sentence"] == "In C1’s messages, the person on the from line is the person who sent it."
    assert out["sentence"] != old


def test_event_time_says_what_the_time_means_from_the_meaning_reading():
    out = W.plain("Phone 1", "event_time", "DeviceConnectivity", "DeviceConnectivity.event_time",
                  {"choice": "StartTime"}, {"StartTime": "When the connection started"})
    assert out["sentence"] == ("When Phone 1 connected to another device, the time Loupe puts on the timeline is "
                               "when the connection started.")
    assert "timeline" in out["if_wrong"]


def test_conditions_read_as_what_the_records_did():
    out = W.plain("C2", "activity", "InstantMessage", "x", {"row": {
        "predicates": [{"field": "Platform", "op": "in", "value": ["Mobile", "Unknown"]}],
        "context": [{"name": "direction", "op": "eq", "value": "outgoing"}],
        "outputs": {"class": "interaction", "actor": "owner"}}})
    assert out["sentence"] == ("For C2’s messages that were made on a platform marked “Mobile” or “Unknown” and went "
                               "out, Loupe counts each one as the owner using the phone.")


def test_every_part_has_its_own_consequence():
    assert set(PARTS) <= set(W.IF_WRONG)
    assert len({W.IF_WRONG[p] for p in PARTS}) >= 8
