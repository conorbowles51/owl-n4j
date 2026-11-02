"""Thread documents: each conversation of a phone as searchable text (02 section 9.7).

Global search, AI chat and Workspace citations read ``evidence_document_texts``, whose key is an evidence file, so
each thread part gets one derived ``evidence_files`` row (``source_type = 'phone_text'``, no file on disk, hidden
from evidence listings). Content is one line per communication in spec 03's copy format (3.7), from the
perspective of the phone the thread came from (its owner, its saved names), in the phone's zone or UTC when the
zone is not known. Each line has a source location naming the record, so a search hit opens the record.

A thread is split only at message boundaries, past 5,000 messages or 2,000,000 characters, never by day. Parts are
regenerated when their content changes (content hash compared first; unchanged parts untouched) and removed when
the thread or the phone is gone. Corrected values (02 section 10) are the ones written.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import timezone

from sqlalchemy import text

GENERATOR_VERSION = "phone-thread-text/2"  # 2: each attachment cites its own record
SOURCE_TYPE = "phone_text"
MAX_MESSAGES = 5000
MAX_CHARS = 2_000_000
NS = uuid.UUID("5d1c7f0a-3b9e-4c55-8a7e-2f61c0d9b4a3")
FROM_ROLES = {"sender", "caller", "from"}
TO_ROLES = {"recipient", "callee", "to"}
KIND_WORDS = {"message": "message", "call": "call", "email": "email", "voicemail": "voicemail"}


def _zone(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name) if name else timezone.utc
    except Exception:  # noqa: BLE001 - an unknown zone name: UTC, as when there is none
        return timezone.utc


def when_words(instant, zone, seconds=True):
    """``Tue, Mar 14, 2023, 3:07:12 PM EDT`` (03 section 3.7)."""
    if instant is None:
        return "No time recorded"
    t = instant.astimezone(zone)
    clock = t.strftime("%I:%M:%S %p" if seconds else "%I:%M %p").lstrip("0")
    return "%s, %s %d, %d, %s %s" % (t.strftime("%a"), t.strftime("%b"), t.day, t.year, clock, t.tzname() or "UTC")


def _party_words(p, phone_label, phone_names, owner_display):
    if p["owner"]:
        who = p["name"] or owner_display
        return "Owner of %s%s" % (phone_label, ": %s" % who if who else "")
    name = phone_names.get(p["identity_key"]) or p["name"]
    number = p["display"]
    if name and number and name != number:
        return "%s (%s)" % (name, number)
    return name or number or "Unknown"


def _line(ev, parties, attachments, phone_label, phone_names, owner_display, zone):
    froms = [p for p in parties if p["role"] in FROM_ROLES]
    tos = [p for p in parties if p["role"] in TO_ROLES]
    words = lambda ps: ", ".join(_party_words(p, phone_label, phone_names, owner_display) for p in ps)  # noqa: E731
    if froms or tos:
        who = "%s -> %s" % (words(froms) or "Unknown", words(tos) or "Unknown")
    else:
        who = words(parties) or "Unknown"
    body = ev["body"] or ""
    if ev["kind"] == "call":
        bits = [b for b in (ev["call_status"], "%ss" % ev["call_duration_s"] if ev["call_duration_s"] is not None
                            else None) if b]
        body = body or ("Call" + (" (%s)" % ", ".join(bits) if bits else ""))
    if ev["subject"] and ev["kind"] == "email":
        body = "Subject: %s%s" % (ev["subject"], ("\n" + body) if body else "")
    body = body.replace("\r\n", "\n").replace("\n", "\n  ")
    head = "%s | %s | %s | %s | %s" % (when_words(ev["sort_instant"], zone), phone_label, ev["app"] or
                                       KIND_WORDS.get(ev["kind"], ev["kind"] or "record").capitalize(), who, body)
    line, spans = head, []
    for uid, title in attachments:  # each attachment is its own record and gets its own citation span
        piece = "[attachment: %s]" % title
        start = len(line) + 1
        line += " " + piece
        spans.append((uid, title, start, start + len(piece)))
    if ev["deleted_state"] and ev["deleted_state"] not in ("Intact", "intact"):
        line += " [Deleted]"
    return line, spans


def build_extraction(conn, extraction_id) -> dict:
    """Write the thread documents of one phone's current reading. Returns counts."""
    from services.phone import identities
    from services.phone.readings import phone_labels
    head = conn.execute(text(
        "SELECT e.case_id, e.device_zone, e.standing, s.generation FROM phone_extractions e JOIN "
        "phone_interpretation_state s ON s.extraction_id = e.id WHERE e.id = :e"), {"e": extraction_id}).one_or_none()
    if head is None or head.standing != "active" or not head.generation:
        return remove_extraction(conn, extraction_id)
    case_id, zone = head.case_id, _zone(head.device_zone)
    label = phone_labels(conn, case_id).get(str(extraction_id)) or "Phone"
    owner = identities.owner(conn, extraction_id)
    owner_key = (owner.get("owner_identity_keys") or [None])[0]
    displays = {r[0]: r[1] for r in conn.execute(text(
        "SELECT identity_key, value_display FROM phone_identities WHERE case_id = :c"), {"c": case_id})}
    phone_names = {r[0]: r[1] for r in conn.execute(text(
        "SELECT identity_key, name FROM pv_identity_name WHERE extraction_id = :e AND is_phone_name"),
        {"e": extraction_id})}
    owner_display = displays.get(owner_key)
    threads = {r.thread_key: r for r in conn.execute(text(
        "SELECT thread_key, app, thread_kind, title_in_record FROM pv_thread WHERE extraction_id = :e"),
        {"e": extraction_id})}
    parties = defaultdict(list)
    for r in conn.execute(text(
            "SELECT p.event_uid, p.identity_key, p.role, p.implied_role, p.is_phone_owner, p.name_in_record, "
            "p.identifier_raw FROM pv_comm_party p WHERE p.extraction_id = :e ORDER BY p.event_uid, p.participation_uid"),
            {"e": extraction_id}):
        implicit = r.role == "owner_implicit"
        parties[r.event_uid].append({
            "identity_key": owner_key if implicit else r.identity_key, "role": r.implied_role if implicit else r.role,
            "owner": bool(implicit or r.is_phone_owner), "name": r.name_in_record,
            "display": displays.get(r.identity_key) or r.identifier_raw})
    attachments = defaultdict(list)
    for parent, uid, title in conn.execute(text(
            "SELECT parent_record_uid, record_uid, coalesce(title, model_type) FROM pv_record WHERE extraction_id = :e AND "
            "model_type = 'Attachment' AND parent_record_uid IS NOT NULL ORDER BY ordinal"), {"e": extraction_id}):
        attachments[parent].append((str(uid), title))
    events = defaultdict(list)
    for r in conn.execute(text(
            "SELECT event_uid, record_uid, thread_key, kind, app, sort_instant, body, subject, call_status, "
            "call_duration_s, deleted_state FROM pv_comm_event WHERE extraction_id = :e AND thread_key IS NOT NULL "
            "ORDER BY thread_key, sort_instant NULLS LAST, record_uid"), {"e": extraction_id}):
        events[r.thread_key].append(dict(r._mapping))

    wanted, stats = set(), defaultdict(int)
    for tk, evs in events.items():
        t = threads.get(tk)
        others = sorted({_party_words(p, label, phone_names, owner_display) for ev in evs[:200]
                         for p in parties.get(ev["event_uid"], []) if not p["owner"]})[:4]
        title = (t.title_in_record if t is not None else None) or ", ".join(others) or "Conversation"
        app = (t.app if t is not None else None) or (evs[0]["app"] if evs else None) or "Messages"
        parts = [[]]
        for ev in evs:
            line, spans = _line(ev, parties.get(ev["event_uid"], []), attachments.get(ev["record_uid"], []),
                                label, phone_names, owner_display, zone)
            if parts[-1] and (len(parts[-1]) >= MAX_MESSAGES or sum(len(x[1]) + 1 for x in parts[-1]) + len(line)
                              > MAX_CHARS):
                parts.append([])
            parts[-1].append((ev, line, spans))
        for i, part in enumerate(parts, 1):
            content, locs, pos = [], [], 0
            for ev, line, spans in part:
                said = "%s %s %s, %s" % (label, app, KIND_WORDS.get(ev["kind"], "record"),
                                         when_words(ev["sort_instant"], zone, seconds=False))
                instant = (ev["sort_instant"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                           if ev["sort_instant"] else None)
                locs.append({"kind": "phone_record", "label": said,
                             "start_char": pos, "end_char": pos + len(line), "record_uid": str(ev["record_uid"]),
                             "source_ref": "rec://%s" % ev["record_uid"],
                             "event_uid": str(ev["event_uid"]), "extraction_id": str(extraction_id),
                             "field_path": "Body", "instant": instant})
                for uid, title, a, b in spans:
                    locs.append({"kind": "phone_record", "label": "%s, attachment %s" % (said, title),
                                 "start_char": pos + a, "end_char": pos + b, "record_uid": uid,
                                 "source_ref": "rec://%s" % uid, "parent_record_uid": str(ev["record_uid"]),
                                 "event_uid": str(ev["event_uid"]), "extraction_id": str(extraction_id),
                                 "field_path": "Attachment", "instant": instant})
                content.append(line)
                pos += len(line) + 1
            body = "\n".join(content)
            first, last = part[0][0], part[-1][0]
            span = "" if len(parts) == 1 else ", messages %d to %d, %s to %s" % (
                sum(len(p) for p in parts[:i - 1]) + 1, sum(len(p) for p in parts[:i]),
                when_words(first["sort_instant"], zone, seconds=False),
                when_words(last["sort_instant"], zone, seconds=False))
            name = "%s · %s · %s (part %d of %d%s)" % (label, app, title, i, len(parts), span)
            fid = uuid.uuid5(NS, "%s|%s|%d" % (extraction_id, tk, i))
            wanted.add(fid)
            stats[_write(conn, fid, case_id, name[:512], body, locs, {
                "phone_extraction_id": str(extraction_id), "thread_key": tk, "part": i, "parts": len(parts),
                "first_event_uid": str(first["event_uid"]), "last_event_uid": str(last["event_uid"]),
                "message_count": len(part), "generator_version": GENERATOR_VERSION, "generation": head.generation},
                "phone-text://%s/%s/%d" % (extraction_id, tk, i))] += 1
    stats["removed"] = _remove(conn, extraction_id, keep=wanted)
    stats["threads"] = len(events)
    return dict(stats)


def _write(conn, fid, case_id, name, body, locs, meta, path):
    data = body.encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    cur = conn.execute(text(
        "SELECT f.sha256, f.original_filename, t.processing_manifest ->> 'generator_version' FROM evidence_files f "
        "LEFT JOIN evidence_document_texts t ON t.evidence_file_id = f.id WHERE f.id = :i"), {"i": fid}).one_or_none()
    # same text, name and generator: nothing to do. A new generator rewrites even unchanged text, because what it
    # changes may be the source locations (which part of the text cites which record), not the text itself.
    if cur is not None and cur[0] == sha and cur[1] == name and cur[2] == GENERATOR_VERSION:
        return "unchanged"
    conn.execute(text(
        "INSERT INTO evidence_files (id, case_id, original_filename, stored_path, size, sha256, status, source_type, "
        "source_ref, metadata, processed_at, created_at, updated_at) VALUES (:i, :c, :n, :p, :s, :h, 'processed', "
        "'phone_text', :ref, CAST(:m AS jsonb), now(), now(), now()) ON CONFLICT (id) DO UPDATE SET "
        "original_filename = EXCLUDED.original_filename, size = EXCLUDED.size, sha256 = EXCLUDED.sha256, "
        "metadata = EXCLUDED.metadata, processed_at = now(), updated_at = now()"),
        {"i": fid, "c": case_id, "n": name, "p": path, "s": len(data), "h": sha, "ref": path,
         "m": json.dumps(meta, sort_keys=True)})
    conn.execute(text(
        "INSERT INTO evidence_document_texts (evidence_file_id, content, content_sha256, character_count, "
        "source_locations, processing_manifest, extracted_at) VALUES (:i, :b, :h, :n, CAST(:l AS jsonb), "
        "CAST(:pm AS jsonb), now()) ON CONFLICT (evidence_file_id) DO UPDATE SET content = EXCLUDED.content, "
        "content_sha256 = EXCLUDED.content_sha256, character_count = EXCLUDED.character_count, "
        "source_locations = EXCLUDED.source_locations, processing_manifest = EXCLUDED.processing_manifest, "
        "extracted_at = now()"),
        {"i": fid, "b": body, "h": sha, "n": len(body), "l": json.dumps(locs),
         "pm": json.dumps({"generator_version": GENERATOR_VERSION, "source": "phone records"})})
    return "written" if cur is None else "rewritten"


def _remove(conn, extraction_id, keep=()):
    ids = [r[0] for r in conn.execute(text(
        "SELECT id FROM evidence_files WHERE source_type = 'phone_text' AND metadata ->> 'phone_extraction_id' = :e"),
        {"e": str(extraction_id)}) if r[0] not in keep]
    if ids:
        conn.execute(text("DELETE FROM evidence_files WHERE id = ANY(:i)"), {"i": ids})
    return len(ids)


def remove_extraction(conn, extraction_id) -> dict:
    return {"removed": _remove(conn, extraction_id)}


def signature(conn, extraction_id):
    """What the documents of a phone are written from: its generation and standing, its owner and names decisions,
    its label and zone. A change regenerates the phone's threads (content hashes then decide what is rewritten)."""
    return conn.execute(text(
        "SELECT md5(concat_ws('|', e.standing, s.generation, s.decision_revision, e.device_zone, "
        "(SELECT max(a.created_at)::text FROM adjudications a WHERE a.case_id = e.case_id AND a.subject_type IN "
        "('phone_identity', 'phone_extraction')), CAST(:v AS text))) FROM phone_extractions e LEFT JOIN phone_interpretation_state s "
        "ON s.extraction_id = e.id WHERE e.id = :e"), {"e": extraction_id, "v": GENERATOR_VERSION}).scalar()


def build_stale(engine) -> dict:
    """The worker's after-pass step: rewrite the threads of every phone whose inputs changed (``texts_at`` with the
    signature in the state counts), and remove the documents of phones that left their case."""
    done = {}
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT e.id, s.counts ->> 'text_signature' FROM phone_extractions e JOIN phone_interpretation_state s ON "
            "s.extraction_id = e.id WHERE s.generation > 0")).fetchall()
        orphans = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT (f.metadata ->> 'phone_extraction_id')::uuid FROM evidence_files f WHERE f.source_type = "
            "'phone_text' AND NOT EXISTS (SELECT 1 FROM phone_extractions e WHERE e.id::text = "
            "f.metadata ->> 'phone_extraction_id')"))]
    for ext, seen in rows:
        with engine.begin() as conn:
            sig = signature(conn, ext)
            if sig == seen:
                continue
            done[str(ext)] = build_extraction(conn, ext)
            conn.execute(text(
                "UPDATE phone_interpretation_state SET texts_at = now(), counts = coalesce(counts, '{}'::jsonb) || "
                "jsonb_build_object('text_signature', CAST(:s AS text)) WHERE extraction_id = :e"), {"s": sig, "e": ext})
    for ext in orphans:
        with engine.begin() as conn:
            done[str(ext)] = remove_extraction(conn, ext)
    return done


def install():
    """Called by the sweep worker (one writer for the thread documents)."""
    from services.phone import sweep
    sweep.register_after_pass(build_stale)
