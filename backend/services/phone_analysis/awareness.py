"""Approach 4: knowledge and awareness (docs/cellebrite/05 section 7; units 05-S7 and cb-gated-aware).

Built: every step of 7.3.

1. Read and play events, per conversation: incoming messages with the owner's read or play time, outgoing messages
   with a recipient's read, play or delivery time. The time belongs to the Party record it sits on (02's per-app
   mapping); a time read through generic interpretation is graded down and labelled.
2. Reply latency, per one-to-one conversation: for each run of incoming messages, the first outgoing message after
   the last of the run is its reply; latency and read-to-reply, median and inter-quartile range, with n.
3. Read without reply, per one-to-one conversation: incoming messages with an owner read time and no outgoing message
   in the conversation within the window (48 hours, a parameter; when no window is given and the case's reply
   latencies have their 95th percentile beyond 48 hours, the window is that percentile).
4. Unread: incoming messages whose status at extraction is Unread.
5. Group roles: admins at extraction and recorded membership changes (unchanged from 4.1-groups).

Steps 1 to 4 run on every phone, however few read times it holds: each result carries a strength on the app's one
scale (``grading``) with its reasons, and the coverage notes give the true counts behind them. The plan's figure
(owner read times on a fifth of incoming messages on 5 phones, 05 7.6) is shown as a rule of thumb and never hides a
result.

Decisions (05 section 19, 19.S7-a to 19.S7-f):

- 19.S7-a A chat is a group when its ChatType is Group, or, where the report gives no ChatType (10 of 14 reports),
  when it lists more than two participants. Reverse if a reviewed mapping gives the chat type per app.
- 19.S7-b The party on a ChatActivity is shown as "participant named", never as who made the change: whether it
  is the actor or the subject is not established (05 section 20).
- 19.S7-c A chat with no admin flag and no recorded change gives no result; the coverage line counts every group.
- 19.S7-d A conversation is one-to-one when its ChatType is OneOnOne or, with no ChatType, when it is a chat or text
  thread naming at most two parties (the converse of 19.S7-a). Steps 2 and 3 run on those only: a reply in a group
  is not established. Group messages with an owner read time are counted in the coverage notes. Reverse with 19.S7-a.
- 19.S7-e The owner's read time on an incoming message is a date_read or date_played on a Party the projection marks
  as the phone owner (02 5.3). Messages without a time or with no direction are left out of steps 2 and 3 and
  counted. Step 3's window runs from the later of the message's time and the owner's read time.
- 19.S7-f Strength (``grading``): substantiation from the count behind the result (some 3, well 10; 10 is the reply
  pairs per conversation M-4b counts), fit from the interpretation level of the records (reviewed or applied mapping
  2, generic 1). Both counts are rules of thumb. Reverse if a measured error rate gives other counts.
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from services.phone import ids
from services.phone_analysis import fields as FV
from services.phone_analysis import grading as G

CODE = "awareness"
VERSION = "4.2-aware"
VERSION_SOURCES = ("grading",)
PARAMETERS = {"no_reply_hours": {"default": 48, "min": 1, "max": 24 * 365}}
KINDS = ("group_roles", "read_events", "reply_latency", "read_without_reply", "unread")
SUPPORTS = ("admin_flag", "membership_change", "change_timed", "read_times", "reply_pairs", "no_reply", "unread_status",
            "strength_rule")
UNDERCUTS = ("participant_role_unknown", "time_not_recorded", "admin_at_extraction_only", "synced_attribution",
             "deleted_or_carved", "receipts_optional", "notification_preview", "server_device_time",
             "generic_interpretation", "window_past_records", "few_records")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [
    {"code": "groups", "label": "Group chats"},
    {"code": "admins", "label": "Group admin flags"},
    {"code": "activity", "label": "Recorded membership changes"},
    {"code": "read_times", "label": "Owner read or play times on incoming messages"},
]
SOME, WELL = 3, 10
RULE_OF_THUMB_SHARE, RULE_OF_THUMB_PHONES = 0.2, 5
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
    totals = defaultdict(int)
    for ext, label in FV.active_phones(conn, case_id).items():
        groups, admins, acts = _groups(conn, ext)
        t = _message_totals(conn, ext)
        for k, v in t.items():
            totals[k] += v
        totals["phones"] += 1
        totals["phones_with_read_times"] += 1 if t["incoming_owner_timed"] else 0
        totals["phones_meeting_rule_of_thumb"] += 1 if (
            t["incoming"] and t["incoming_owner_timed"] >= RULE_OF_THUMB_SHARE * t["incoming"]) else 0
        phones[ext] = {"label": label, "signals": {
            "groups": {"carries_signal": groups > 0, "records": groups},
            "admins": {"carries_signal": admins > 0, "records": admins},
            "activity": {"carries_signal": acts > 0, "records": acts},
            "read_times": {"carries_signal": t["incoming_owner_timed"] > 0, "records": t["incoming_owner_timed"]}}}
    return {"phones": phones, "signals": SIGNALS, "totals": dict(totals), "notes": notes(dict(totals))}


def _n(v):
    return "{:,}".format(int(v or 0))


def notes(t) -> list:
    """The thin-data lines (cb-gated-aware D): true counts behind steps 1 to 4, and the plan's figure as a rule of
    thumb that hides nothing."""
    if not t.get("phones"):
        return []
    return [
        "Owner read or play times on %s of %s phones; the read results below rest on %s timed incoming messages "
        "(%s played), out of %s incoming. %s outgoing messages carry a recipient's read, play or delivery time. "
        "%s incoming messages are marked unread at extraction." % (
            _n(t.get("phones_with_read_times")), _n(t.get("phones")), _n(t.get("incoming_owner_timed")),
            _n(t.get("incoming_owner_played")), _n(t.get("incoming")), _n(t.get("outgoing_recipient_timed")),
            _n(t.get("incoming_unread"))),
        "Reply times rest on the order of messages, not on read times: %s incoming and %s outgoing messages with a "
        "time in one-to-one conversations. %s messages have no time or no direction and are left out." % (
            _n(t.get("one_to_one_incoming")), _n(t.get("one_to_one_outgoing")), _n(t.get("untimed_or_undirected"))),
        "Rule of thumb (no measurement behind it): the plan asked for owner read times on a fifth of incoming "
        "messages on 5 phones before comparing read times; %s of %s phones here meet it. Every result is listed "
        "whatever the count, with its strength: strong, moderate, weak or faint, set by a stated rule, never by a "
        "model." % (_n(t.get("phones_meeting_rule_of_thumb")), _n(t.get("phones"))),
    ]


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


# ---- steps 1 to 4: read times, replies, unread ----------------------------------------------------------------------

OWNERISH = ("owner_implicit",)


def _messages(conn, ext):
    """``(threads, events)``: ``threads`` {thread_key: {record_uid, kind, chat_type, title, keys}}; ``events`` the
    phone's messages in time order, each with its parties' read, play and delivery times."""
    threads = {r.thread_key: {"record_uid": str(r.record_uid) if r.record_uid else None, "kind": r.thread_kind,
                              "chat_type": r.chat_type, "title": r.title_in_record,
                              "keys": [k for k in (r.party_identity_keys or []) if k]}
               for r in conn.execute(text(
                   "SELECT thread_key, record_uid, thread_kind, chat_type, title_in_record, party_identity_keys FROM "
                   "pv_thread WHERE extraction_id = :e"), {"e": ext})}
    events = {}
    for r in conn.execute(text(
            "SELECT event_uid::text AS eu, record_uid::text AS ru, thread_key, direction, sort_instant, status, "
            "interpretation_level FROM pv_comm_event WHERE extraction_id = :e AND kind = 'message' "
            "ORDER BY sort_instant NULLS LAST, record_uid"), {"e": ext}):
        events[r.eu] = {"record_uid": r.ru, "thread": r.thread_key, "direction": r.direction, "t": r.sort_instant,
                        "status": r.status, "level": r.interpretation_level, "owner_read": None,
                        "owner_played": None, "owner_level": None, "recipient_read": None, "recipient_played": None,
                        "recipient_delivered": None, "recipient_level": None, "other": None}
    for r in conn.execute(text(
            "SELECT p.event_uid::text AS eu, p.identity_key, p.role, p.is_phone_owner, p.date_read, p.date_played, "
            "p.date_delivered, p.name_in_record, p.identifier_raw, p.interpretation_level FROM pv_comm_party p JOIN "
            "pv_comm_event c ON c.event_uid = p.event_uid AND c.extraction_id = p.extraction_id WHERE "
            "p.extraction_id = :e AND c.kind = 'message' ORDER BY p.event_uid, p.participation_uid"), {"e": ext}):
        ev = events.get(r.eu)
        if ev is None:
            continue
        owner = bool(r.is_phone_owner) or r.role in OWNERISH
        if owner:
            if r.date_read and ev["owner_read"] is None:
                ev["owner_read"], ev["owner_level"] = r.date_read, r.interpretation_level
            if r.date_played and ev["owner_played"] is None:
                ev["owner_played"], ev["owner_level"] = r.date_played, r.interpretation_level
        else:
            if ev["other"] is None and (r.identity_key or r.name_in_record or r.identifier_raw):
                ev["other"] = {"identity_key": r.identity_key, "name": r.name_in_record, "raw": r.identifier_raw}
            for k, v in (("recipient_read", r.date_read), ("recipient_played", r.date_played),
                         ("recipient_delivered", r.date_delivered)):
                if v and ev[k] is None:
                    ev[k], ev["recipient_level"] = v, r.interpretation_level
    return threads, list(events.values())


def one_to_one(th) -> bool:
    """19.S7-d."""
    if th is None or th["kind"] not in ("chat", "sms_group"):
        return False
    if th["chat_type"] == "OneOnOne":
        return True
    return th["chat_type"] in (None, "", "Unknown") and len(th["keys"]) <= 2


def _owner_time(ev):
    return ev["owner_read"] or ev["owner_played"]


def _message_totals(conn, ext) -> dict:
    threads, events = _messages(conn, ext)
    t = defaultdict(int)
    for ev in events:
        d = ev["direction"]
        if d == "incoming":
            t["incoming"] += 1
            t["incoming_owner_timed"] += 1 if _owner_time(ev) else 0
            t["incoming_owner_played"] += 1 if ev["owner_played"] else 0
            t["incoming_unread"] += 1 if ev["status"] == "Unread" else 0
        elif d == "outgoing":
            t["outgoing"] += 1
            t["outgoing_recipient_timed"] += 1 if (ev["recipient_read"] or ev["recipient_played"] or
                                                   ev["recipient_delivered"]) else 0
        if ev["t"] is None or d not in ("incoming", "outgoing"):
            t["untimed_or_undirected"] += 1
        elif one_to_one(threads.get(ev["thread"])):
            t["one_to_one_" + d] += 1
        elif d == "incoming" and _owner_time(ev):
            t["group_incoming_owner_timed"] += 1
    for k in ("incoming", "incoming_owner_timed", "incoming_owner_played", "incoming_unread", "outgoing",
              "outgoing_recipient_timed", "untimed_or_undirected", "one_to_one_incoming", "one_to_one_outgoing",
              "group_incoming_owner_timed"):
        t.setdefault(k, 0)
    return dict(t)


def reply_pairs(seq) -> list:
    """7.3 step 2 over one one-to-one conversation's timed, directed messages in time order: ``[(incoming, reply)]``,
    one per run of incoming messages, from the last of the run."""
    out, last_in = [], None
    for ev in seq:
        if ev["direction"] == "incoming":
            last_in = ev
        elif ev["direction"] == "outgoing" and last_in is not None:
            out.append((last_in, ev))
            last_in = None
    return out


def without_reply(seq, window: timedelta) -> list:
    """7.3 step 3: incoming messages with an owner read time and no outgoing message in the conversation within
    ``window`` after them."""
    outs = [ev["t"] for ev in seq if ev["direction"] == "outgoing"]
    found = []
    for ev in seq:
        if ev["direction"] != "incoming" or not _owner_time(ev):
            continue
        # the window runs from the later of arrival and the owner's read time (19.S7-e): a message read late and
        # answered soon after is answered
        start = max(ev["t"], _owner_time(ev))
        j = bisect.bisect_right(outs, ev["t"])
        if j >= len(outs) or outs[j] > start + window:
            found.append(ev)
    return found


def _quartiles(xs):
    xs = sorted(xs)
    if not xs:
        return None

    def q(p):
        k = (len(xs) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
        return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)
    return {"n": len(xs), "median_s": round(q(0.5), 1), "q1_s": round(q(0.25), 1), "q3_s": round(q(0.75), 1)}


def _p95(xs):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * 0.95
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _duration(s):
    s = float(s)
    if s < 120:
        return "%d seconds" % round(s)
    if s < 7200:
        return "%d minutes" % round(s / 60)
    if s < 172800:
        return "%.1f hours" % (s / 3600)
    return "%.1f days" % (s / 86400)


FIT_WORDS = {2: "Times read through a reviewed or applied mapping of the app",
             1: "Some times read through generic interpretation, not a mapping of the app",
             0: "No interpretation of the app behind the times"}


def _correspondent(conn_cache, seq, th):
    for ev in seq:
        if ev["other"]:
            o = ev["other"]
            return {"identity_key": o["identity_key"],
                    "display": o["name"] or conn_cache.get(o["identity_key"]) or o["raw"] or o["identity_key"]}
    return {"identity_key": None, "display": (th or {}).get("title") or "Not named in the record"}


def _graded(kind, n, noun, levels, supports, undercuts, measures, recs, start, end):
    fit = G.fit_of_levels(levels)
    subst = G.substantiation(n, SOME, WELL)
    lv = G.level(subst, fit)
    supports = supports + [_d("strength_rule", G.reasons(n, noun, SOME, WELL, fit, FIT_WORDS))]
    if fit < 2:
        undercuts = undercuts + [_d("generic_interpretation", "Some of these records were read without a mapping of "
                                    "the app, so which party a time belongs to is less certain.")]
    if subst == 0:
        undercuts = undercuts + [_d("few_records", "Only %d %s behind it." % (n, noun[0] if n == 1 else noun[1]))]
    return {"kind": kind, "strength": lv, "measures": dict(measures, strength_basis={"count": n, "substantiation":
                                                                                         subst, "fit": fit}),
            "directions": {"supports": supports, "undercuts": undercuts}, "period_start": start, "period_end": end,
            "records": recs}


READ_UNDERCUTS = (("receipts_optional", "Read receipts depend on the app's settings: no read time does not mean the "
                   "message was not read."),
                  ("synced_attribution", "Reading on a linked device sets the read state on the phone."),
                  ("notification_preview", "A notification preview lets a message be seen without being marked "
                   "read."),
                  ("server_device_time", "Read times may be the service's time, not the phone's."))


def _rec(ext, uid, role, kind):
    return {"extraction_id": ext, "record_uid": uid, "field_path": "awareness:" + kind, "role": role}


def message_results(conn, ext, label, window_s, counts, names) -> list:
    """Steps 1 to 4 for one phone. ``window_s`` is step 3's window in seconds."""
    threads, events = _messages(conn, ext)
    by_thread = defaultdict(list)
    for ev in events:
        by_thread[ev["thread"]].append(ev)
    out = []
    for tkey in sorted(by_thread, key=lambda k: (k is None, str(k))):
        evs = by_thread[tkey]
        th = threads.get(tkey)
        who = _correspondent(names, evs, th)
        base = {"phone_label": label, "title": (th or {}).get("title"), "correspondent": who,
                "one_to_one": one_to_one(th)}
        anchor = [{"extraction_id": ext, "record_uid": th["record_uid"], "field_path": None, "role": "conversation"}] \
            if th and th["record_uid"] else []
        # step 1
        inc_t = [e for e in evs if e["direction"] == "incoming" and _owner_time(e)]
        out_t = [e for e in evs if e["direction"] == "outgoing" and (e["recipient_read"] or e["recipient_played"] or
                                                                    e["recipient_delivered"])]
        if inc_t or out_t:
            times = [_owner_time(e) for e in inc_t] + [e["recipient_read"] or e["recipient_played"] or
                                                       e["recipient_delivered"] for e in out_t]
            n = len(inc_t) + len(out_t)
            counts["read_events_messages"] += n
            m = dict(base, incoming=sum(1 for e in evs if e["direction"] == "incoming"), incoming_owner_read=sum(
                1 for e in inc_t if e["owner_read"]), incoming_owner_played=sum(1 for e in inc_t if e["owner_played"]),
                outgoing=sum(1 for e in evs if e["direction"] == "outgoing"),
                outgoing_recipient_read=sum(1 for e in out_t if e["recipient_read"]),
                outgoing_recipient_played=sum(1 for e in out_t if e["recipient_played"]),
                outgoing_recipient_delivered=sum(1 for e in out_t if e["recipient_delivered"]))
            out.append(_graded(
                "read_events", n, ("message with a read, play or delivery time", "messages with a read, play or "
                                   "delivery time"),
                [e["owner_level"] for e in inc_t] + [e["recipient_level"] for e in out_t],
                [_d("read_times", "%d incoming read or played by the owner, %d outgoing read, played or delivered to "
                    "the other side." % (len(inc_t), len(out_t)))],
                [_d(c, w) for c, w in READ_UNDERCUTS], m,
                anchor + [_rec(ext, e["record_uid"], "read_incoming", "read") for e in inc_t] +
                [_rec(ext, e["record_uid"], "read_outgoing", "read") for e in out_t], min(times), max(times)))
        # step 4
        unread = [e for e in evs if e["direction"] == "incoming" and e["status"] == "Unread"]
        if unread:
            counts["unread_messages"] += len(unread)
            ts = [e["t"] for e in unread if e["t"]]
            out.append(_graded(
                "unread", len(unread), ("incoming message marked unread", "incoming messages marked unread"),
                [e["level"] for e in unread],
                [_d("unread_status", "%d incoming messages carry the status Unread at extraction." % len(unread))],
                [_d("synced_attribution", "Reading on a linked device or a notification preview can leave a message "
                    "marked unread on the phone.")], dict(base, unread=len(unread)),
                anchor + [_rec(ext, e["record_uid"], "unread", "unread") for e in unread],
                min(ts) if ts else None, max(ts) if ts else None))
        if not one_to_one(th):
            continue
        seq = [e for e in evs if e["t"] is not None and e["direction"] in ("incoming", "outgoing")]
        # step 2
        pairs = reply_pairs(seq)
        if pairs:
            lat = [(o["t"] - i["t"]).total_seconds() for i, o in pairs]
            r2r = [(o["t"] - _owner_time(i)).total_seconds() for i, o in pairs if _owner_time(i)]
            counts["reply_pairs"] += len(pairs)
            counts.setdefault("_latencies", []).extend(lat)
            q, rq = _quartiles(lat), _quartiles(r2r)
            line = "%d replies; median %s (middle half %s to %s)." % (
                q["n"], _duration(q["median_s"]), _duration(q["q1_s"]), _duration(q["q3_s"]))
            if rq:
                line += " From the owner's read time: median %s over %d." % (_duration(rq["median_s"]), rq["n"])
            out.append(_graded(
                "reply_latency", len(pairs), ("reply", "replies"), [e["level"] for p in pairs for e in p],
                [_d("reply_pairs", line)],
                [_d("server_device_time", "Message times may be the service's or the phone's; the gap between them "
                    "is not corrected here.")],
                dict(base, latency=q, read_to_reply=rq),
                anchor + [_rec(ext, i["record_uid"], "incoming", "reply") for i, _ in pairs] +
                [_rec(ext, o["record_uid"], "reply", "reply") for _, o in pairs],
                pairs[0][0]["t"], pairs[-1][1]["t"]))
        by_thread[tkey] = seq
    return out, threads, by_thread


def no_reply_results(ext, label, threads, by_thread, window_s, basis, last_instant, counts, names) -> list:
    out = []
    window = timedelta(seconds=window_s)
    for tkey in sorted(by_thread, key=lambda k: (k is None, str(k))):
        th = threads.get(tkey)
        if not one_to_one(th):
            continue
        seq = by_thread[tkey]
        found = without_reply(seq, window)
        if not found:
            continue
        read = sum(1 for e in seq if e["direction"] == "incoming" and _owner_time(e))
        late = sum(1 for e in found if last_instant and e["t"] + window > last_instant)
        counts["read_without_reply"] += len(found)
        undercuts = [_d(c, w) for c, w in READ_UNDERCUTS[:1]] + [
            _d("synced_attribution", "A reply may have been sent from another device or another app.")]
        if late:
            undercuts.append(_d("window_past_records", "%d of them came less than the window before the phone's last "
                                "message, so a later reply would not be on this phone." % late))
        anchor = [{"extraction_id": ext, "record_uid": th["record_uid"], "field_path": None, "role": "conversation"}] \
            if th["record_uid"] else []
        out.append(_graded(
            "read_without_reply", len(found), ("message read without reply", "messages read without reply"),
            [e["owner_level"] for e in found],
            [_d("no_reply", "%d of %d messages the owner read had no message back within %s." % (
                len(found), read, _duration(window_s)))],
            undercuts,
            {"phone_label": label, "title": th.get("title"), "correspondent": _correspondent(names, seq, th),
             "one_to_one": True, "read_incoming": read, "without_reply": len(found),
             "share": round(len(found) / read, 4) if read else None, "window_hours": round(window_s / 3600, 2),
             "window_basis": basis, "near_end_of_records": late},
            anchor + [_rec(ext, e["record_uid"], "read_no_reply", "no_reply") for e in found],
            found[0]["t"], found[-1]["t"]))
    return out


def _names(conn, case_id):
    return {r[0]: r[1] for r in conn.execute(text(
        "SELECT identity_key, value_display FROM phone_identities WHERE case_id = :c"), {"c": str(case_id)})}


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    phones = FV.active_phones(conn, case_id)
    names = _names(conn, case_id)
    per_phone = []
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
        msg, threads, by_thread = message_results(conn, ext, label, None, counts, names)
        out.extend(msg)
        last = max((e["t"] for seq in by_thread.values() for e in seq if e["t"] is not None), default=None)
        per_phone.append((ext, label, threads, by_thread, last))
    # step 3's window: the parameter; at its default, the case's 95th percentile of reply latency when beyond it
    window_h = params.get("no_reply_hours", PARAMETERS["no_reply_hours"]["default"])
    window_s, basis = window_h * 3600.0, "parameter"
    p95 = _p95(counts.pop("_latencies", []))
    if window_h == PARAMETERS["no_reply_hours"]["default"] and p95 is not None and p95 > window_s:
        window_s, basis = p95, "case_95th_percentile"
    counts["no_reply_window_hours"] = round(window_s / 3600, 2)
    for ext, label, threads, by_thread, last in per_phone:
        out.extend(no_reply_results(ext, label, threads, by_thread, window_s, basis, last, counts, names))
    for r in out:
        if r["kind"] != "group_roles":
            counts["%s_%s" % (r["kind"], r["strength"])] += 1
    if ctx is not None:
        ctx.progress(len(phones), len(phones))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
