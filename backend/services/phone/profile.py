"""Phone summary, the extraction profile (03 section 7; 07 J-2, J-11, J-15).

``profile`` returns, for one phone of a case, everything the Phone summary shows. Every number is a count over the
read views (``pv_*``) or 01's capture tables at the phone's current reading; nothing is typed in and nothing is
estimated (P-1). Each count carries the address of the screen that lists what it counts, so the page's numbers and
the lists they open agree.

The verdict follows the reconciliation result and the reading state (P-7): ``Read in full`` only when the phone is
read and every document reconciled exactly; ``Partly read`` when capture was incomplete or a document's counts
differ; ``Still reading`` while capture or interpretation runs; ``Failed`` when either failed.
"""
from __future__ import annotations

from urllib.parse import quote

from sqlalchemy import text

from services.phone import labels as L
from services.phone import streams
from services.phone import time_display as T

SELECTION_MEANING = {
    "IsSelectiveExtraction": ("Selective extraction", "The examiner chose which data to extract. Absence of a type may "
                              "mean it was not chosen."),
    "IsPartialData": ("Partial data", "The report says it holds only part of the phone's data."),
    "IsStoppedByUser": ("Stopped by the examiner", "The extraction was stopped before it finished."),
    "IsTriageExtraction": ("Triage extraction", "A quick extraction of selected data, made to decide what to look at "
                           "first."),
}
LEVEL_WORDS = {"reviewed": "Interpreted", "applied_unconfirmed": "Mapped by the system, not yet confirmed",
               "generic": "Read generically", "captured_only": "Held, not yet read"}
SIGNALS = (("messages", "pv_comm_event", "sort_instant", "kind = 'message'"),
           ("calls", "pv_comm_event", "sort_instant", "kind = 'call'"),
           ("emails", "pv_comm_event", "sort_instant", "kind = 'email'"),
           ("locations", "pv_location_point", "instant", "true"),
           ("timeline entries", "pv_timeline_entry", "instant", "true"))
TOP_PEOPLE = 10


class NotFound(LookupError):
    pass


def _verdict_word(x) -> str:
    if x.state == "failed":
        return "Failed"
    if x.state in ("capturing", "interpreting", "building_views"):
        return "Still reading"
    if x.state == "partial" or x.reconciliation_state == "failed":
        return "Partly read"
    if x.state == "replaced":
        return "Replaced"
    if x.reconciliation_state != "exact":  # no reconciliation on record: read, but not shown to be whole (P-7)
        return "Read, counts not checked"
    return "Read in full"


def _flag_words(value):
    if value is None:
        return "not stated"
    if isinstance(value, list):
        return "the report's sections disagree: " + ", ".join("not stated" if v is None else str(v) for v in value)
    return str(value)


HELD_SHOWN = 500
MEASURE_WORDS = {"elements": "elements", "attributes": "attributes", "attr_hash": "attribute values",
                 "texts": "texts", "text_chars": "characters of text", "text_hash": "text values",
                 "bad_tails": "pieces of text between elements", "rows_unreached": "stored rows no element reaches"}


def _path_words(path):
    return " / ".join(str(path or "").split("/")[-3:])


def held_view(conn, extraction_id) -> list:
    """Documents held by the check (01 section 8.4, 07 J-1), each with every difference up to ``HELD_SHOWN`` and the
    true total, and the acceptance on record if a person accepted them."""
    from services.phone import corrections
    out = []
    for h in corrections.held_reconciliations(conn, extraction_id):
        diffs = h["differences"]
        out.append({"document_index": h["document_index"], "document": h["document"],
                    "difference_count": h["difference_count"], "accepted": h["accepted"],
                    "differences": [{"where": _path_words(d.get("path")), "measure": d.get("measure"),
                                     "what": MEASURE_WORDS.get(d.get("measure"), d.get("measure")),
                                     "attribute": d.get("attribute"), "stated": d.get("source"),
                                     "read": d.get("captured")} for d in diffs[:HELD_SHOWN]],
                    "shown": min(len(diffs), HELD_SHOWN)})
    return out


def held_sentence(held) -> str:
    """07 J-1: "Held: the report lists 1,204 call records; 1,198 were read. See which." The first difference is
    named; the rest are counted."""
    open_ = [h for h in held if h["accepted"] is None]
    total = sum(h["difference_count"] for h in open_)
    first = next((d for h in open_ for d in h["differences"]), None)
    if first is None:
        return "Held: the report does not match its own counts."
    words = "Held: the report lists %s %s at %s; %s %s read." % (
        "{:,}".format(int(first["stated"] or 0)), first["what"], first["where"], "{:,}".format(int(first["read"] or 0)),
        "was" if int(first["read"] or 0) == 1 else "were")
    if total > 1:
        words += " %s more %s." % ("{:,}".format(total - 1), "difference" if total == 2 else "differences")
    return words


def profile(conn, case_id, extraction_id) -> dict:
    from services.phone import coverage, identities, records, readings
    ext = str(extraction_id)
    x = conn.execute(text("SELECT * FROM pv_extraction WHERE case_id = :c AND extraction_id::text = :e"),
                     {"c": case_id, "e": ext}).first()
    if x is None:
        raise NotFound(ext)
    phone = next(p for p in records.phones(conn, case_id) if p["extraction_id"] == ext)
    zone = streams.case_zone(conn, case_id)
    zname = zone["name"]
    zone["display_name"] = T.zone_name(zname)
    base = "/cases/%s" % case_id
    conv = "%s/phones/%s/records/conversations" % (base, ext)
    gen = conn.execute(text("SELECT generation FROM phone_interpretation_state WHERE extraction_id::text = :e"),
                       {"e": ext}).scalar()

    # ---- data periods and the verdict --------------------------------------------------------------------------
    periods = []
    for name, view, col, cond in SIGNALS:
        r = conn.execute(text("SELECT count(*) AS n, count(%s) AS dated, min(%s) AS f, max(%s) AS l FROM %s WHERE "
                              "extraction_id::text = :e AND %s" % (col, col, col, view, cond)), {"e": ext}).one()
        periods.append({"signal": name, "records": int(r.n), "dated": int(r.dated), "first_instant": T.iso(r.f),
                        "last_instant": T.iso(r.l),
                        "first_words": T.format_full(r.f, zname) if r.f else None,
                        "last_words": T.format_full(r.l, zname) if r.l else None})
    span = conn.execute(text("SELECT min(first_instant), max(first_instant) FROM phone_record_summaries WHERE "
                             "extraction_id::text = :e AND generation = :g AND has_time"), {"e": ext, "g": gen}).one()
    from services.phone.filters import StreamFilter

    def listed(**kw):  # the count the linked Conversations list shows: same filter, copies collapsed
        return streams.shown_count(conn, StreamFilter.model_validate({"case_id": str(case_id), "phones": [ext], **kw}))
    app_names = [a for (a,) in conn.execute(text(
        "SELECT DISTINCT app FROM pv_comm_event WHERE extraction_id::text = :e AND app IS NOT NULL"), {"e": ext})]
    apps = sorted(({"app": a, "events": listed(apps=[a])} for a in app_names), key=lambda r: (-r["events"], r["app"]))
    word = _verdict_word(x)
    # 01's stored count; the captured records counted when it is not stored (live 2 November: stored on all 6
    # active phones and equal to the count of phone_records on each).
    records_total = int(x.record_count) if x.record_count is not None else int(conn.execute(text(
        "SELECT count(*) FROM phone_records WHERE extraction_id::text = :e"), {"e": ext}).scalar() or 0)

    def day(v):
        return T.format_day_header(T.day_of(v, zname)) if v else None

    # ---- owner, zone and what needs a decision -----------------------------------------------------------------
    own = identities.owner(conn, extraction_id)
    shown = {r[0]: r[1] for r in conn.execute(text(
        "SELECT identity_key, value_display FROM phone_identities WHERE case_id = :c AND identity_key = ANY(:k)"),
        {"c": case_id, "k": [c["identity_key"] for c in own["candidates"] if c["identity_key"]]})}
    candidates = [{"identity_key": c["identity_key"], "text": shown.get(c["identity_key"]) or c["identity_key"],
                   "tier": c["tier"], "occurrences": int(c["occurrences"] or 0), "basis": c["basis"]}
                  for c in own["candidates"] if c["candidate_kind"] == "number" and c["identity_key"]]
    owner_label = phone["owner"]
    decided = own.get("decided")
    basis = own.get("owner_basis") or (own.get("computed") or {}).get("basis")
    owner_missing = not (owner_label and owner_label.get("identity_key")) and not decided
    if decided:
        owner_words = "Set by a person%s" % ((" on %s" % day(decided.get("at"))) if decided.get("at") else "")
    elif basis in (None, "unidentified"):
        owner_words = "No owner number was found."
    elif "device" in str(basis) or str(basis).startswith("tier1") or (own.get("computed") or {}).get("tier") == 1:
        owner_words = "Read from the device information in the report"
    else:
        owner_words = "Worked out from messages the phone sent"
    open_readings = conn.execute(text(
        "SELECT count(*) FROM phone_mapping_judgements j JOIN phone_interpretation_state s ON s.extraction_id = "
        "j.extraction_id AND s.generation = j.generation WHERE j.case_id = :c AND j.extraction_id::text = :e AND "
        "j.status = 'open' AND j.records_touched > 0"), {"c": case_id, "e": ext}).scalar() or 0
    needs = []
    if owner_missing:
        needs.append({"kind": "owner", "words": "No owner number was found. Person-level views stay off until an owner "
                      "is set. Set the owner.", "link": "%s/phones/%s#set-owner" % (base, ext)})
    if not x.device_zone:
        needs.append({"kind": "zone", "words": "This phone did not record its time zone. Times show in the case zone "
                      "(%s)." % zone["display_name"], "link": "%s/settings" % base})
    held = held_view(conn, extraction_id) if x.reconciliation_state == "failed" else []
    if any(h["accepted"] is None for h in held):
        needs.append({"kind": "reconciliation", "words": held_sentence(held), "link": None})
    if open_readings:
        needs.append({"kind": "readings", "words": "%s %s of how the system read this phone %s a person's check."
                      % ("{:,}".format(open_readings), "reading" if open_readings == 1 else "readings",
                         "needs" if open_readings == 1 else "need"), "link": "%s/phone-review" % base})

    n_needs = len(needs)
    sentence = "%s: %s records" % (word, "{:,}".format(records_total))
    if span[0] and span[1]:
        sentence += ", %s to %s" % (day(span[0]), day(span[1]))
    sentence += ", %d %s." % (len(apps), "app" if len(apps) == 1 else "apps")
    sentence += (" Nothing needs a decision." if not n_needs else " 1 thing needs a decision." if n_needs == 1
                 else " %s things need a decision." % "{:,}".format(n_needs))

    # ---- report, selection, completeness ------------------------------------------------------------------------
    sel = coverage.selection(conn, extraction_id)
    selection = [{"flag": k, "name": SELECTION_MEANING[k][0], "verbatim": _flag_words(sel.get(k)),
                  "meaning": SELECTION_MEANING[k][1] if sel.get(k) not in (None, "False", "false") else None}
                 for k in coverage.SELECTION_FLAGS]
    recon = []
    for r in conn.execute(text(
            "SELECT DISTINCT ON (document_index) document_index, result, source_totals, captured_totals, "
            "difference_count FROM phone_reconciliations WHERE extraction_id::text = :e ORDER BY document_index, "
            "ran_at DESC"), {"e": ext}):
        src, got = r.source_totals or {}, r.captured_totals or {}
        recon.append({"document_index": r.document_index, "result": r.result, "differences": int(r.difference_count or 0),
                      "stated_vs_read": [{"what": k, "stated": src.get(k), "read": got.get(k)}
                                         for k in sorted(set(src) | set(got)) if src.get(k) != got.get(k)]})

    # ---- files, deleted, coverage --------------------------------------------------------------------------------
    files_total = conn.execute(text("SELECT count(*) FROM pv_file WHERE extraction_id::text = :e"), {"e": ext}).scalar()
    by_cat = {c or "not recorded": int(n) for c, n in conn.execute(text(
        "SELECT category, count(*) FROM pv_file WHERE extraction_id::text = :e GROUP BY 1 ORDER BY 2 DESC"), {"e": ext})}
    verification = {v or "not checked": int(n) for v, n in conn.execute(text(
        "SELECT verification, count(*) FROM pv_file WHERE extraction_id::text = :e GROUP BY 1 ORDER BY 2 DESC"),
        {"e": ext})}
    deleted = []
    for r in conn.execute(text(
            "SELECT model_type, count(*) FILTER (WHERE deleted_state = 'Intact') AS intact, count(*) FILTER (WHERE "
            "deleted_state = 'Deleted') AS deleted, count(*) FILTER (WHERE deleted_state = 'Trash') AS trash, count(*) "
            "FILTER (WHERE deleted_state IS NULL OR deleted_state NOT IN ('Intact', 'Deleted', 'Trash')) AS unknown "
            "FROM phone_record_summaries WHERE extraction_id::text = :e AND generation = :g AND is_top_level GROUP BY 1 "
            "HAVING count(*) FILTER (WHERE deleted_state IN ('Deleted', 'Trash')) > 0 ORDER BY 3 DESC, 1"),
            {"e": ext, "g": gen}):
        deleted.append({"model_type": r.model_type, "intact": int(r.intact), "deleted": int(r.deleted),
                        "trash": int(r.trash), "unknown": int(r.unknown)})
    comm_deleted = listed(deleted_states=["Deleted", "Trash"])
    cov = {}
    for r in conn.execute(text(
            "SELECT model_type, interpretation_level, count(*) AS n FROM phone_record_summaries WHERE "
            "extraction_id::text = :e AND generation = :g AND is_top_level GROUP BY 1, 2"), {"e": ext, "g": gen}):
        t = cov.setdefault(r.model_type, {"model_type": r.model_type, "records": 0, "levels": {}})
        t["records"] += int(r.n)
        t["levels"][r.interpretation_level or "captured_only"] = int(r.n)
    coverage_rows = []
    for t in sorted(cov.values(), key=lambda t: (-t["records"], t["model_type"])):
        main = max(t["levels"].items(), key=lambda kv: kv[1])[0]
        coverage_rows.append({**t, "level": main, "level_words": LEVEL_WORDS.get(main, main)})

    # ---- months, people, continue -------------------------------------------------------------------------------
    months = {}
    for m, k, n in conn.execute(text(
            "SELECT to_char(sort_instant AT TIME ZONE :z, 'YYYY-MM') AS m, kind, count(*) FROM pv_comm_event WHERE "
            "extraction_id::text = :e AND sort_instant IS NOT NULL GROUP BY 1, 2"),
            {"e": ext, "z": "UTC" if T.is_utc(zname) else zname}):
        months.setdefault(m, {"month": m, "messages": 0, "calls": 0, "other": 0})
        months[m]["messages" if k == "message" else "calls" if k == "call" else "other"] += int(n)
    month_rows = []
    if months:
        keys = sorted(months)
        y, mo = int(keys[0][:4]), int(keys[0][5:7])
        while "%04d-%02d" % (y, mo) <= keys[-1]:
            k = "%04d-%02d" % (y, mo)
            month_rows.append(months.get(k, {"month": k, "messages": 0, "calls": 0, "other": 0}))
            y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    people = streams.participant_list(conn, StreamFilter.model_validate({"case_id": str(case_id), "phones": [ext]}))
    top = [p for p in people["items"] if not p["label"].get("is_owner")][:TOP_PEOPLE]
    top_rows = [{"label": p["label"], "text": L.label_text(p["label"]), "events": p["events"],
                 "link": "%s?tab=people&people=%s" % (conv, quote(p["label"]["identity_key"], safe="")) if p["label"].get("identity_key")
                 else None} for p in top]

    suggestions = []
    if comm_deleted:
        suggestions.append({"words": "Look at the %s deleted messages and calls" % "{:,}".format(comm_deleted),
                            "link": "%s?deleted=only" % conv})
    if top_rows and top_rows[0]["link"]:
        suggestions.append({"words": "Read the conversations with %s, the most frequent contact" % top_rows[0]["text"],
                            "link": top_rows[0]["link"]})
    if open_readings:
        suggestions.append({"words": "Check how the system read this phone", "link": "%s/phone-review" % base})

    return {
        "phone": phone,
        "verdict": {"word": word, "sentence": sentence, "records": records_total, "apps": len(apps),
                    "first_day": day(span[0]), "last_day": day(span[1]), "needs_decision": n_needs},
        "owner": {"label": owner_label, "basis": basis, "words": owner_words, "missing": owner_missing,
                  "decided": bool(decided), "keys": list(own.get("owner_identity_keys") or []),
                  "candidates": candidates},
        "zone": {"device_zone": x.device_zone, "basis": x.device_zone_basis, "case_zone": zone["display_name"]},
        "report": {"filename": phone.get("report_filename"), "form": x.form, "report_version": x.report_version,
                   "producer": x.producer, "extraction_type": x.extraction_type, "container_name": x.container_name,
                   "container_sha256": x.container_sha256, "report_sha256": x.report_sha256,
                   "extraction_start": phone["device"].get("extraction_start"), "ingested_at": T.iso(x.ingested_at)},
        "selection": selection,
        "completeness": {"reconciliation": x.reconciliation_state, "state": x.state, "documents": recon,
                         "held": held},
        "files": {"total": int(files_total or 0), "by_category": by_cat, "verification": verification,
                  "link": "%s/phones/%s/records/media" % (base, ext)},
        "deleted": {"comm_events": int(comm_deleted), "link": "%s?deleted=only" % conv, "by_type": deleted},
        "coverage": coverage_rows,
        "data_periods": periods,
        "months": month_rows,
        "apps": apps,
        "top_people": top_rows,
        "needs": needs,
        "where_to_start": suggestions,
        "zone_name": zname,
        "links": {"conversations": conv, "review": "%s/phone-review" % base},
    }
