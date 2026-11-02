"""Comm events and threads from the ``type`` mappings (docs/cellebrite/02 sections 5.3, 6.9, 12.2).

Runs inside the applier (6.7) after the rule rows are marked, for each mapping with a ``comm_kind``:

- one ``phone_comm_events`` row per record of the type: the event time is the time value the mapping marked
  ``is_event_time``; the body and subject are complete; direction from ``Direction`` for calls (a disagreement
  with the owner flag sets ``direction_conflict`` and keeps ``Direction``), from the sender's owner flag
  otherwise; the thread key by the mapping's strategy;
- an ``owner_implicit`` participation for a message, call or email with no party marked as the phone's owner,
  with the side it fills (``implied_role``) from the direction (5.3, owner side);
- one ``phone_threads`` row per thread key, and one per Chat record (a chat with no messages is still a thread).

Thread keys hold the extraction id, so no thread spans two phones. A counterpart set and an email subject are
hashed into the key (the parts stay in the events and parties). Party keys are the identity key when 8.2 has
given one, else the identifier as captured.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from services.phone import body as B
from services.phone import generic, ids
from services.phone import values as V

EVENT_COLUMNS = ("case_id", "extraction_id", "interpretation_level", "mapping_version_id", "mapping_row_id",
                 "generation", "event_uid", "record_uid", "document_index", "ordinal", "locator", "model_type", "kind",
                 "thread_key", "app", "direction", "direction_basis", "sort_instant", "time_field", "time_uid",
                 "end_instant", "end_basis", "body", "subject", "status", "call_duration_s", "call_status", "video",
                 "deleted_state", "flags", "dup_group_uid", "dup_rule_version")
THREAD_COLUMNS = ("case_id", "extraction_id", "interpretation_level", "mapping_version_id", "mapping_row_id",
                  "generation", "thread_key", "record_uid", "app", "thread_kind", "chat_type", "title_in_record",
                  "first_instant", "last_instant", "event_count", "party_identity_keys")
PARTY_COLUMNS = generic.COLUMNS["phone_participations"] + ("implied_role",)
COLUMNS = {"phone_comm_events": EVENT_COLUMNS, "phone_threads": THREAD_COLUMNS,
           "phone_participations_implicit": PARTY_COLUMNS}
OWNER_SIDE_KINDS = ("message", "call", "email")
SUBJECT_PREFIX = re.compile(r"^\s*(re|fwd?|aw|wg|tr|sv)\s*(\[\d+\])?\s*:\s*", re.I)
HEADER_FIELDS = ("MessageId", "MessageID", "InReplyTo", "References")  # used when a report carries them (none of 14 do)


def normalised_subject(s):
    s = s or ""
    while True:
        t = SUBJECT_PREFIX.sub("", s, count=1)
        if t == s:
            break
        s = t
    return " ".join(s.split()).casefold()


def _message_ids(value):
    """Message ids in a header value, normalised: angle brackets removed, case folded, in order."""
    if not value or not str(value).strip():
        return []
    found = re.findall(r"<([^<>\s]+)>", str(value))
    return [x.strip().lower() for x in (found or str(value).split()) if x.strip("<> ")]


def header_thread_root(headers):
    """The thread an email belongs to by its headers (02 decision 45): the first id of References (the thread's
    first message), else In-Reply-To, else its own Message-ID. None when it carries none of them."""
    for name in ("References", "InReplyTo", "MessageId", "MessageID"):
        ids_ = _message_ids(headers.get(name))
        if ids_:
            return ids_[0]
    return None


def _h(*parts):
    return hashlib.sha256("\x1f".join(p or "" for p in parts).encode("utf-8")).hexdigest()[:32]


def party_key(identity_key, identifier_raw):
    if identity_key:
        return identity_key
    if identifier_raw and identifier_raw.strip():
        return "raw:" + identifier_raw.strip()
    return None


class _Writer(generic.Writer):
    """COPY writer for the mapped tables; the implicit owner rows go to ``phone_participations``."""

    def _flush(self):
        implicit = self.buf.pop("phone_participations_implicit", None)
        super()._flush()
        if implicit:
            self.buf["phone_participations_implicit"] = implicit
            cols = PARTY_COLUMNS
            import io
            data = io.StringIO()
            for r in implicit:
                data.write("\t".join(generic._copy_text(r.get(c)) for c in cols))
                data.write("\n")
            with self.raw.cursor() as cur:
                with cur.copy("COPY phone_participations (%s) FROM STDIN" % ", ".join(cols)) as cp:
                    cp.write(data.getvalue())
            implicit.clear()


def _parties(conn, ext, gen, t):
    out = defaultdict(list)
    for r in conn.execute(text(
            "SELECT record_uid, role, is_phone_owner, identity_key, identifier_raw FROM phone_participations WHERE "
            "extraction_id = :e AND generation = :g AND model_type = :t"), {"e": ext, "g": gen, "t": t}):
        out[r[0]].append(r)
    return out


def _times(conn, ext, gen, t, where, params=None):
    out = {}
    for r in conn.execute(text(
            "SELECT record_uid, effective_instant, field_name, time_uid FROM phone_time_values WHERE extraction_id = :e "
            "AND generation = :g AND model_type = :t AND " + where + " ORDER BY record_uid, value_index"),
            dict(params or {}, e=ext, g=gen, t=t)):
        out.setdefault(r[0], r)
    return out


def _effective_text(corr, uid, fmap, name):
    """A top-level field's first text, as corrected when a correction is in effect (02 section 10.3)."""
    for f in fmap.get(name, ()):
        for v in f.real_values:
            if v.text is not None:
                fixed = corr.get((uid, name, v.index))
                return fixed[0] if fixed else v.text
    return None


def _chat_ordinals(conn, ext):
    return {(r[0], r[1]) for r in conn.execute(text(
        "SELECT document_index, ordinal FROM phone_records WHERE extraction_id = :e AND model_type = 'Chat'"),
        {"e": ext})}


def build(conn, ext, case_id, gen, mappings, levels):
    """Write comm events, implicit owner rows and threads for every comm mapping in ``mappings`` (already
    filtered to those applied, not suspended). ``levels``: {rule_id: interpretation level}. Returns counts."""
    w = _Writer(conn, COLUMNS)
    chats = _chat_ordinals(conn, ext)
    thread_of_record = {}
    stats = defaultdict(int)
    chat_mapping = None
    for m in mappings:
        b = m.typed
        if b.comm_kind == "thread":
            chat_mapping = m
            continue
        if b.comm_kind is None:
            continue
        _events(conn, w, ext, case_id, gen, m, b, levels, chats, thread_of_record, stats)
    w.flush()
    _threads(conn, w, ext, case_id, gen, chat_mapping, levels, stats)
    w.flush()
    return dict(stats)


def _events(conn, w, ext, case_id, gen, m, b, levels, chats, thread_of_record, stats):
    t, kind = b.applies_to, b.comm_kind
    event_times = _times(conn, ext, gen, t, "is_event_time")
    end_times = _times(conn, ext, gen, t, "field_name = :f", {"f": b.end_time.field}) if b.end_time.field else {}
    parties = _parties(conn, ext, gen, t)
    from services.phone import corrections
    corr = corrections.current(conn, ext)
    rec_level = levels["%s.record" % m.name]
    implicit_rule = "%s.owner_implicit" % m.name
    rows = conn.execute(text(
        "SELECT document_index, ordinal, parent_ordinal, top_ordinal, deleted_state, body FROM phone_records WHERE "
        "extraction_id = :e AND model_type = :t ORDER BY document_index, ordinal").execution_options(
        stream_results=True, yield_per=2000), {"e": ext, "t": t})
    sf = b.status_fields
    body_field = "Body" if "Body" in b.text_fields else None
    subject_field = "Subject" if "Subject" in b.text_fields else None
    for doc, ordinal, parent, top, deleted_state, body in rows:
        uid = ids.record_uid(ext, doc, ordinal)
        fmap = defaultdict(list)
        for f in B.fields(body):
            fmap[f.name].append(f)
        first = lambda name: _effective_text(corr, uid, fmap, name) if name else None  # noqa: E731
        flags = []
        ps = parties.get(uid, [])
        owner_roles = {p[1] for p in ps if p[2] is True}
        direction, basis = "unknown", None
        if b.participants.direction_field:
            d = (first(b.participants.direction_field) or "").lower()
            if d in ("incoming", "outgoing"):
                direction, basis = d, "direction_field"
                if kind == "call" and owner_roles:
                    if (d == "outgoing" and owner_roles == {"callee"}) or (d == "incoming" and owner_roles == {"caller"}):
                        flags.append("direction_conflict")
        if basis is None:
            senders = [p for p in ps if p[1] == "sender"]
            if senders and senders[0][2] is True:
                direction, basis = "outgoing", "sender_owner_flag"
            elif senders and senders[0][2] is False:
                direction, basis = "incoming", "sender_owner_flag"
        if kind in OWNER_SIDE_KINDS and not owner_roles:
            if kind == "call":
                implied = {"outgoing": "caller", "incoming": "callee"}.get(direction)
            else:
                implied = {"outgoing": "sender", "incoming": "recipient"}.get(direction)
            row = {c: None for c in PARTY_COLUMNS}
            row.update(case_id=case_id, extraction_id=ext, document_index=doc, ordinal=ordinal, record_uid=uid,
                       root_record_uid=ids.record_uid(ext, doc, top), locator="%s/%d/r%d" % (ext, doc, ordinal),
                       model_type=t, interpretation_level=levels[implicit_rule], mapping_version_id=m.id,
                       mapping_row_id=implicit_rule, deleted_state=deleted_state, flags=[], generation=gen,
                       participation_uid=uuid.uuid5(uid, "owner_implicit"), role="owner_implicit",
                       role_basis="owner_side", implied_role=implied)
            w.add("phone_participations_implicit", row)
            stats["owner_implicit:%s" % t] += 1
        # thread
        key = None
        strat = b.thread.strategy
        if strat == "parent_chat" and parent is not None and (doc, parent) in chats:
            key = "chat:%s:%s" % (ext, ids.record_uid(ext, doc, parent))
        elif parent is not None and ids.record_uid(ext, doc, top) in thread_of_record:
            key = thread_of_record[ids.record_uid(ext, doc, top)]
        else:
            if strat == "parent_chat":
                strat = b.thread.fallback or "none"
            app = first(b.app_field)
            if strat == "counterpart_set":
                keys = sorted({k for k in (party_key(p[3], p[4]) for p in ps if p[2] is not True) if k})
                key = "set:%s:%s:%s" % (ext, kind, _h(app, *keys))
            elif strat == "field":
                hdr = header_thread_root({h: first(h) for h in HEADER_FIELDS})
                if hdr:
                    key = "hdr:%s:%s" % (ext, _h(hdr))
                else:
                    key = "email:%s:%s" % (ext, _h(first(b.thread.group_field), normalised_subject(first(subject_field))))
            elif strat == "self":
                key = "%s:%s" % (b.thread.fixed_key or kind, ext)
        if key:
            thread_of_record[uid] = key
        et = event_times.get(uid)
        sort_instant = et[1] if et else None
        duration = None
        if b.end_time.duration_field:
            duration = V.parse_timespan(first(b.end_time.duration_field))[0] if first(b.end_time.duration_field) else None
        end_instant, end_basis = None, None
        if b.end_time.field and uid in end_times:
            end_instant, end_basis = end_times[uid][1], "field"
        elif duration is not None and sort_instant is not None:
            end_instant, end_basis = sort_instant + timedelta(seconds=float(duration)), "computed"
        status = first(sf.get("status"))
        video = V.parse_boolean(first(sf.get("video"))) if sf.get("video") else None
        w.add("phone_comm_events", {
            "case_id": case_id, "extraction_id": ext, "interpretation_level": rec_level, "mapping_version_id": m.id,
            "mapping_row_id": "%s.record" % m.name, "generation": gen, "event_uid": uuid.uuid5(uid, "comm"),
            "record_uid": uid, "document_index": doc, "ordinal": ordinal, "locator": "%s/%d/r%d" % (ext, doc, ordinal),
            "model_type": t, "kind": kind, "thread_key": key, "app": first(b.app_field), "direction": direction,
            "direction_basis": basis, "sort_instant": sort_instant, "time_field": et[2] if et else None,
            "time_uid": et[3] if et else None, "end_instant": end_instant, "end_basis": end_basis,
            "body": first(body_field), "subject": first(subject_field), "status": status,
            "call_duration_s": duration if kind == "call" else None, "call_status": status if kind == "call" else None,
            "video": video, "deleted_state": deleted_state, "flags": flags, "dup_group_uid": None,
            "dup_rule_version": None})
        stats["events:%s" % kind] += 1
        stats["events:%s:threaded" % kind] += 1 if key else 0
        if kind == "message":
            stats["messages:%s" % ("under_chat" if key and key.startswith("chat:") else "top_level" if parent is None
                                   else "nested")] += 1


THREAD_KIND = {"message": "sms_group", "call": "call_log", "email": "email_folder", "voicemail": "voicemail",
               "chat_activity": "chat"}


def _threads(conn, w, ext, case_id, gen, chat_mapping, levels, stats):
    agg = {}
    for r in conn.execute(text(
            "SELECT ev.thread_key, min(ev.sort_instant), max(ev.sort_instant), count(*), min(ev.kind), "
            "min(ev.app), min(ev.mapping_row_id), (array_agg(ev.mapping_version_id))[1], "
            "min(ev.interpretation_level) FROM phone_comm_events ev WHERE ev.extraction_id = :e AND ev.generation = :g "
            "AND ev.thread_key IS NOT NULL GROUP BY ev.thread_key"), {"e": ext, "g": gen}):
        agg[r[0]] = r
    keys = defaultdict(set)
    for tk, ik, raw, owner in conn.execute(text(
            "SELECT ev.thread_key, p.identity_key, p.identifier_raw, p.is_phone_owner FROM phone_comm_events ev JOIN "
            "phone_participations p ON p.record_uid = ev.record_uid AND p.generation = ev.generation WHERE "
            "ev.extraction_id = :e AND ev.generation = :g AND ev.thread_key IS NOT NULL"), {"e": ext, "g": gen}):
        k = party_key(ik, raw)
        if k:
            keys[tk].add(k)
    chats = {}
    if chat_mapping is not None:
        b = chat_mapping.typed
        for doc, ordinal, body in conn.execute(text(
                "SELECT document_index, ordinal, body FROM phone_records WHERE extraction_id = :e AND model_type = :t "
                "ORDER BY document_index, ordinal"), {"e": ext, "t": b.applies_to}):
            fmap = defaultdict(list)
            for f in B.fields(body):
                fmap[f.name].append(f)
            uid = ids.record_uid(ext, doc, ordinal)
            chats["chat:%s:%s" % (ext, uid)] = (uid, generic._first_text(fmap, b.app_field) if b.app_field else None,
                                                 generic._first_text(fmap, "ChatType"),
                                                 generic._first_text(fmap, "Name"))
        for uid, ik, raw in conn.execute(text(
                "SELECT record_uid, identity_key, identifier_raw FROM phone_participations WHERE extraction_id = :e AND "
                "generation = :g AND model_type = :t"), {"e": ext, "g": gen, "t": b.applies_to}):
            k = party_key(ik, raw)
            if k:
                keys["chat:%s:%s" % (ext, uid)].add(k)
    for tk in sorted(set(agg) | set(chats)):
        a = agg.get(tk)
        c = chats.get(tk)
        if c is not None:
            mv, rule = chat_mapping.id, "%s.record" % chat_mapping.name
            kind = "chat"
        else:
            mv = a[7]
            rule = "%s.thread" % a[6][:-len(".record")]
            kind = "chat" if tk.startswith("chat:") else THREAD_KIND.get(a[4], "sms_group")
        w.add("phone_threads", {
            "case_id": case_id, "extraction_id": ext, "interpretation_level": levels.get(rule, "applied_unconfirmed"),
            "mapping_version_id": mv, "mapping_row_id": rule, "generation": gen, "thread_key": tk,
            "record_uid": c[0] if c else None, "app": (c[1] if c else None) or (a[5] if a else None),
            "thread_kind": kind, "chat_type": c[2] if c else None, "title_in_record": c[3] if c else None,
            "first_instant": a[1] if a else None, "last_instant": a[2] if a else None, "event_count": a[3] if a else 0,
            "party_identity_keys": sorted(keys.get(tk, ()))})
        stats["threads:%s" % kind] += 1
