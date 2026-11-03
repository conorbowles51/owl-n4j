"""Approach 4: knowledge and awareness, group roles part (docs/cellebrite/05 section 7; unit 05-S7).

Built: 7.3 step 5, group roles. Per group chat: who the phone report flags as an admin at extraction, and the
membership changes it records (ChatActivity), with their time where the record carries one and the participant it
names. The gate (7.6) passed for group roles (277 timed ChatActivity records on P14) and failed for read times and
reply latency (owner read times on 20 percent of incoming messages on 2 phones, 5 needed), so steps 1 to 4 are not
built.

Decisions (05 section 19, 19.S7-a to 19.S7-c):

- 19.S7-a A chat is a group when its ChatType is Group, or, where the report gives no ChatType (10 of 14 reports),
  when it lists more than two participants. Reverse if a reviewed mapping gives the chat type per app.
- 19.S7-b The party on a ChatActivity is shown as "participant named", never as who made the change: whether it
  is the actor or the subject is not established (05 section 20).
- 19.S7-c A chat with no admin flag and no recorded change gives no result; the coverage line counts every group.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from services.phone import ids
from services.phone_analysis import fields as FV

CODE = "awareness"
VERSION = "4.1-groups"
PARAMETERS: dict = {}
KINDS = ("group_roles",)
SUPPORTS = ("admin_flag", "membership_change", "change_timed")
UNDERCUTS = ("participant_role_unknown", "time_not_recorded", "admin_at_extraction_only", "synced_attribution",
             "deleted_or_carved")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [
    {"code": "groups", "label": "Group chats"},
    {"code": "admins", "label": "Group admin flags"},
    {"code": "activity", "label": "Recorded membership changes"},
]
TRUE = {"true", "1", "yes"}
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def _chats(conn, ext):
    """Per Chat record: participants (with admin flag), activities (with action, participant and time)."""
    rows = conn.execute(text(
        "SELECT document_index, ordinal, parent_ordinal, model_type, deleted_state FROM phone_records WHERE "
        "extraction_id = :e AND model_type IN ('Chat', 'Party', 'ChatActivity')"), {"e": ext}).fetchall()
    kind = {(r.document_index, r.ordinal): r.model_type for r in rows}
    chats = {}
    for r in rows:
        if r.model_type == "Chat":
            chats[(r.document_index, r.ordinal)] = {"uid": str(ids.record_uid(ext, r.document_index, r.ordinal)),
                                                    "deleted": r.deleted_state, "parties": [], "activities": []}
    parties_of_activity = defaultdict(list)
    for r in rows:
        parent = (r.document_index, r.parent_ordinal)
        uid = str(ids.record_uid(ext, r.document_index, r.ordinal))
        if r.model_type == "Party" and kind.get(parent) == "Chat":
            chats[parent]["parties"].append(uid)
        elif r.model_type == "ChatActivity" and kind.get(parent) == "Chat":
            chats[parent]["activities"].append(uid)
        elif r.model_type == "Party" and kind.get(parent) == "ChatActivity":
            parties_of_activity[str(ids.record_uid(ext, r.document_index, r.parent_ordinal))].append(uid)
    return chats, parties_of_activity


def coverage(conn, case_id) -> dict:
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        groups, admins, acts = _groups(conn, ext)
        phones[ext] = {"label": label, "signals": {
            "groups": {"carries_signal": groups > 0, "records": groups},
            "admins": {"carries_signal": admins > 0, "records": admins},
            "activity": {"carries_signal": acts > 0, "records": acts}}}
    return {"phones": phones, "signals": SIGNALS}


def _groups(conn, ext):
    res = _read(conn, ext)
    return (len(res["groups"]), sum(len(g["admins"]) for g in res["groups"]),
            sum(len(g["activities"]) for g in res["groups"]))


def _read(conn, ext):
    chats, act_parties = _chats(conn, ext)
    chat_uids = [c["uid"] for c in chats.values()]
    party_uids = [p for c in chats.values() for p in c["parties"]] + [p for v in act_parties.values() for p in v]
    act_uids = [a for c in chats.values() for a in c["activities"]]
    vals = FV.field_values(conn, ext, ("Chat", "Party", "ChatActivity"),
                           ("ChatType", "IsGroupAdmin", "Identifier", "Name", "Action"))
    times = FV.times_for(conn, ext, act_uids, ("SystemMessageTimeStamp", "TimeStamp"))
    ident = {}
    if party_uids:
        for r in conn.execute(text(
                "SELECT record_uid::text, identity_key, value_display FROM pv_identity_sighting WHERE extraction_id = :e "
                "AND record_uid = ANY(CAST(:u AS uuid[]))"), {"e": ext, "u": party_uids}):
            ident.setdefault(r[0], (r[1], r[2]))
    titles = {str(r[0]): r[1] for r in conn.execute(text(
        "SELECT record_uid, title_in_record FROM pv_thread WHERE extraction_id = :e AND record_uid = ANY(CAST(:u AS "
        "uuid[]))"), {"e": ext, "u": chat_uids})} if chat_uids else {}

    def who(uid):
        v = vals.get(uid, {}).get("values", {})
        key, display = ident.get(uid, (None, None))
        name = (v.get("Name") or [None])[0]
        return {"record_uid": uid, "identity_key": key,
                "display": name or display or (v.get("Identifier") or [None])[0] or "Not named in the record"}
    groups = []
    for c in chats.values():
        ctype = (vals.get(c["uid"], {}).get("values", {}).get("ChatType") or [None])[0]
        if not (ctype == "Group" or (ctype in (None, "Unknown") and len(c["parties"]) > 2)):
            continue
        admins = [who(p) for p in c["parties"] if any(str(x).lower() in TRUE for x in
                                                         vals.get(p, {}).get("values", {}).get("IsGroupAdmin", ()))]
        acts = []
        for a in c["activities"]:
            t = times.get(a, {})
            when = t.get("SystemMessageTimeStamp") or t.get("TimeStamp")
            acts.append({"record_uid": a, "action": (vals.get(a, {}).get("values", {}).get("Action") or
                                                      ["Unknown"])[0],
                         "instant": when, "participants": [who(p) for p in act_parties.get(a, [])]})
        acts.sort(key=lambda x: (x["instant"] is None, x["instant"] or 0, x["record_uid"]))
        groups.append({"uid": c["uid"], "deleted": c["deleted"], "chat_type": ctype,
                       "participants": len(c["parties"]), "admins": admins, "activities": acts,
                       "title": titles.get(c["uid"])})
    return {"groups": groups}


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    phones = FV.active_phones(conn, case_id)
    out = []
    for i, (ext, label) in enumerate(phones.items()):
        if ctx is not None:
            ctx.progress(i, len(phones), label)
            if ctx.cancelled():
                break
        for g in _read(conn, ext)["groups"]:
            counts["groups"] += 1
            if not g["admins"] and not g["activities"]:
                counts["groups_without_roles"] += 1
                continue
            timed = [a for a in g["activities"] if a["instant"]]
            counts["activities"] += len(g["activities"])
            counts["activities_timed"] += len(timed)
            supports, undercuts = [], []
            if g["admins"]:
                supports.append(_d("admin_flag", "%d participants flagged as admin." % len(g["admins"]),
                                   [a["record_uid"] for a in g["admins"]]))
                undercuts.append(_d("admin_at_extraction_only", "Admin flags are as the phone held them at "
                                    "extraction; earlier admins are not recorded."))
            if g["activities"]:
                supports.append(_d("membership_change", "%d membership changes recorded." % len(g["activities"])))
                undercuts.append(_d("participant_role_unknown", "The participant named on a change may be who made "
                                    "it or who it was made to; the record does not say."))
            if len(timed) < len(g["activities"]):
                undercuts.append(_d("time_not_recorded", "%d changes carry no time." %
                                    (len(g["activities"]) - len(timed))))
            if g["deleted"] in ("Deleted", "Trash"):
                undercuts.append(_d("deleted_or_carved", "The chat record is a deleted one the phone still held."))
            recs = [{"extraction_id": ext, "record_uid": g["uid"], "field_path": "Participants", "role": "group_chat"}]
            recs += [{"extraction_id": ext, "record_uid": a["record_uid"], "field_path": "IsGroupAdmin",
                      "role": "admin"} for a in g["admins"]]
            recs += [{"extraction_id": ext, "record_uid": a["record_uid"], "field_path": None,
                      "role": "membership_change"} for a in g["activities"]]
            out.append({
                "kind": "group_roles", "strength": "timed" if timed else "untimed",
                "measures": {"phone_label": label, "title": g["title"], "chat_type": g["chat_type"],
                             "participants": g["participants"],
                             "admins": [{k: a[k] for k in ("identity_key", "display")} for a in g["admins"]],
                             "changes": [{"action": a["action"], "instant": a["instant"],
                                          "participants": [p["display"] for p in a["participants"]]}
                                         for a in g["activities"]],
                             "timed_changes": len(timed)},
                "directions": {"supports": supports, "undercuts": undercuts},
                "period_start": timed[0]["instant"] if timed else None,
                "period_end": timed[-1]["instant"] if timed else None,
                "records": recs})
    if ctx is not None:
        ctx.progress(len(phones), len(phones))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
