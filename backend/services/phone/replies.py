"""Replies, quotes and forwards on stream rows (docs/cellebrite/03 section 6.6, 07 section 4.4).

A report keeps these as child records of the message under ``MessageExtraData``. They are not a projection of their
own: everything here is read, per window, from the rows the interpreter already writes for each generation, so a
new generation of a phone carries them with no extra step and no record is added or changed:

- ``phone_record_summaries``: the child record and its type;
- ``phone_texts``: ``OriginalMessageID`` on the child, and ``Identifier`` on the message it names;
- ``phone_participations`` and ``phone_time_values``: ``OriginalSender`` and ``TimeCreated`` of a forward.

The link is the report's own: a message is the original of a reply only when its ``Identifier`` equals the reply's
``OriginalMessageID`` on the same phone. Measured 5 Nov on the 4 reference phones: 225 of 225 replies resolve to one
message each, none later than the reply, 9 in another conversation. The 35 replies on the synthetic phones name no
message that exists, so a reply whose original is missing is stated as such, never dropped.

Attribution stays honest. ``OriginalSender`` is who first wrote a forwarded message; the row's sender stays the
party that sent this copy. The report's original sender sits on the child record, so it can never become ``from``.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

from sqlalchemy import text

from services.phone import time_display as T

REPLY_TYPES = {"ReplyMessageData": "reply", "QuotedMessageData": "quote"}
FORWARD_TYPE = "ForwardedMessageData"
EXCERPT = 280
# the party that sent the message (never a forward's original author)
SENT_BY = ("sender", "caller", "author")


def _digest(value: str) -> str:
    """What ``ix_phone_texts_message_identifier`` is keyed on: md5, so a long value can never fail a write."""
    return hashlib.md5(value.encode("utf-8")).hexdigest()  # noqa: S324 - an index key, not a security use


def _children(conn, uids):
    return conn.execute(text(
        "SELECT s.record_uid, s.parent_record_uid, s.extraction_id, s.model_type FROM phone_record_summaries s "
        "JOIN phone_interpretation_state st ON st.extraction_id = s.extraction_id AND st.generation = s.generation "
        "WHERE s.parent_record_uid = ANY(:u) AND s.model_type = ANY(:t) ORDER BY s.parent_record_uid, s.ordinal"),
        {"u": uids, "t": list(REPLY_TYPES) + [FORWARD_TYPE]}).fetchall()


def _original_ids(conn, child_uids):
    if not child_uids:
        return {}
    return {r.record_uid: r.value for r in conn.execute(text(
        "SELECT t.record_uid, t.value FROM phone_texts t JOIN phone_interpretation_state st ON "
        "st.extraction_id = t.extraction_id AND st.generation = t.generation WHERE t.record_uid = ANY(:u) AND "
        "t.field_name = 'OriginalMessageID' ORDER BY t.value_index DESC"), {"u": child_uids})}


def _targets(conn, wanted):
    """Messages by (phone, Identifier), every copy of each."""
    out = defaultdict(list)
    if not wanted:
        return out
    exts = sorted({str(e) for e, _ in wanted})
    for r in conn.execute(text(
            "SELECT t.extraction_id, t.value AS identifier, ev.event_uid, ev.record_uid, ev.thread_key, ev.kind, "
            "ev.sort_instant, ev.time_field, ev.body, ev.subject, ev.deleted_state, ev.interpretation_level FROM "
            "phone_texts t JOIN phone_interpretation_state st ON st.extraction_id = t.extraction_id AND "
            "st.generation = t.generation JOIN phone_comm_events ev ON ev.record_uid = t.record_uid AND "
            "ev.generation = t.generation WHERE t.extraction_id = ANY(CAST(:e AS uuid[])) AND t.model_type = "
            "'InstantMessage' AND t.field_name = 'Identifier' AND md5(t.value) = ANY(CAST(:h AS text[])) "
            "ORDER BY ev.record_uid"),
            {"e": exts, "h": sorted({_digest(v) for _, v in wanted})}):
        if (str(r.extraction_id), r.identifier) in wanted:
            out[(str(r.extraction_id), r.identifier)].append(r)
    return out


def _parties(conn, uids):
    """The people named on these records: the sender of a target, the original sender of a forward."""
    out = defaultdict(list)
    if not uids:
        return out
    for p in conn.execute(text(
            "SELECT p.record_uid, p.identity_key, p.role, p.implied_role, p.name_in_record, p.identifier_raw, "
            "p.is_phone_owner FROM phone_participations p JOIN phone_interpretation_state st ON st.extraction_id = "
            "p.extraction_id AND st.generation = p.generation WHERE p.record_uid = ANY(:u) ORDER BY p.record_uid, "
            "p.ordinal, p.participation_uid"), {"u": uids}):
        out[p.record_uid].append(p)
    return out


def _times(conn, uids):
    if not uids:
        return {}
    out = {}
    for r in conn.execute(text(
            "SELECT t.record_uid, t.effective_instant, t.field_name FROM phone_time_values t JOIN "
            "phone_interpretation_state st ON st.extraction_id = t.extraction_id AND st.generation = t.generation "
            "WHERE t.record_uid = ANY(:u) AND t.field_name = 'TimeCreated' ORDER BY t.record_uid, t.value_index"),
            {"u": uids}):
        out.setdefault(r.record_uid, r)
    return out


def _thread_titles(conn, keys):
    if not keys:
        return {}
    return {r.thread_key: r.title_in_record for r in conn.execute(text(
        "SELECT t.thread_key, t.title_in_record FROM phone_threads t JOIN phone_interpretation_state st ON "
        "st.extraction_id = t.extraction_id AND st.generation = t.generation WHERE t.thread_key = ANY(:k)"),
        {"k": sorted(keys)})}


def _pick(copies, parent_uid, thread_key):
    """The one message a reply points at: never the reply itself; its own conversation first, then a stable order."""
    others = [c for c in copies if c.record_uid != parent_uid]
    return next((c for c in others if c.thread_key == thread_key), others[0] if others else None)


def for_rows(conn, ctx, rows, zone: str) -> dict:
    """``{record_uid: {"replies": [...], "forward": {...} or None}}`` for the rows that carry either.

    A reply: ``kind`` reply or quote; ``original_id`` the report's id; ``state`` found, not_in_extraction (the id names
    no message on this phone) or not_recorded (the report gives no id); ``target`` for a found one. Four to seven
    queries a window, none per row."""
    from services.phone.streams import row_flags

    uids = [r.record_uid for r in rows]
    children = _children(conn, uids) if uids else []
    if not children:
        return {}
    by_uid = {r.record_uid: r for r in rows}
    reply_children = [c for c in children if c.model_type in REPLY_TYPES]
    forwards = [c for c in children if c.model_type == FORWARD_TYPE]
    ids = _original_ids(conn, [c.record_uid for c in reply_children])
    wanted = {(str(c.extraction_id), ids[c.record_uid]) for c in reply_children if c.record_uid in ids}
    found = _targets(conn, wanted)
    chosen = {}
    for c in reply_children:
        copies = found.get((str(c.extraction_id), ids.get(c.record_uid)), [])
        chosen[c.record_uid] = _pick(copies, c.parent_record_uid, by_uid[c.parent_record_uid].thread_key)
    picked = [t for t in chosen.values() if t is not None]
    parties = _parties(conn, sorted({t.record_uid for t in picked} | {c.record_uid for c in forwards}))
    ctx.load([p.identity_key for ps in parties.values() for p in ps])
    times = _times(conn, [c.record_uid for c in forwards])
    titles = _thread_titles(conn, {t.thread_key for t in picked if t.thread_key})

    def lab(ext, p):
        return ctx.label(ext, identity_key=p.identity_key, name_in_record=p.name_in_record,
                         identifier_raw=p.identifier_raw, is_phone_owner=p.is_phone_owner, role=p.role)

    out = defaultdict(lambda: {"replies": [], "forward": None})
    for c in children:
        parent, ext = c.parent_record_uid, str(c.extraction_id)
        if c.model_type == FORWARD_TYPE:
            ps = [p for p in parties.get(c.record_uid, []) if p.role == "original_sender"]
            at = times.get(c.record_uid)
            # A message forwarded twice still reads as one forward; the first child is the report's first.
            if out[parent]["forward"] is None:
                out[parent]["forward"] = {"original_sender": lab(ext, ps[0]) if ps else None,
                                          "time_created": T.format_full(at.effective_instant, zone)
                                          if at is not None and at.effective_instant is not None else None}
            continue
        original_id = ids.get(c.record_uid)
        target = chosen.get(c.record_uid)
        entry = {"kind": REPLY_TYPES[c.model_type], "original_id": original_id,
                 "state": "found" if target is not None else "not_in_extraction" if original_id else "not_recorded",
                 "target": None}
        if target is not None:
            senders = [p for p in parties.get(target.record_uid, [])
                       if p.role in SENT_BY or p.implied_role in ("sender", "caller")]
            body = target.body or ""
            entry["target"] = {
                "event_uid": str(target.event_uid), "record_uid": str(target.record_uid),
                "thread_key": target.thread_key, "thread_title": titles.get(target.thread_key),
                "same_thread": target.thread_key == by_uid[parent].thread_key, "kind": target.kind,
                "from": lab(ext, senders[0]) if senders else None,
                "time": T.time_block(target.sort_instant, zone, offset_present=target.sort_instant is not None,
                                     time_field=target.time_field)["full"],
                "excerpt": body[:EXCERPT] or None, "chars": len(body), "subject": target.subject,
                "flags": row_flags(target)}
        out[parent]["replies"].append(entry)
    return dict(out)


def reply_words(row) -> list:
    """A forward and a reply as the row states them (03 section 6.6), for an export: the row's sender stays the sender
    of this copy. The PDF prints these lines and RSMF carries them in custom fields."""
    from services.phone.labels import label_text
    out = []
    forward = row.get("forward")
    if forward:
        by = forward.get("original_sender")
        out.append("Forwarded. " + ("First written by %s%s." % (
            label_text(by), ", %s" % forward["time_created"] if forward.get("time_created") else "")
            if by else "The report does not say who first wrote it."))
    for link in row.get("replies") or []:
        verb = "Quoting" if link["kind"] == "quote" else "Replying to"
        target = link.get("target")
        if target:
            who = target.get("from")
            excerpt = target.get("excerpt") or "(no text)"
            out.append("%s %s, %s: %s%s" % (verb, label_text(who) if who else "(sender not recorded)", target["time"],
                                            excerpt, "…" if target.get("chars", 0) > len(target.get("excerpt") or "")
                                            else ""))
        elif link["state"] == "not_in_extraction":
            out.append("%s a message that is not in this extraction (the report's id: %s)." % (verb, link["original_id"]))
        else:
            out.append("Marked as a reply; the report does not say to which message.")
    return out
