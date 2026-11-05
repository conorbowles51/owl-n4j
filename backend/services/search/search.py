"""Loupe-wide search (03 section 11): every group's exact total, its first hits, and pages of the rest.

Groups: ``messages``, ``calls``, ``emails`` (phone communications; the same filter Conversations runs, so a group's
total is the Conversations total for that text, S-4), ``people`` (phone identities and their names, and the case's
people), ``records`` (other phone records with text), ``documents`` (document texts and transcripts). Text is
matched after folding the query and the text with 02's ``fold`` (S-1, S-2); ``exact`` turns folding off. A query
that is mostly digits also finds identities whose digits contain it (S-3). Queries under 3 characters search
identifiers only (11.6). Snippets are cut from the original text, and the match inside a snippet is the original
characters, found through the folded-to-original map (S-5).

``payments`` is the case's ledger rows by description, counterparty or amount, with money totals per currency
(services/search/payments.py); each hit cites its row by ``txn://``.

``machine_text`` is text read from phone photos and audio on request (OCR and transcripts, 03 8.3), and machine
translations of messages and transcripts (05 17.5): its own group, always labelled machine-generated with the model
that made it, a translation citing its original. Media nobody asked to read is not searched, and the response says
so.
"""
from __future__ import annotations

import re

from sqlalchemy import text

from services.phone import fold as F
from services.phone import labels as L
from services.phone import streams
from services.phone import time_display as T
from services.phone.derive import IN_USE_ORDER
from services.search import document_folds

GROUPS = ("messages", "calls", "emails", "people", "records", "documents", "machine_text", "payments")
COMM_KINDS = {"messages": ["message", "chat_activity"], "calls": ["call", "voicemail"], "emails": ["email"]}
FIRST = 20
MAX_PAGE = 200
MIN_TEXT = 3
SNIPPET = 60
NOT_SEARCHED = [{"group": "media", "reason": "Photos, audio and video are searched only where someone asked on the "
                   "Media screen for their text to be read or transcribed."}]
SHORT = "Type at least 3 letters."


class SearchError(ValueError):
    pass


def _like(q):
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _digits(q):
    d = re.sub(r"\D", "", q)
    return d if len(d) >= 4 and len(d) >= 0.6 * len(re.sub(r"\s", "", q)) else None


def snippet(original, query, exact=False):
    """``{before, match, after}`` from ``original`` around the first match of ``query`` (folded the same way), or
    None. The match is the original characters (S-5)."""
    if not original:
        return None
    fq = F.fold_with_map(query, exact=exact)[0]
    if not fq:
        return None
    # folded piece by piece up to the first match: a long email is not folded whole for a snippet near its start
    folded, starts = "", []
    for piece, at_ in F.iter_fold_with_map(original, exact=exact):
        before = len(folded)
        folded += piece
        starts.extend(at_)
        at = folded.find(fq, max(0, before - len(fq) + 1))
        if at >= 0:
            s, e = starts[at], starts[at + len(fq) - 1] + 1
            return _cut(original, s, e)
    return None


def _cut(original, s, e):
    b0 = max(0, s - SNIPPET)
    a1 = min(len(original), e + SNIPPET)
    sp = re.compile(r"\s+")
    return {"before": ("…" if b0 > 0 else "") + sp.sub(" ", original[b0:s]), "match": original[s:e],
            "after": sp.sub(" ", original[e:a1]) + ("…" if a1 < len(original) else "")}


# ---- phone communications -------------------------------------------------------------------------------------------

def _comm_filter(case_id, group, q, exact, phones, start, end):
    from services.phone.filters import StreamFilter
    body = {"case_id": str(case_id), "kinds": COMM_KINDS[group], "text": {"query": q, "exact_characters": exact}}
    if phones:
        body["phones"] = phones
    if start:
        body["from_instant"] = start
    if end:
        body["to_instant"] = end
    return StreamFilter.model_validate(body)


def _comm(conn, case_id, group, q, exact, phones, start, end, offset, limit, ctx):
    f = _comm_filter(case_id, group, q, exact, phones, start, end)
    total = streams.shown_count(conn, f)
    if not total or not limit:
        return total, []
    qy, _ = streams._query(conn, f)
    qy.params.update({"lim": limit, "off": offset})
    rows = conn.execute(text(
        "WITH m AS (%s) SELECT event_uid, record_uid, extraction_id, thread_key, kind, app, sort_instant, body, subject "
        "FROM m WHERE copy_rank = 1 ORDER BY sort_instant NULLS LAST, event_uid LIMIT :lim OFFSET :off"
        % qy.matched_sql()), qy.params).fetchall()
    senders = _senders(conn, [r.event_uid for r in rows], ctx)
    zone = ctx["zone"]
    out = []
    for r in rows:
        snip = snippet(r.body, q, exact) or snippet(r.subject, q, exact)
        if snip is None:  # the match is in an attachment's name or another field of the record
            snip = snippet(_record_text(conn, r.record_uid, q, exact), q, exact) or {
                "before": "", "match": "", "after": (r.body or r.subject or "")[:2 * SNIPPET]}
        phone = ctx["phones"].get(str(r.extraction_id), "Phone")
        out.append({
            "kind": r.kind, "title": "%s %s %s" % (phone, r.app or "", r.kind or ""), "snippet": snip,
            "phone_label": phone, "time": T.format_row(r.sort_instant, zone) if r.sort_instant else None,
            "instant": T.iso(r.sort_instant), "participants": senders.get(r.event_uid, []),
            "record_uid": str(r.record_uid), "evidence_file_id": None,
            "open": {"screen": "conversations", "params": {"phone": str(r.extraction_id), "thread": r.thread_key,
                                                           "event": str(r.event_uid), "q": q,
                                                           "exact": exact}}})
    return total, out


# a record's own text and its child records' text, each read through the record_uid index (an OR of the two made
# Postgres read every phone text of every case, about 245 ms per hit on live)
RECORD_TEXT_SQL = ("SELECT t.value FROM pv_text t WHERE t.record_uid = :u AND NOT t.is_sensitive UNION ALL SELECT "
                   "t.value FROM pv_text t JOIN pv_record s ON s.record_uid = t.record_uid WHERE s.parent_record_uid = "
                   ":u AND NOT t.is_sensitive")


def _record_text(conn, record_uid, q, exact):
    fq = F.fold(q, exact=exact)
    for (v,) in conn.execute(text(RECORD_TEXT_SQL), {"u": record_uid}):
        if v and fq in F.fold(v, exact=exact):
            return v
    return None


def _senders(conn, event_uids, ctx):
    if not event_uids:
        return {}
    out = {}
    for r in conn.execute(text(
            "SELECT event_uid, extraction_id, identity_key, name_in_record, identifier_raw FROM pv_comm_party WHERE "
            "event_uid = ANY(:u) AND role IN ('sender', 'caller', 'from') ORDER BY event_uid, participation_uid"),
            {"u": event_uids}):
        lab = ctx["labels"].label(str(r.extraction_id), identity_key=r.identity_key, name_in_record=r.name_in_record,
                                  identifier_raw=r.identifier_raw)
        out.setdefault(r.event_uid, []).append(lab)
    return out


# ---- people -----------------------------------------------------------------------------------------------------------

def _people(conn, case_id, q, exact, short, offset, limit):
    fq = F.fold(q, exact=exact)
    digits = _digits(q)
    names = {}
    for key, name in conn.execute(text(
            "SELECT DISTINCT identity_key, name FROM pv_identity_name WHERE case_id = :c"), {"c": case_id}):
        names.setdefault(key, []).append(name)
    found = []
    for r in conn.execute(text(
            "SELECT identity_key, kind, value_display, value_normalised, sighting_count, person_id FROM pv_identity "
            "WHERE case_id = :c ORDER BY identity_key"), {"c": case_id}):
        own = names.get(r.identity_key, [])
        if short:
            hit = q.strip().lower() in (r.value_normalised.lower(), r.value_display.lower())
        else:
            hit = any(fq in F.fold(v, exact=exact) for v in [r.value_display, *own] if v)
        if not hit and digits:
            hit = digits in re.sub(r"\D", "", r.value_normalised or "")
        if hit:
            shown = sorted(own, key=lambda n: (F.fold(n), n))
            found.append({"kind": "identity", "title": shown[0] if shown else r.value_display,
                          "snippet": {"before": "", "match": r.value_display, "after": ""},
                          "identity_key": r.identity_key, "names": shown[:5], "sightings": int(r.sighting_count),
                          "record_uid": None, "evidence_file_id": None,
                          "open": {"screen": "people", "params": {"people": r.identity_key}}})
    if not short:
        for pid, name in conn.execute(text(
                "SELECT id, display_name FROM case_profiles WHERE case_id = :c AND profile_type = 'person' "
                "ORDER BY display_name, id"), {"c": case_id}):
            if fq in F.fold(name, exact=exact):
                found.append({"kind": "person", "title": name, "snippet": snippet(name, q, exact),
                              "person_id": str(pid), "record_uid": None, "evidence_file_id": None,
                              "open": {"screen": "dossier", "params": {"id": str(pid)}}})
    found.sort(key=lambda h: (F.fold(h["title"]), h["title"], h.get("identity_key") or h.get("person_id") or ""))
    return len(found), found[offset:offset + limit]


# ---- other phone records ------------------------------------------------------------------------------------------------

def _records_sql(exact):
    cond = "position(:q in lower(t.value)) > 0" if exact else "t.value_folded LIKE :like"
    # sensitive values (passwords, cookies, card numbers, key-value pairs) are never searched (05 section 3.8)
    return ("FROM pv_text t JOIN pv_record r ON r.record_uid = t.record_uid WHERE t.case_id = :c AND %s "
            "AND NOT t.is_sensitive "
            "AND (CAST(:p AS uuid[]) IS NULL OR t.extraction_id = ANY(CAST(:p AS uuid[]))) "
            "AND NOT EXISTS (SELECT 1 FROM pv_comm_event e WHERE e.record_uid = t.record_uid OR "
            "e.record_uid = r.parent_record_uid OR e.record_uid = r.root_record_uid)" % cond)


def _records(conn, case_id, q, exact, phones, offset, limit, ctx):
    p = {"c": case_id, "q": F.fold(q, exact=True), "like": _like(F.fold(q)), "p": phones or None}
    total = int(conn.execute(text("SELECT count(DISTINCT t.record_uid) " + _records_sql(exact)), p).scalar() or 0)
    if not total or not limit:
        return total, []
    p.update({"lim": limit, "off": offset})
    rows = conn.execute(text(
        "SELECT DISTINCT ON (r.first_instant, t.record_uid) t.record_uid, t.extraction_id, r.model_type, "
        "r.first_instant, t.value " + _records_sql(exact) + " ORDER BY r.first_instant NULLS LAST, t.record_uid, "
        "t.field_path LIMIT :lim OFFSET :off"), p).fetchall()
    out = []
    for r in rows:
        phone = ctx["phones"].get(str(r.extraction_id), "Phone")
        out.append({"kind": "record", "title": "%s %s" % (phone, r.model_type), "phone_label": phone,
                    "snippet": snippet(r.value, q, exact) or {"before": "", "match": "", "after": r.value[:120]},
                    "time": T.format_row(r.first_instant, ctx["zone"]) if r.first_instant else None,
                    "instant": T.iso(r.first_instant), "record_uid": str(r.record_uid), "evidence_file_id": None,
                    "open": {"screen": "record", "params": {"record_uid": str(r.record_uid)}}})
    return total, out


# ---- documents ------------------------------------------------------------------------------------------------------------

DOC_FROM = ("FROM evidence_document_texts t JOIN evidence_files f ON f.id = t.evidence_file_id "
            "LEFT JOIN evidence_text_folds x ON x.evidence_file_id = t.evidence_file_id AND x.content_sha256 = "
            "t.content_sha256 AND x.fold_version = :v "
            "WHERE f.case_id = :c AND f.deleted_at IS NULL AND f.source_type IS DISTINCT FROM 'phone_text' "
            "AND t.content IS NOT NULL ")


def _documents(conn, case_id, q, exact, offset, limit):
    """Folded documents match on their folded text; a document whose fold is not ready yet matches as typed
    (case-insensitive), and the count of those is returned so the screen can say so."""
    fq, fq_exact = F.fold_with_map(q)[0], F.fold(q, exact=True)
    if exact:
        cond = "position(:qe in lower(t.content)) > 0"
    else:
        cond = "((x.evidence_file_id IS NOT NULL AND x.content_folded LIKE :like) OR (x.evidence_file_id IS NULL AND " \
               "position(:qe in lower(t.content)) > 0))"
    p = {"c": case_id, "v": document_folds.FOLD_VERSION, "like": _like(fq), "qe": fq_exact}
    counts = conn.execute(text(
        "SELECT count(*) AS n, count(*) FILTER (WHERE x.evidence_file_id IS NULL) AS unfolded " + DOC_FROM +
        "AND " + cond), p).one()
    unprepared = int(conn.execute(text("SELECT count(*) " + DOC_FROM + "AND x.evidence_file_id IS NULL"), p).scalar()
                     or 0)
    total = int(counts.n)
    if not total or not limit:
        return total, [], unprepared
    p.update({"lim": limit, "off": offset})
    rows = conn.execute(text(
        "SELECT f.id, f.original_filename, t.content, t.source_locations, x.content_folded, x.fold_map " + DOC_FROM +
        "AND " + cond + " ORDER BY lower(f.original_filename), f.id LIMIT :lim OFFSET :off"), p).fetchall()
    out = []
    for r in rows:
        snip, page = None, None
        if not exact and r.content_folded is not None and fq:
            at = r.content_folded.find(fq)
            if at >= 0:
                s, e = F.original_span(r.fold_map, at, at + len(fq))
                snip, page = _cut(r.content, s, e), _page(r.source_locations, s)
        if snip is None:
            snip = snippet(r.content, q, exact) or {"before": "", "match": "", "after": r.content[:120]}
            at = r.content.lower().find(fq_exact) if exact else -1
            page = _page(r.source_locations, at) if at >= 0 else None
        out.append({"kind": "document", "title": r.original_filename, "snippet": snip, "page": page,
                    "record_uid": None, "evidence_file_id": str(r.id),
                    "open": {"screen": "document", "params": {"evidence_file_id": str(r.id), "page": page}}})
    return total, out, unprepared


def _page(locations, at):
    best = None
    for loc in locations or []:
        s, e = int(loc.get("start_char", 0)), int(loc.get("end_char", 0))
        if s <= at < e and loc.get("page_number") is not None and (best is None or e - s < best[0]):
            best = (e - s, loc.get("page_number"))
    return best[1] if best else None


# ---- machine-generated text (OCR and transcripts) -----------------------------------------------------------------

def _machine_sql(exact):
    # a person's correction replaces the machine text in search (07 4.6); the machine text is not searched then
    cond = ("position(:qe in lower(coalesce(d.corrected_text, d.text))) > 0" if exact
            else "coalesce(d.corrected_text_folded, d.text_folded) LIKE :like")
    return ("FROM (SELECT DISTINCT ON (d.file_uid, d.kind) d.* FROM phone_derived_texts d WHERE d.case_id = :c AND "
            "d.state = 'done' " + IN_USE_ORDER + ") d JOIN pv_file f ON f.file_uid = "
            "d.file_uid AND f.case_id = :c WHERE (CAST(:p AS uuid[]) IS NULL OR f.extraction_id = ANY(CAST(:p AS "
            "uuid[]))) AND " + cond)


def _translation_sql(exact):
    # the latest finished translation of each source, and only one of the text in effect now: a translation of a
    # text corrected since is not searched (05 17.5; only the corrected value is searched)
    cond = "position(:qe in lower(t.text)) > 0" if exact else "t.text_folded LIKE :like"
    return ("FROM (SELECT DISTINCT ON (t.source_type, t.source_key) t.* FROM phone_translations t WHERE t.case_id = :c "
            "AND t.state = 'done' ORDER BY t.source_type, t.source_key, t.finished_at DESC, t.id) t "
            "LEFT JOIN pv_comm_event ev ON t.source_type = 'message' AND ev.event_uid = t.source_key AND "
            "ev.case_id = :c LEFT JOIN phone_derived_texts dt ON t.source_type = 'derived_text' AND dt.id = t.source_key "
            "AND dt.case_id = :c "
            # only a translation of the reading in use for its file and kind (a person's latest, else the latest
            # finished; the same reading the PDF prints): a translation of a reading displaced since is not searched
            "AND dt.id IN (SELECT DISTINCT ON (d.file_uid, d.kind) d.id FROM phone_derived_texts d WHERE "
            "d.case_id = :c AND d.state = 'done' " + IN_USE_ORDER + ") "
            "LEFT JOIN pv_file tf ON tf.file_uid = dt.file_uid AND tf.case_id = :c "
            "WHERE t.outcome = 'translated' AND (ev.event_uid IS NOT NULL OR tf.file_uid IS NOT NULL) AND "
            "t.source_sha256 = encode(sha256(convert_to(coalesce(ev.body, dt.corrected_text, dt.text, ''), 'UTF8')), "
            "'hex') AND (CAST(:p AS uuid[]) IS NULL OR coalesce(ev.extraction_id, tf.extraction_id) = ANY(CAST(:p AS "
            "uuid[]))) AND " + cond)


def _machine(conn, case_id, q, exact, phones, offset, limit, ctx):
    """Machine texts (OCR, transcripts) and machine translations (05 17.5) in one group, newest first. Each item
    says which it is; a translation cites its original."""
    p = {"c": case_id, "qe": F.fold(q, exact=True), "like": _like(F.fold(q)), "p": phones or None}
    total = int(conn.execute(text("SELECT (SELECT count(*) " + _machine_sql(exact) + ") + (SELECT count(*) "
                                  + _translation_sql(exact) + ")"), p).scalar() or 0)
    if not total or not limit:
        return total, []
    p.update({"lim": limit, "off": offset})
    page = conn.execute(text(
        "SELECT * FROM (SELECT 'derived' AS src, d.id, d.finished_at " + _machine_sql(exact) + " UNION ALL "
        "SELECT 'translation' AS src, t.id, t.finished_at " + _translation_sql(exact) + ") u "
        "ORDER BY u.finished_at DESC, u.src, u.id LIMIT :lim OFFSET :off"), p).fetchall()
    derived = _derived_items(conn, case_id, q, exact, [r.id for r in page if r.src == "derived"], ctx)
    translated = _translation_items(conn, case_id, q, exact, [r.id for r in page if r.src == "translation"], ctx)
    return total, [derived[r.id] if r.src == "derived" else translated[r.id] for r in page]


def _derived_items(conn, case_id, q, exact, ids, ctx):
    from services.phone import derive
    if not ids:
        return {}
    out = {}
    for r in conn.execute(text(
            "SELECT d.id, d.file_uid, d.kind, coalesce(d.corrected_text, d.text) AS text, d.model, d.model_version, "
            "d.finished_at, d.state, d.corrected_at, d.corrected_by_name, d.correction_reason, d.confirmed_at, "
            "d.confirmed_by_name, f.extraction_id, f.local_path FROM phone_derived_texts d JOIN pv_file f ON "
            "f.file_uid = d.file_uid AND f.case_id = :c WHERE d.id = ANY(:i)"), {"c": case_id, "i": ids}):
        phone = ctx["phones"].get(str(r.extraction_id), "Phone")
        name = (r.local_path or "").replace("\\", "/").rsplit("/", 1)[-1] or "File not named in the report"
        out[r.id] = {"kind": "machine_text", "title": "%s %s: %s" % (
                         phone, "text read from" if r.kind == "ocr" else "transcript of", name),
                     "phone_label": phone, "machine_generated": r.corrected_at is None,
                     "origin": derive.origin(dict(r._mapping)),
                     "label": derive.label(r.model, r.model_version, r.finished_at),
                     "snippet": snippet(r.text, q, exact) or {"before": "", "match": "", "after": (r.text or "")[:120]},
                     "record_uid": None, "evidence_file_id": None, "file_uid": str(r.file_uid),
                     "extraction_id": str(r.extraction_id),
                     "open": {"screen": "media", "params": {"file_uid": str(r.file_uid),
                                                            "extraction_id": str(r.extraction_id)}}}
    return out


ORIGINAL_CHARS = 200


def _translation_items(conn, case_id, q, exact, ids, ctx):
    from services.phone import translate
    if not ids:
        return {}
    out = {}
    for r in conn.execute(text(
            "SELECT t.id, t.source_type, t.source_key, t.text, t.model, t.model_version, t.detected_language_name, "
            "ev.body, ev.record_uid, ev.thread_key, ev.extraction_id AS ev_ext, ev.app, dt.kind AS dkind, "
            "coalesce(dt.corrected_text, dt.text) AS dtext, dt.file_uid, tf.extraction_id AS f_ext, tf.local_path "
            "FROM phone_translations t LEFT JOIN pv_comm_event ev ON t.source_type = 'message' AND ev.event_uid = "
            "t.source_key AND ev.case_id = :c LEFT JOIN phone_derived_texts dt ON t.source_type = 'derived_text' AND "
            "dt.id = t.source_key LEFT JOIN pv_file tf ON tf.file_uid = dt.file_uid AND tf.case_id = :c "
            "WHERE t.id = ANY(:i)"), {"c": case_id, "i": ids}):
        ext = str(r.ev_ext or r.f_ext)
        phone = ctx["phones"].get(ext, "Phone")
        original = r.body if r.source_type == "message" else r.dtext
        if r.source_type == "message":
            what = "message"
            where = {"screen": "conversations", "params": {"phone": ext, "thread": r.thread_key,
                                                           "event": str(r.source_key), "q": q, "exact": exact}}
        else:
            name = (r.local_path or "").replace("\\", "/").rsplit("/", 1)[-1] or "File not named in the report"
            what = "%s %s" % ("transcript of" if r.dkind == "transcript" else "text read from", name)
            where = {"screen": "media", "params": {"file_uid": str(r.file_uid), "extraction_id": ext}}
        out[r.id] = {"kind": "machine_translation", "title": "%s machine translation of a %s" % (phone, what)
                     if r.source_type == "message" else "%s machine translation of the %s" % (phone, what),
                     "phone_label": phone, "machine_generated": True,
                     "label": translate.label(r.model, r.model_version),
                     "translated_from": r.detected_language_name,
                     "original": {"text": (original or "")[:ORIGINAL_CHARS],
                                  "clipped": len(original or "") > ORIGINAL_CHARS, "chars": len(original or "")},
                     "snippet": snippet(r.text, q, exact) or {"before": "", "match": "", "after": (r.text or "")[:120]},
                     "record_uid": str(r.record_uid) if r.record_uid else None, "evidence_file_id": None,
                     "extraction_id": ext, "translation_id": str(r.id), "open": where}
        if r.file_uid:
            out[r.id]["file_uid"] = str(r.file_uid)
    return out


# ---- entry points -----------------------------------------------------------------------------------------------------------

def _context(conn, case_id):
    from services.phone import readings
    return {"phones": readings.phone_labels(conn, case_id), "zone": streams.case_zone(conn, case_id)["name"],
            "labels": L.LabelContext(conn, case_id, "phone")}


def _group(conn, case_id, group, q, exact, phones, start, end, offset, limit, ctx, short):
    unprepared = None
    if group in COMM_KINDS:
        total, items = (0, []) if short else _comm(conn, case_id, group, q, exact, phones, start, end, offset, limit,
                                                   ctx)
    elif group == "people":
        total, items = _people(conn, case_id, q, exact, short, offset, limit)
    elif group == "records":
        total, items = (0, []) if short else _records(conn, case_id, q, exact, phones, offset, limit, ctx)
    elif group == "machine_text":
        total, items = (0, []) if short else _machine(conn, case_id, q, exact, phones, offset, limit, ctx)
    elif group == "documents":
        total, items, unprepared = (0, [], None) if short else _documents(conn, case_id, q, exact, offset, limit)
    elif group == "payments":
        from services.search.payments import NOT_SEARCHED as PAYMENTS_NOT_SEARCHED, search_payments
        total, items, totals = (0, [], None) if short else search_payments(conn, case_id, q, offset=offset,
                                                                              limit=limit)
        out = {"group": group, "total": total, "items": items, "totals": totals, "searched": PAYMENTS_NOT_SEARCHED,
               "next_cursor": str(offset + len(items)) if offset + len(items) < total else None}
        return out
    else:
        raise SearchError("No search group called %s." % group)
    out = {"group": group, "total": total, "items": items,
           "next_cursor": str(offset + len(items)) if offset + len(items) < total else None}
    if unprepared:
        out["note"] = ("%s %s still being prepared for this search; %s matched as typed, without folding."
                       % ("{:,}".format(unprepared), "document is" if unprepared == 1 else "documents are",
                          "it is" if unprepared == 1 else "they are"))
    return out


def search(conn, case_id, q, *, exact=False, groups=GROUPS, phones=None, start=None, end=None) -> dict:
    q = (q or "").strip()
    if not q:
        raise SearchError("Type something to search for.")
    short = len(F.fold(q, exact=exact).replace(" ", "")) < MIN_TEXT
    ctx = _context(conn, case_id)
    out = [_group(conn, case_id, g, q, exact, phones, start, end, 0, FIRST, ctx, short) for g in groups]
    for g in out:  # the Enter rule's order (11.4): exact name first, then the group whose top hit is newest text
        g["score"] = _score(g, q, exact)
    limits = coverage_limits(conn, case_id, phones)
    return {"query": q, "folded_query": F.fold(q, exact=exact), "exact": exact, "complete": not limits,
            "limits": limits, "short": SHORT if short else None, "groups": out,
            "not_searched": NOT_SEARCHED + unread_files(conn, case_id)}


def coverage_limits(conn, case_id, phones=None) -> list:
    """The phones in scope still being read or only partly read: the same words Conversations shows (3.8, 4.2), so a
    search total is never presented as whole while a phone it counts from is incomplete."""
    from services.phone.filters import StreamFilter
    return streams.limits_for(conn, StreamFilter(case_id=str(case_id), phones=[str(p) for p in phones or []]))


def unread_files(conn, case_id) -> list:
    """Evidence files of the case with no text read (still waiting, failed, or not documents): not searched, said
    with their count. Internal copies and phone thread documents are not evidence listings and are left out."""
    from sqlalchemy import func, select

    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
    from services.financial.source_lineage import visible_evidence_condition
    n = conn.execute(select(func.count()).select_from(EvidenceFile).outerjoin(
        EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id).where(
        EvidenceFile.case_id == case_id, visible_evidence_condition(),
        EvidenceDocumentText.content.is_(None))).scalar() or 0
    if not n:
        return []
    return [{"group": "unread_files", "reason": "%s %s no text read yet (still waiting, failed, or not a document) "
             "and %s not searched." % ("{:,}".format(n), "file has" if n == 1 else "files have",
                                       "is" if n == 1 else "are")}]


def group_page(conn, case_id, q, group, *, cursor=None, limit=MAX_PAGE, exact=False, phones=None, start=None,
               end=None) -> dict:
    q = (q or "").strip()
    if not q:
        raise SearchError("Type something to search for.")
    if not 1 <= limit <= MAX_PAGE:
        raise SearchError("A page holds 1 to 200 hits.")
    offset = int(cursor or 0)
    short = len(F.fold(q, exact=exact).replace(" ", "")) < MIN_TEXT
    limits = coverage_limits(conn, case_id, phones)
    return dict(_group(conn, case_id, group, q, exact, phones, start, end, offset, limit, _context(conn, case_id),
                       short), query=q, complete=not limits, limits=limits)


def _score(g, q, exact):
    if not g["items"]:
        return 0.0
    top = g["items"][0]
    fq = F.fold(q, exact=exact)
    if g["group"] == "people" and F.fold(top["title"], exact=exact) == fq:
        return 3.0
    base = {"messages": 2.0, "people": 1.5, "emails": 1.4, "calls": 1.2, "documents": 1.1, "records": 1.0, "machine_text": 0.9,
            "payments": 1.05}
    return base.get(g["group"], 1.0)


def freeze_group(db, user, case_id, q, group, *, exact=False, phones=None) -> dict:
    """A whole search group as one ``phone_selection`` (07 J-5, section 6.1): the message, call and email groups by the
    stream filter they count with, so every copy is held; the other phone groups by the records their hits name. The
    group's total and any hit with no phone record behind it come back as ``group_total`` and ``left_out``."""
    from services.phone import selections
    from services.phone.filters import StreamFilter
    conn = db.connection()
    if group in COMM_KINDS:
        f = _comm_filter(case_id, group, q, exact, phones or [], None, None)
        total = group_page(conn, case_id, q, group, limit=1, exact=exact, phones=phones)["total"]
        out = selections.freeze(db, f, user, 'Every %s matching "%s"' % (group[:-1], q))
        return dict(out, group_total=int(total), left_out=max(0, int(total) - int(out["event_count"])))
    uids, cursor, total = [], None, 0
    while True:
        page = group_page(conn, case_id, q, group, cursor=cursor, limit=MAX_PAGE, exact=exact, phones=phones)
        total = int(page["total"])
        uids += [i["record_uid"] for i in page["items"] if i.get("record_uid")]
        cursor = page["next_cursor"]
        if not cursor:
            break
    f = StreamFilter.model_validate({"case_id": str(case_id), "text": {"query": q, "exact_characters": exact},
                                     **({"phones": phones} if phones else {})})
    out = selections.freeze_records(db, f, uids, user, 'Every hit in %s matching "%s"' % (group.replace("_", " "), q))
    return dict(out, group_total=total, left_out=total - int(out["record_count"]))
