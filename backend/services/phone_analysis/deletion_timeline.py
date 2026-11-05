"""Approach 3: deletion and concealment timeline (docs/cellebrite/05 section 6; unit 05-S6).

What the records show was deleted or made unreadable, when it can be placed in time, which conversations lost a
larger share of their messages than the phone's norm for that app, which deletions a setting or reason accounts for,
and the concealment context (apps in concealment-capable categories, app removals, wipes, power-offs, unreadable
messages). Key dates are read by the screen at display time, so adding one never needs a rerun.

Rules kept from 6.3:

- A deletion is an interval ``[earliest, latest]``: earliest is the record's own latest time, latest is
  ``DateDeleted`` where present, else the extraction start. Replies, the counterpart's copy and wipes never narrow it;
  a wipe is shown beside, never used as a bound (test 6.8.6).
- Explained deletions (``SelfDestructDuration`` non-zero or ``Label`` SelfDestruct; ``DeletionReason`` UserViewed or
  UserDeleted; ``Label`` Recalled) are excluded from the clearing score and reported beside it.
- A result states what the records show, never a person's state of mind (05 3.5).

Decisions taken here (05 section 19, rows 19.S6-a to 19.S6-c):

- 19.S6-a, hole threshold: a gap is compared with the 99th percentile of the conversation's *other* gaps (leave one
  out). With fewer than 100 gaps the plain 99th percentile is the largest gap itself, so no gap could ever exceed it.
  Reverse if a corpus run shows leave-one-out marking more than 5 percent of conversations with 20 or more messages.
- 19.S6-b, "inside the availability band for app A": 04's observed bands are built only from observing streams
  (device events, connectivity, places), never from messages, so no band exists per app. A gap is a hole only when the
  phone holds messages of the same app in other conversations inside the gap (the app was recording); a gap during
  which the app recorded nothing at all on the phone is that app's no-data period, not a hole. Reverse if 04 gains a
  per-app band.
- 19.S6-c, ``hole_confirmed_by_counterpart`` (6.3 step 4) rests on approach 2's matching (``message_reconciliation``,
  run here with its default parameters over the same phones): a conversation on phone P is linked to a conversation
  on phone Q when at least one message of each is a strong match (``matched_strong``, as the approach 2 gate counts,
  19.S5-j) of the other. A hole in P's conversation is confirmed when Q holds, in a linked conversation, a message
  inside the gap whose copy on P is missing or deleted. The counterpart messages are cited in the support's locators
  (up to 20, the full count in ``measures``); the result rests on the same two bounding records as an unconfirmed
  hole, so a person's decision on it carries over. Reverse if a reviewed sample shows strong links joining
  conversations that are not the same.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from services.phone import ids
from services.phone_analysis import conversation_gaps as G
from services.phone_analysis import fields as FV
from services.phone_analysis.conversation_gaps import holes_in  # noqa: F401 - the rule's public name here

CODE = "deletion_timeline"
VERSION = "3.3"  # 3.3: holes confirmed by the counterpart phone (19.S6-c)
VERSION_SOURCES = ("conversation_gaps",)
PARAMETERS = {
    "clearing_min_messages": {"default": 20, "min": 5, "max": 1000},
    "clearing_q": {"default": 0.05, "min": 0.001, "max": 0.2},
    "hole_min_days": {"default": G.HOLE_MIN_DAYS, "min": 1, "max": 365},
}
KINDS = ("deleted_record", "referenced_message_absent", "selective_clearing", "hole", "hole_confirmed_by_counterpart",
         "concealment_app",
         "app_removed", "wipe", "power_off", "scrambled_messages")
SUPPORTS = ("deleted_state_recorded", "date_deleted_recorded", "deletion_reason_recorded", "reference_on_phone",
            "binomial_significant", "bounded_by_intact", "app_recording_in_gap", "category_recorded",
            "event_recorded", "counterpart_copy_in_gap")
UNDERCUTS = ("bounded_by_extraction_only", "auto_delete_setting", "view_once", "carving_partial",
             "decoder_differs_by_app", "selective_extraction", "no_data_period", "deleted_or_carved",
             "reference_id_local", "wipe_scope_unknown", "explained_excluded", "time_not_recorded",
             "synced_attribution")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
DELETED = G.DELETED
CONCEALMENT_CATEGORIES = ("HideFilesPictures", "FakeGPS", "CleanMobile")
EXPLANATIONS = ("explained_by_setting", "explained_by_view_once", "user_deleted", "recalled_by_sender", "unexplained")
SIGNALS = [
    {"code": "deleted", "label": "Deleted records"},
    {"code": "reasons", "label": "Deletion reasons or disappearing-message settings"},
    {"code": "references", "label": "Replies and quotes"},
    {"code": "apps", "label": "Installed app categories"},
    {"code": "device_events", "label": "Device and power events"},
]
_TIMESPAN = re.compile(r"^-?(?:(\d+)\.)?(\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?$")
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def timespan_seconds(v) -> float | None:
    """A TimeSpan value as seconds: ``d.hh:mm:ss`` or ``hh:mm:ss`` (and an ISO 8601 duration ``P7D``/``PT30S``)."""
    if v is None:
        return None
    s = str(v).strip()
    m = _TIMESPAN.match(s)
    if m:
        days = int(m.group(1) or 0)
        sec = days * 86400 + int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4))
        return float(-sec if s.startswith("-") else sec)
    m = re.match(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$", s)
    if m and any(m.groups()):
        d, h, mi, se = (float(x or 0) for x in m.groups())
        return d * 86400 + h * 3600 + mi * 60 + se
    try:
        return float(s)
    except ValueError:
        return None


def explanation(values: dict) -> str:
    """6.3 step 2, in that order of precedence."""
    labels = {str(x) for x in values.get("Label", ())}
    reasons = {str(x) for x in values.get("DeletionReason", ())}
    durations = [timespan_seconds(x) for x in values.get("SelfDestructDuration", ())]
    if any(d for d in durations if d) or "SelfDestruct" in labels:
        return "explained_by_setting"
    if "UserViewed" in reasons:
        return "explained_by_view_once"
    if "UserDeleted" in reasons:
        return "user_deleted"
    if "Recalled" in labels:
        return "recalled_by_sender"
    return "unexplained"


def binomial_upper_tail(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), in log space."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    lp, lq = math.log(p), math.log1p(-p)
    lg = math.lgamma
    terms = [lg(n + 1) - lg(i + 1) - lg(n - i + 1) + i * lp + (n - i) * lq for i in range(k, n + 1)]
    top = max(terms)
    return min(1.0, math.exp(top) * sum(math.exp(t - top) for t in terms))


def benjamini_hochberg(pvalues: list) -> list:
    """Adjusted q-values in the input order."""
    m = len(pvalues)
    if not m:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        q[i] = running
    return q


# ---- reading -----------------------------------------------------------------------------------------------------

def _extraction_start(conn, ext):
    from services.pattern_of_life.availability import extraction_start
    return extraction_start(conn, ext)


def _messages(conn, ext) -> list:
    return G.phone_messages(conn, ext)


def _deleted_records(conn, ext) -> list:
    return conn.execute(text(
        "SELECT r.record_uid::text AS uid, r.model_type, r.deleted_state, r.is_carved, r.first_instant, "
        "(SELECT max(t.instant) FROM pv_time t WHERE t.record_uid = r.record_uid AND t.field_path <> 'DateDeleted') "
        "AS latest_own, (SELECT min(t.instant) FROM pv_time t WHERE t.record_uid = r.record_uid AND t.field_path = "
        "'DateDeleted') AS date_deleted FROM pv_record r WHERE r.extraction_id = :e AND r.deleted_state = ANY(:d) "
        "AND r.model_type NOT IN ('Party', 'ReplyMessageData', 'QuotedMessageData', 'ScrambledMessageData') "
        "ORDER BY r.ordinal"), {"e": ext, "d": list(DELETED)}).mappings().all()


def coverage(conn, case_id) -> dict:
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        deleted = int(conn.execute(text("SELECT count(*) FROM pv_record WHERE extraction_id = :e AND deleted_state = "
                                        "ANY(:d)"), {"e": ext, "d": list(DELETED)}).scalar() or 0)
        reasons = len(FV.field_values(conn, ext, ("InstantMessage",), ("DeletionReason", "SelfDestructDuration")))
        tc = FV.type_counts(conn, ext, ("ReplyMessageData", "QuotedMessageData", "InstalledApplication",
                                         "DeviceEvent", "PoweringEvent"))
        refs = tc.get("ReplyMessageData", 0) + tc.get("QuotedMessageData", 0)
        dev = tc.get("DeviceEvent", 0) + tc.get("PoweringEvent", 0)
        phones[ext] = {"label": label, "signals": {
            "deleted": {"carries_signal": deleted > 0, "records": deleted},
            "reasons": {"carries_signal": reasons > 0, "records": reasons},
            "references": {"carries_signal": refs > 0, "records": refs},
            "apps": {"carries_signal": tc.get("InstalledApplication", 0) > 0,
                     "records": tc.get("InstalledApplication", 0),
                     "reason_absent": None if tc.get("InstalledApplication") else "type_absent"},
            "device_events": {"carries_signal": dev > 0, "records": dev}}}
    return {"phones": phones, "signals": SIGNALS}


# ---- the analysis ------------------------------------------------------------------------------------------------

def _rec(ext, uid, role, field_path=None):
    return {"extraction_id": ext, "record_uid": uid, "field_path": field_path, "role": role}


def analyse_phone(conn, ext, label, params, counts, counterpart=None) -> list:
    out = []
    start = _extraction_start(conn, ext)
    msgs = _messages(conn, ext)
    by_uid = {m["uid"]: m for m in msgs}
    expl_vals = FV.field_values(conn, ext, ("InstantMessage",), ("DeletionReason", "SelfDestructDuration", "Label"))
    explained = {uid: explanation(v["values"]) for uid, v in expl_vals.items()}

    # 1-2. deletion events with their interval and explanation
    for r in _deleted_records(conn, ext):
        uid = r["uid"]
        m = by_uid.get(uid)
        earliest = r["latest_own"] or (m["sort_instant"] if m else None) or r["first_instant"]
        latest, basis = (r["date_deleted"], "date_deleted") if r["date_deleted"] else (start, "extraction_start")
        if latest is None:
            basis = "unknown"
        ex = explained.get(uid, "unexplained") if r["model_type"] == "InstantMessage" else None
        supports = [_d("deleted_state_recorded", "The phone report marks this record %s." % r["deleted_state"], [uid])]
        undercuts = [_d("carving_partial", "Recovery finds only some deleted records, so this is a lower bound.")]
        if basis == "date_deleted":
            supports.append(_d("date_deleted_recorded", "The record carries a deletion time.", [uid]))
        elif basis == "extraction_start":
            undercuts.append(_d("bounded_by_extraction_only", "Deleted at some time between its own time and the "
                                "extraction; nothing on the phone narrows it."))
        if earliest is None:
            undercuts.append(_d("time_not_recorded", "The record carries no time of its own, so the start of the "
                                "interval is not known."))
        if ex == "explained_by_setting":
            undercuts.append(_d("auto_delete_setting", "A disappearing-message setting accounts for this deletion."))
        elif ex == "explained_by_view_once":
            undercuts.append(_d("view_once", "The record says it was removed after being viewed once."))
        elif ex in ("user_deleted", "recalled_by_sender"):
            supports.append(_d("deletion_reason_recorded", "The record states a deletion reason.", [uid]))
        if r["is_carved"]:
            undercuts.append(_d("deleted_or_carved", "Recovered by carving."))
        counts["deleted_records"] += 1
        counts["by_explanation"][ex or "not_a_message"] += 1
        out.append({
            "kind": "deleted_record", "strength": "recorded_time" if basis == "date_deleted" else "interval",
            "measures": {"phone_label": label, "model_type": r["model_type"], "deleted_state": r["deleted_state"],
                         "earliest": earliest, "latest": latest, "latest_basis": basis, "explanation": ex,
                         "thread_key": m["thread_key"] if m else None, "app": m["app"] if m else None},
            "directions": {"supports": supports, "undercuts": undercuts},
            "period_start": earliest or latest, "period_end": latest or earliest,
            "records": [_rec(ext, uid, "deleted_record")]})

    # 3. replies and quotes whose referenced message is not on the phone
    ident = defaultdict(set)
    for r in conn.execute(text(
            "SELECT record_uid::text, value FROM pv_text WHERE extraction_id = :e AND model_type = 'InstantMessage' "
            "AND field_path ~ '(^|\\.)Identifier$' AND value IS NOT NULL"), {"e": ext}):
        ident[r[1]].add(r[0])
    refs = FV.field_values(conn, ext, ("ReplyMessageData", "QuotedMessageData"), ("OriginalMessageID",))
    counts["references"] += len(refs)
    for ref_uid, v in sorted(refs.items()):
        ids_ = [x for x in v["values"].get("OriginalMessageID", []) if x]
        if not ids_:
            counts["references_without_id"] += 1
            continue
        if any(i in ident for i in ids_):
            continue
        parent = v["parent_uid"]
        pm = by_uid.get(parent)
        counts["referenced_absent"] += 1
        out.append({
            "kind": "referenced_message_absent", "strength": "reference_on_phone",
            "measures": {"phone_label": label, "reference_type": v["model_type"], "thread_key": pm["thread_key"]
                         if pm else None, "app": pm["app"] if pm else None,
                         "reply_instant": pm["sort_instant"] if pm else None},
            "directions": {"supports": [_d("reference_on_phone", "A message on this phone refers to an earlier "
                                           "message that the extraction does not hold.", [parent or ref_uid])],
                           "undercuts": [_d("reference_id_local", "The reference is the app's own message number; "
                                            "the earlier message may be outside what was extracted rather than "
                                            "deleted.")]},
            "period_start": pm["sort_instant"] if pm else None, "period_end": pm["sort_instant"] if pm else None,
            "records": [_rec(ext, parent, "reply") if parent else _rec(ext, ref_uid, "reply"),
                        _rec(ext, ref_uid, "reference", "OriginalMessageID")]})

    # 4. selective clearing and holes, per conversation, against the phone's baseline for the app
    convs = G.conversations(msgs)
    per_app = defaultdict(lambda: [0, 0])  # app -> [unexplained deleted, considered]
    stats = {}
    for key, ms in convs.items():
        deleted_unexpl = sum(1 for m in ms if m["deleted_state"] in DELETED and explained.get(m["uid"], "unexplained")
                             == "unexplained")
        explained_n = sum(1 for m in ms if m["deleted_state"] in DELETED and explained.get(m["uid"], "unexplained")
                          != "unexplained")
        n = len(ms) - explained_n
        stats[key] = (deleted_unexpl, n, explained_n)
        per_app[key[0]][0] += deleted_unexpl
        per_app[key[0]][1] += n
    tested = []
    for key, (k, n, explained_n) in stats.items():
        if n < params["clearing_min_messages"] or k == 0:
            continue
        app_k, app_n = per_app[key[0]]
        base_n = app_n - n
        if base_n <= 0:
            continue
        # 19.S6-f: with no unexplained deletion elsewhere in the app the baseline is its 95 percent upper bound
        # (rule of three), never 0, so a single deletion is not "significant" on a zero baseline
        d0 = (app_k - k) / base_n if app_k > k else min(1.0, 3 / base_n)
        tested.append((key, k, n, explained_n, d0, binomial_upper_tail(k, n, d0)))
    qs = benjamini_hochberg([t[5] for t in tested])
    thread_rec = {r[0]: str(r[1]) for r in conn.execute(text(
        "SELECT thread_key, record_uid FROM pv_thread WHERE extraction_id = :e AND record_uid IS NOT NULL"), {"e": ext})}
    counts["conversations_tested"] += len(tested)
    for (key, k, n, explained_n, d0, p), q in zip(tested, qs):
        if q > params["clearing_q"]:
            continue
        ms = convs[key]
        deleted_uids = sorted(m["uid"] for m in ms if m["deleted_state"] in DELETED and
                              explained.get(m["uid"], "unexplained") == "unexplained")
        times = [m["sort_instant"] for m in ms if m["sort_instant"]]
        counts["selective_clearing"] += 1
        out.append({
            "kind": "selective_clearing", "strength": "significant",
            "measures": {"phone_label": label, "app": key[0], "thread_key": key[1], "messages": n,
                         "deleted": k, "share": round(k / n, 4), "baseline_share": round(d0, 6), "p": p, "q": q,
                         "explained_excluded": explained_n},
            "directions": {"supports": [_d("binomial_significant", "%d of %d messages in this conversation are "
                                           "deleted, against %.1f percent across this app's other conversations on "
                                           "the phone." % (k, n, 100 * d0))],
                           "undercuts": [_d("decoder_differs_by_app", "What is recovered differs by app, so the "
                                            "comparison is within the app only."),
                                         _d("carving_partial", "Recovery finds only some deleted records.")] +
                                        ([_d("explained_excluded", "%d deletions a setting or reason accounts for are "
                                             "left out." % explained_n)] if explained_n else [])},
            "period_start": min(times) if times else None, "period_end": max(times) if times else None,
            "records": [_rec(ext, u, "deleted_message") for u in deleted_uids] +
                       ([_rec(ext, thread_rec[key[1]], "conversation", "Messages")] if thread_rec.get(key[1]) else
                        [_rec(ext, deleted_uids[0], "conversation", "thread:" + key[1])])})

    # holes: gaps between intact messages, inside the app's own recording on the phone (19.S6-b)
    holes, without_data = G.conversation_holes(msgs, timedelta(days=params["hole_min_days"]), convs)
    counts["gaps_without_app_data"] += without_data
    for hole in holes:
        key, a, b, elsewhere = hole["key"], hole["start"], hole["end"], hole["elsewhere"]
        copies = [c for c in (counterpart or {}).get((ext, key[1]), ()) if a < c["t"] < b]
        measures = {"phone_label": label, "app": key[0], "thread_key": key[1], "gap_start": a, "gap_end": b,
                    "gap_days": round((b - a).total_seconds() / 86400, 2),
                    "app_messages_elsewhere_in_gap": elsewhere}
        supports = [_d("bounded_by_intact", "Intact messages sit on both sides of the gap.",
                       [hole["before"], hole["after"]]),
                    _d("app_recording_in_gap", "The same app holds %d messages in other conversations on this "
                       "phone during the gap." % elsewhere)]
        if copies:
            counts["holes_confirmed_by_counterpart"] += 1
            names = sorted({c["phone_label"] for c in copies})
            absent = sum(1 for c in copies if not c["deleted_here"])
            measures.update(counterpart_messages_in_gap=len(copies), counterpart_phones=names,
                            counterpart_absent_here=absent, counterpart_deleted_here=len(copies) - absent,
                            counterpart_linked=min(len(copies), COUNTERPART_LINKS))
            supports.append(_d("counterpart_copy_in_gap", "%s %s %d %s of this conversation inside the gap: %d "
                               "not on this phone, %d deleted here.%s" % (
                                   " and ".join(names), "holds" if len(names) == 1 else "hold", len(copies),
                                   "message" if len(copies) == 1 else "messages", absent, len(copies) - absent,
                                   "" if len(copies) <= COUNTERPART_LINKS else " %d of them are linked."
                                   % COUNTERPART_LINKS), [c["uid"] for c in copies[:COUNTERPART_LINKS]]))
        else:
            counts["holes"] += 1
        out.append({
            "kind": "hole_confirmed_by_counterpart" if copies else "hole",
            "strength": "confirmed_by_counterpart" if copies else "unconfirmed",
            "measures": measures,
            "directions": {"supports": supports,
                           "undercuts": [_d("no_data_period", "A quiet period in a conversation is not by itself "
                                            "a deletion; no message has to have existed.")]},
            "period_start": a, "period_end": b,
            "records": [_rec(ext, hole["before"], "before_gap"), _rec(ext, hole["after"], "after_gap")]})

    # 5. concealment context
    apps = FV.field_values(conn, ext, ("InstalledApplication",), ("Categories", "Name", "Identifier"))
    app_times_ = FV.times_for(conn, ext, list(apps), ("InstallDate", "PurchaseDate", "DeletedDate"))
    for uid, v in sorted(apps.items()):
        cats = sorted(set(v["values"].get("Categories", ())) & set(CONCEALMENT_CATEGORIES))
        t = app_times_.get(uid, {})
        if cats:
            counts["concealment_apps"] += 1
            when = t.get("InstallDate") or t.get("PurchaseDate")
            out.append({
                "kind": "concealment_app", "strength": "category_recorded",
                "measures": {"phone_label": label, "categories": cats, "install": t.get("InstallDate"),
                             "purchase": t.get("PurchaseDate"), "removed": t.get("DeletedDate")},
                "directions": {"supports": [_d("category_recorded", "The phone report puts this app in the %s "
                                               "category." % ", ".join(cats), [uid])],
                               "undercuts": [_d("synced_attribution", "Installed is not used: the records do not "
                                                "show the app was opened.")]},
                "period_start": when, "period_end": t.get("DeletedDate") or when,
                "records": [_rec(ext, uid, "app", "Categories")]})
        if t.get("DeletedDate"):
            counts["apps_removed"] += 1
            out.append({
                "kind": "app_removed", "strength": "event_recorded",
                "measures": {"phone_label": label, "removed": t["DeletedDate"], "categories": cats},
                "directions": {"supports": [_d("event_recorded", "The app record carries a removal time.", [uid])],
                               "undercuts": []},
                "period_start": t["DeletedDate"], "period_end": t["DeletedDate"],
                "records": [_rec(ext, uid, "app", "DeletedDate")]})
    events = FV.field_values(conn, ext, ("DeviceEvent", "PoweringEvent"), ("EventType", "Event"))
    ev_times = FV.times_for(conn, ext, list(events), ("StartTime", "TimeStamp"))
    for uid, v in sorted(events.items()):
        t = ev_times.get(uid, {})
        when = t.get("StartTime") or t.get("TimeStamp")
        if v["model_type"] == "DeviceEvent" and "Wipe" in v["values"].get("EventType", ()):
            counts["wipes"] += 1
            out.append({
                "kind": "wipe", "strength": "event_recorded", "measures": {"phone_label": label, "instant": when},
                "directions": {"supports": [_d("event_recorded", "The phone recorded a wipe event.", [uid])],
                               "undercuts": [_d("wipe_scope_unknown", "Which records a wipe would clear is not "
                                                "established, so it is shown beside deletions and never used to "
                                                "date them.")]},
                "period_start": when, "period_end": when, "records": [_rec(ext, uid, "event", "EventType")]})
        elif v["model_type"] == "PoweringEvent" and any(str(x).lower() == "off" for x in v["values"].get("Event", ())):
            counts["power_offs"] += 1
            out.append({
                "kind": "power_off", "strength": "event_recorded", "measures": {"phone_label": label, "instant": when},
                "directions": {"supports": [_d("event_recorded", "The phone recorded being switched off.", [uid])],
                               "undercuts": []},
                "period_start": when, "period_end": when, "records": [_rec(ext, uid, "event", "Event")]})
    scr = defaultdict(list)
    for r in conn.execute(text(
            "SELECT p.document_index, p.parent_ordinal FROM phone_records p WHERE p.extraction_id = :e AND "
            "p.model_type = 'ScrambledMessageData'"), {"e": ext}):
        if r.parent_ordinal is not None:
            parent = str(ids.record_uid(ext, r.document_index, r.parent_ordinal))
            pm = by_uid.get(parent)
            scr[(pm["app"], pm["thread_key"]) if pm and pm["thread_key"] else ("", "parent:" + parent)].append(parent)
    for (app, thread), parents in sorted(scr.items()):
        counts["scrambled"] += len(parents)
        times = [by_uid[p]["sort_instant"] for p in parents if p in by_uid and by_uid[p]["sort_instant"]]
        out.append({
            "kind": "scrambled_messages", "strength": "category_recorded",
            "measures": {"phone_label": label, "app": app, "thread_key": None if thread.startswith("parent:") else
                         thread, "messages": len(set(parents))},
            "directions": {"supports": [_d("event_recorded", "%d messages here are marked unreadable by the phone "
                                           "report." % len(set(parents)))],
                           "undercuts": [_d("decoder_differs_by_app", "Why a message is unreadable is not established "
                                            "(05 section 20).")]},
            "period_start": min(times) if times else None, "period_end": max(times) if times else None,
            "records": [_rec(ext, p, "unreadable_message", "ScrambledMessageData") for p in sorted(set(parents))]})
    return out


COUNTERPART_LINKS = 20


def counterpart_copies(conn, case_id, phones) -> dict:
    """``{(extraction_id, thread_key): [{"t", "uid", "extraction_id", "phone_label", "deleted_here"}]}``: for each
    conversation, the messages another phone holds in a conversation linked to it by approach 2's strong matches
    whose copy on this phone is missing or deleted (19.S6-c), in time order."""
    from itertools import combinations

    from services.phone_analysis import message_reconciliation as R
    if len(phones) < 2:
        return {}
    params = {k: v["default"] for k, v in R.PARAMETERS.items()}
    people = R._people(conn, case_id)
    data = {e: R.load_phone(conn, e, people) for e in phones}
    owners = {e: R._owners(conn, e, people) for e in phones}
    devices = {e: R.device_ids(conn, e) for e in phones}
    out = defaultdict(list)
    for x, y in combinations(sorted(phones), 2):
        px, py = data[x], data[y]
        if R.same_device(devices[x], devices[y]) or not R.candidate_pair(px, py, owners[x], owners[y]):
            continue
        res = R.match_pair(px, py, owners[x], owners[y], params)
        links = R.strong_links(res["matched"], px, py)
        copy_of = ({}, {})         # message index on one side -> its matched index on the other
        tied = (set(), set())      # messages with two equally close copies: neither side is said to lack them
        for ties in res["ambiguous"]:
            for c in ties:
                tied[0].add(c[1])
                tied[1].add(c[2])
        for c in res["matched"]:
            i, j = c[1], c[2]
            copy_of[0][i], copy_of[1][j] = j, i
        for side, (here, there, ph, pt) in enumerate(((x, y, px, py), (y, x, py, px))):
            theirs = copy_of[1 - side]    # there-index -> here-index
            by_thread = defaultdict(list)
            for k, m in enumerate(pt["msgs"]):
                by_thread[m["thread"]].append(k)
            for (s_, thread), others in links.items():
                if s_ != side:
                    continue
                for th in sorted(others, key=str):
                    for k in by_thread.get(th, ()):
                        m = pt["msgs"][k]
                        if m["deleted"] or k in tied[1 - side]:
                            continue
                        h = theirs.get(k)
                        if h is None or ph["msgs"][h]["deleted"]:
                            out[(here, thread)].append({"t": m["t"], "uid": m["uid"], "extraction_id": there,
                                                        "phone_label": phones[there], "deleted_here": h is not None})
    for v in out.values():
        v.sort(key=lambda c: (c["t"], c["uid"]))
    return dict(out)


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    counts["by_explanation"] = defaultdict(int)
    phones = FV.active_phones(conn, case_id)
    counterpart = counterpart_copies(conn, case_id, phones)
    results = []
    for i, (ext, label) in enumerate(phones.items()):
        if ctx is not None:
            ctx.progress(i, len(phones), label)
            if ctx.cancelled():
                break
        results.extend(analyse_phone(conn, ext, label, params, counts, counterpart))
    if ctx is not None:
        ctx.progress(len(phones), len(phones))
    counts["by_explanation"] = dict(counts["by_explanation"])
    return results, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
