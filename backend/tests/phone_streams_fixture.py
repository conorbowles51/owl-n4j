"""Synthetic phones written straight into 02's derived tables, for the screen tests (03 sections 4 to 6).

Invented data only: numbers are 555 numbers, names are made up. A phone is captured (one record per event, so the
record panel reads a real body) and interpreted at generation 1 with the event, party, thread, text, identity, name
and owner rows a sweep would write, without running the sweep. ``bulk_events`` writes many events by SQL for the
size tests (03 section 6.8).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from services.phone import fold as F
from services.phone import identities as I
from services.phone import ids
from tests.phone_pg import fld, make_extraction, model

GEN = 1


def ident_kind(key):
    return {"phone": "phone", "email": "email", "app": "app_user"}.get(key.split(":", 1)[0], "other")


def display(key):
    v = key.split(":", 1)[1] if ":" in key else key
    if key.startswith("phone:+1") and len(v) == 12:
        return "+1 %s-%s-%s" % (v[2:5], v[5:8], v[8:])
    return v.rsplit(":", 1)[-1]


def ensure_identity(c, case, key, subkind=None):
    iid = I.identity_id(case, key)
    c.execute(text(
        "INSERT INTO phone_identities (id, case_id, identity_key, kind, subkind, value_normalised, value_display, "
        "sighting_count, phone_count) VALUES (:i, :c, :k, :kind, :sk, :v, :d, 1, 1) ON CONFLICT DO NOTHING"),
        {"i": iid, "c": case, "k": key, "kind": ident_kind(key), "sk": subkind, "v": key.split(":", 1)[-1],
         "d": display(key)})
    return iid


def phone(c, case, *, label="C3", owner="phone:+12025550100", device_zone=None, events=(), contacts=None,
          threads=None, capture_state="captured", interpreted=True):
    """``events``: dicts with kind, instant, direction, app, body, subject, thread, deleted_state, dup, parties
    [(identity_key, role, is_owner, name_in_record, identifier_raw[, implied_role])], call_duration_s, call_status.
    ``contacts``: {identity_key: name on this phone}. ``threads``: {thread: {"chat_type", "title", "members"}}.
    Returns (extraction_id, [event dicts with record_uid and event_uid])."""
    records = [(i, None, i, model("Call" if e.get("kind") == "call" else "InstantMessage",
                                  [fld("Body", ("String", e.get("body") or ""))]))
               for i, e in enumerate(events)] or [(0, None, 0, model("InstantMessage", []))]
    ext = make_extraction(c, case, records, label=label, capture_state=capture_state)
    c.execute(text(
        "INSERT INTO phone_interpretation_state (extraction_id, case_id, generation, status, interpreted_at, "
        "identities_at, texts_at, projected_at, device_zone, device_zone_basis) VALUES (:e, :c, :g, :s, now(), now(), "
        ":t, :t, :z, :zb)"), {"e": ext, "c": case, "g": GEN, "s": "done" if interpreted else "running",
                              "t": datetime.now(timezone.utc) if interpreted else None, "z": device_zone,
                              "zb": "device_metadata" if device_zone else None})
    if owner:
        oid = ensure_identity(c, case, owner)
        c.execute(text(
            "INSERT INTO phone_owner_candidates (case_id, extraction_id, candidate_kind, identity_id, identity_key, "
            "tier, occurrences, basis, generation) VALUES (:c, :e, 'number', :i, :k, 1, 1, 'extracted', :g)"),
            {"c": case, "e": ext, "i": oid, "k": owner, "g": GEN})
    for key, name in (contacts or {}).items():
        iid = ensure_identity(c, case, key)
        c.execute(text(
            "INSERT INTO phone_identity_names (case_id, extraction_id, identity_id, name, basis, occurrences, "
            "is_phone_name, generation) VALUES (:c, :e, :i, :n, 'contact', 1, true, :g)"),
            {"c": case, "e": ext, "i": iid, "n": name, "g": GEN})
    out, seen_threads = [], {}
    for i, e in enumerate(events):
        uid = ids.record_uid(ext, 0, i)
        ev_uid = uuid.uuid5(uid, "comm")
        th = e.get("thread")
        tkey = "chat:%s:%s" % (ext, th) if th else None
        base = {"c": case, "e": ext, "o": i, "u": uid, "loc": "%s/0/r%d" % (ext, i), "g": GEN,
                "mt": "Call" if e.get("kind") == "call" else "InstantMessage"}
        c.execute(text(
            "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, locator, model_type, generation, is_top_level, title, first_instant, has_time, "
            "has_point, deleted_state) VALUES (:c, :e, 0, :o, :u, :u, :loc, :mt, :g, true, 'synthetic', :i, :ht, "
            "false, :ds)"), dict(base, i=e.get("instant"), ht=e.get("instant") is not None,
                                  ds=e.get("deleted_state")))
        c.execute(text(
            "INSERT INTO phone_comm_events (case_id, extraction_id, interpretation_level, generation, event_uid, "
            "record_uid, document_index, ordinal, locator, model_type, kind, thread_key, app, direction, sort_instant, "
            "time_field, body, subject, call_duration_s, call_status, video, deleted_state, dup_group_uid, "
            "dup_rule_version) VALUES (:c, :e, :lvl, :g, :ev, :u, 0, :o, :loc, :mt, :k, :t, :app, :d, :i, "
            "'TimeStamp', :b, :s, :dur, :cs, :v, :ds, :dup, :dv)"),
            dict(base, lvl=e.get("level", "reviewed"), ev=ev_uid, k=e.get("kind", "message"), t=tkey,
                 app=e.get("app", "WhatsApp"), d=e.get("direction", "incoming"), i=e.get("instant"),
                 b=e.get("body"), s=e.get("subject"), dur=e.get("call_duration_s"), cs=e.get("call_status"),
                 v=e.get("video"), ds=e.get("deleted_state", "Intact"), dup=e.get("dup"),
                 dv=1 if e.get("dup") else None))
        for j, p in enumerate(e.get("parties", ())):
            key, role, is_owner, name, raw = p[:5]
            implied = p[5] if len(p) > 5 else None
            if key:
                ensure_identity(c, case, key)
            c.execute(text(
                "INSERT INTO phone_participations (case_id, extraction_id, document_index, ordinal, record_uid, "
                "root_record_uid, locator, model_type, generation, participation_uid, role, role_basis, "
                "is_phone_owner, identifier_raw, name_in_record, identity_key, implied_role) VALUES (:c, :e, 0, :o, "
                ":u, :u, :loc, :mt, :g, :pu, :r, 'container', :io, :raw, :n, :k, :ir)"),
                dict(base, pu=uuid.uuid5(uid, "p%d" % j), r=role, io=is_owner, raw=raw, n=name, k=key, ir=implied))
        for field, value in (("Body", e.get("body")), ("Subject", e.get("subject"))):
            if value:
                c.execute(text(
                    "INSERT INTO phone_texts (case_id, extraction_id, document_index, ordinal, record_uid, "
                    "root_record_uid, locator, model_type, generation, text_uid, body_path, field_name, field_path, "
                    "value_index, value, value_folded, effective_value) VALUES (:c, :e, 0, :o, :u, :u, :loc, :mt, :g, "
                    ":tu, '0', :f, :fp, 0, :v, :vf, :ve)"),
                    dict(base, tu=uuid.uuid5(uid, field), f=field, fp=field, v=value, vf=F.fold(value), ve=value))
        if tkey and tkey not in seen_threads:
            meta = (threads or {}).get(th, {})
            seen_threads[tkey] = meta
            c.execute(text(
                "INSERT INTO phone_threads (case_id, extraction_id, interpretation_level, generation, thread_key, app, "
                "thread_kind, chat_type, title_in_record, party_identity_keys) VALUES (:c, :e, 'reviewed', :g, :t, "
                ":app, 'chat', :ct, :ti, CAST(:m AS text[]))"),
                {"c": case, "e": ext, "g": GEN, "t": tkey, "app": e.get("app", "WhatsApp"),
                 "ct": meta.get("chat_type", "OneOnOne"), "ti": meta.get("title"),
                 "m": meta.get("members") or sorted({p[0] for x in events if x.get("thread") == th
                                                     for p in x.get("parties", ()) if p[0]})})
        out.append(dict(e, record_uid=str(uid), event_uid=str(ev_uid), thread_key=tkey))
    c.execute(text(
        "UPDATE phone_threads t SET event_count = (SELECT count(*) FROM phone_comm_events ev WHERE ev.thread_key = "
        "t.thread_key AND ev.generation = t.generation), first_instant = (SELECT min(sort_instant) FROM "
        "phone_comm_events ev WHERE ev.thread_key = t.thread_key), last_instant = (SELECT max(sort_instant) FROM "
        "phone_comm_events ev WHERE ev.thread_key = t.thread_key) WHERE t.extraction_id = :e"), {"e": ext})
    return ext, out


def bulk_events(c, case, ext, n, *, start, step_seconds=60, other="phone:+12025550143", owner="phone:+12025550100",
                no_time_every=0):
    """``n`` messages by SQL (generate_series): alternating direction, the owner and one other party each, one
    thread; every ``no_time_every``-th has no time."""
    ensure_identity(c, case, other)
    tkey = "chat:%s:bulk" % ext
    c.execute(text(
        "INSERT INTO phone_threads (case_id, extraction_id, interpretation_level, generation, thread_key, app, "
        "thread_kind, chat_type, party_identity_keys) VALUES (:c, :e, 'reviewed', :g, :t, 'WhatsApp', 'chat', "
        "'OneOnOne', ARRAY[:o, :x]) ON CONFLICT DO NOTHING"), {"c": case, "e": ext, "g": GEN, "t": tkey, "o": owner,
                                                               "x": other})
    c.execute(text(
        "INSERT INTO phone_comm_events (case_id, extraction_id, interpretation_level, generation, event_uid, record_uid, "
        "document_index, ordinal, locator, model_type, kind, thread_key, app, direction, sort_instant, time_field, body, "
        "deleted_state) SELECT :c, :e, 'reviewed', :g, md5('ev' || :e || i)::uuid, md5('r' || :e || i)::uuid, 0, "
        "100000 + i, 'bulk', 'InstantMessage', 'message', :t, 'WhatsApp', CASE WHEN i % 2 = 0 THEN 'incoming' ELSE "
        "'outgoing' END, CASE WHEN :nte > 0 AND i % :nte = 0 THEN NULL ELSE :s + (i * :st) * interval '1 second' END, "
        "'TimeStamp', 'synthetic message ' || i, 'Intact' FROM generate_series(1, :n) i"),
        {"c": case, "e": ext, "g": GEN, "t": tkey, "s": start, "st": step_seconds, "n": n, "nte": no_time_every})
    c.execute(text(
        "INSERT INTO phone_participations (case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, "
        "locator, model_type, generation, participation_uid, role, role_basis, is_phone_owner, identity_key) "
        "SELECT :c, :e, 0, 100000 + i, md5('r' || :e || i)::uuid, md5('r' || :e || i)::uuid, 'bulk', 'InstantMessage', "
        ":g, md5('ps' || :e || i)::uuid, 'sender', 'container', i % 2 = 1, CASE WHEN i % 2 = 1 THEN :o ELSE :x END "
        "FROM generate_series(1, :n) i UNION ALL "
        "SELECT :c, :e, 0, 100000 + i, md5('r' || :e || i)::uuid, md5('r' || :e || i)::uuid, 'bulk', 'InstantMessage', "
        ":g, md5('pr' || :e || i)::uuid, 'recipient', 'container', i % 2 = 0, CASE WHEN i % 2 = 0 THEN :o ELSE :x END "
        "FROM generate_series(1, :n) i"), {"c": case, "e": ext, "g": GEN, "n": n, "o": owner, "x": other})
    return tkey


def at(y, mo, d, h=12, mi=0, s=0, zone=timezone.utc):
    return datetime(y, mo, d, h, mi, s, tzinfo=zone)


def plus(dt, **kw):
    return dt + timedelta(**kw)
