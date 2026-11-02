"""Attribution flags (04 section 4.2, unit U3).

Two sources of flags on every activity event and place observation:

- the reviewed attribution rows (``mappings/data/attribution``), which depend on a record's own fields
  (Location affiliation Synced or Unknown, message Platform Web);
- context flags computed here from the event itself (04 decision 18): deleted, decoding confidence, offset
  absent, latest only, bucketed, counterpart, account level, and a UserMapping other than ``Decoding``.

Group A flags demote an interaction to ``weak``; one group-B flag to ``moderate``; two or more group-B flags to
``weak`` (3.1). The groups are fixed here and in the strength view (migration ``20261102_pol_activity``).
"""
from __future__ import annotations

GROUP_A = ("synced_from_account", "other_device_platform", "user_mapping_other", "wearable", "offset_absent")
GROUP_B = ("affiliation_unknown", "account_level", "deleted_record", "low_decoding_confidence", "latest_only",
           "bucketed")
SHOWN_ONLY = ("deleted_state_unknown", "counterpart", "after_extraction_time")

UI_COPY = {
    "synced_from_account": "Synced from the account. May come from another device.",
    "affiliation_unknown": "Not known whether this device recorded it.",
    "other_device_platform": "Sent from a web or desktop session.",
    "account_level": "Recorded on the account. The device that did it is not shown.",
    "user_mapping_other": "Linked to a different device user or source.",
    "wearable": "Recorded by a paired wearable.",
    "deleted_record": "Recovered deleted record.",
    "deleted_state_unknown": "Not known whether this record was deleted.",
    "low_decoding_confidence": "Decoded with lower confidence.",
    "offset_absent": "Time zone not stated in the source.",
    "latest_only": "Latest occurrence only. Earlier ones are not kept.",
    "bucketed": "Happened somewhere in this period.",
    "counterpart": "Action by the other person.",
    "after_extraction_time": "Stamped after the extraction started (clock or time zone problem).",
}

LATEST_SEMANTICS = ("latest_of_many", "last_modified")


def context_flags(*, semantics, offset_status, deleted_state, decoding_confidence, actor, user_mapping):
    """The flags 4.2 computes from the event's context (no mapping row)."""
    out = []
    if deleted_state == "Deleted":
        out.append("deleted_record")
    elif deleted_state == "Unknown":
        out.append("deleted_state_unknown")
    if decoding_confidence and decoding_confidence != "High":
        out.append("low_decoding_confidence")
    if offset_status != "explicit":
        out.append("offset_absent")
    if semantics in LATEST_SEMANTICS:
        out.append("latest_only")
    if semantics == "aggregate_bucket":
        out.append("bucketed")
    if actor == "counterpart":
        out.append("counterpart")
    if actor == "account":
        out.append("account_level")
    if user_mapping and user_mapping != "Decoding":
        out.append("user_mapping_other")
    return out


def strength(activity_class, actor, flags, semantics, offset_status, deleted_state, physical):
    """The Python twin of ``pol_activity_event_v.strength`` (3.1), used where events are not read through the view
    and checked against it in the tests."""
    a = sum(1 for f in flags if f in GROUP_A)
    b = sum(1 for f in flags if f in GROUP_B)
    if activity_class == "interaction":
        if semantics == "unknown":
            return "none"
        if a > 0 or b >= 2 or semantics in ("aggregate_bucket", "service_observed") or actor in ("other_device",
                                                                                                "unknown"):
            return "weak"
        if b == 1 or semantics in ("latest_of_many", "last_modified", "first_record") or offset_status != "explicit" \
                or (deleted_state or "") != "Intact":
            return "moderate"
        if semantics in ("event_instant", "interval_start", "interval_end", "counterpart_action"):
            return "strong"
        return "moderate"
    if activity_class == "device_state":
        if semantics == "unknown":
            return "none"
        return "moderate" if actor in ("owner", "counterpart") and a + b == 0 else "weak"
    if activity_class == "passive" and physical:
        return "weak"
    return "none"
