"""Saved keyword lists (docs/cellebrite/03 section 11.2; 07 J-6 "Saves"; 07 section 14 "keyword lists attached to a
theory").

A search saved as a named list of terms. The list runs on every phone of its case, including phones added later:
the phone worker's after-pass step (``run_stale``) runs a list again whenever its terms or the case's phones changed
(a phone added, re-read, replaced, finished reading, or text read from its media). Each run keeps the exact total per
phone, per term and per group, counted by the same search that opens the hits (``services.search.search``, one
phone at a time), so a list's total equals what the search shows for that phone and term, and each hit opens the
record in context through the search's own hit links (07 J-6 step 3). Sensitive values are never searched, as in
search (05 section 3.8).

A list is a Workspace note tagged ``keyword list`` (it shows, is searched and is deleted with the rest of the
Workspace) with a ``phone_keyword_lists`` row holding its terms, written in one transaction (the pattern of the case
terms in ``services/pattern_of_life/key_dates.py``). A theory takes a list through the Workspace's own entry link
(target type ``entry``), so the theory shows its lists and their current totals.

Decisions (03 section 11 decisions table, 11.2):

- Lists count the phone groups only: messages, calls, emails, other phone records and machine-generated text from
  media. People and documents are case-wide rather than per phone and stay in the search itself. Reverse if a list
  must count documents too.
- A term is at least 3 letters after folding (search's own floor, 11.6); a shorter term is refused with words.
- Every run states when it ran, on how many phones, and names each phone of the case it could not count in full
  (still being read, only partly read, not yet readable): rule 2, nothing silently left out.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from services.phone import fold as F

log = logging.getLogger(__name__)

TAG = "keyword list"
GROUPS = ("messages", "calls", "emails", "records", "machine_text")
GROUP_WORDS = {"messages": "messages", "calls": "calls", "emails": "emails", "records": "other phone records",
               "machine_text": "text read from photos and audio"}
MAX_TERMS = 50
MAX_TERM = 240
RUN_VERSION = "kw1"  # a change in how a list counts runs every list again


class KeywordListError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def clean_terms(terms, exact=False) -> list:
    """The list's terms as typed, trimmed, one per distinct folded form, in the order given."""
    out, seen = [], set()
    for t in terms or []:
        t = " ".join(str(t or "").split())
        if not t:
            continue
        if len(t) > MAX_TERM:
            raise KeywordListError("A term is at most %d characters." % MAX_TERM)
        key = F.fold(t, exact=exact)
        if len(key.replace(" ", "")) < 3:
            raise KeywordListError("\"%s\" is too short: a keyword list term needs at least 3 letters or digits." % t)
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    if not out:
        raise KeywordListError("A keyword list needs at least one term.")
    if len(out) > MAX_TERMS:
        raise KeywordListError("A keyword list holds at most %d terms; this one has %d. Split it into two lists."
                               % (MAX_TERMS, len(out)))
    return out


def create(db, case_id, user, *, name, terms, exact=False, note=None) -> dict:
    from services.workspace_entry_service import create_entry
    name = " ".join((name or "").split())
    if not name:
        raise KeywordListError("Give the keyword list a name.")
    terms = clean_terms(terms, exact)
    eid = uuid.uuid4()
    db.execute(text(
        "INSERT INTO phone_keyword_lists (entry_id, case_id, name, terms, exact, created_by) VALUES (:e, :c, :n, "
        "CAST(:t AS jsonb), :x, :b)"),
        {"e": eid, "c": str(case_id), "n": name[:240], "t": json.dumps(terms), "x": bool(exact),
         "b": (getattr(user, "name", None) or getattr(user, "email", None) or "")[:240] or None})
    body = "Keyword list %s: %s.%s Runs on every phone in the case, including phones added later." % (
        name, "; ".join("\"%s\"" % t for t in terms), " Exact characters." if exact else "")
    if note:
        body += " " + note.strip()
    create_entry(db, case_id=case_id, current_user=user, entry_id=eid, entry_type="note", body=body,
                 title=("Keyword list: %s" % name)[:240], tags=[TAG])  # commits the note and the row together
    return get(db.connection(), case_id, eid)


_SELECT = ("SELECT k.entry_id, k.name, k.terms, k.exact, k.created_by, k.created_at, k.run_signature, "
           "k.run_started_at, k.last_run_at, k.run, k.run_error FROM phone_keyword_lists k JOIN workspace_entries w "
           "ON w.id = k.entry_id WHERE k.case_id = :c AND w.deleted_at IS NULL")


def _iso(v):
    return v.isoformat() if v else None


def _theories(conn, case_id, entry_ids) -> dict:
    """``{list entry id: [{id, title}]}``: theories that link to each list (07 section 14)."""
    if not entry_ids:
        return {}
    out = {}
    for r in conn.execute(text(
            "SELECT l.target_id, w.id, w.title FROM workspace_entry_links l JOIN workspace_entries w ON w.id = "
            "l.entry_id WHERE w.case_id = :c AND w.entry_type = 'theory' AND w.deleted_at IS NULL AND l.target_type "
            "= 'entry' AND l.target_id = ANY(:ids) ORDER BY w.title, w.id"),
            {"c": str(case_id), "ids": [str(e) for e in entry_ids]}):
        out.setdefault(str(r[0]), []).append({"id": str(r[1]), "title": r[2]})
    return out


def _out(conn, r, theories, current) -> dict:
    run = r["run"] or None
    state = "not_run"
    if run is not None:
        state = "current" if r["run_signature"] == current else "rerun_due"
    elif r["run_error"]:
        state = "failed"
    out = {"entry_id": str(r["entry_id"]), "name": r["name"], "terms": list(r["terms"]), "exact": r["exact"],
           "created_by": r["created_by"], "created_at": _iso(r["created_at"]), "last_run_at": _iso(r["last_run_at"]),
           "state": state, "error": r["run_error"], "theories": theories.get(str(r["entry_id"]), []),
           "run": run, "summary": summary(run, state)}
    return out


def summary(run, state) -> str:
    """The list's run in words: when, on how many phones, and every phone not counted in full (rule 2)."""
    if run is None:
        return ("Not run yet. It runs on every phone in the case within a minute of being saved."
                if state != "failed" else "The last run failed; it is tried again after the next phone pass.")
    n = len(run["phones"])
    words = "Last run %s on %d %s, %s %s in all." % (
        run["ran_at_words"], n, "phone" if n == 1 else "phones", "{:,}".format(run["total"]),
        "match" if run["total"] == 1 else "matches")
    for p in run.get("not_counted", []):
        words += " " + p["message"]
    if state == "rerun_due":
        words += " The phones or the list changed since; it runs again after the next phone pass."
    return words


def list_for_case(conn, case_id, theory=None) -> dict:
    q = _SELECT
    p = {"c": str(case_id)}
    if theory:
        q += (" AND k.entry_id::text IN (SELECT l.target_id FROM workspace_entry_links l WHERE l.entry_id = :t AND "
              "l.target_type = 'entry')")
        p["t"] = str(theory)
    rows = list(conn.execute(text(q + " ORDER BY k.created_at, k.entry_id"), p).mappings())
    th = _theories(conn, case_id, [r["entry_id"] for r in rows])
    phones = case_phones(conn, case_id)
    items = [_out(conn, r, th, signature(conn, case_id, r, phones)) for r in rows]
    return {"total": len(items), "items": items}


def get(conn, case_id, entry_id) -> dict | None:
    r = conn.execute(text(_SELECT + " AND k.entry_id = :e"), {"c": str(case_id), "e": str(entry_id)}).mappings().first()
    if r is None:
        return None
    return _out(conn, r, _theories(conn, case_id, [r["entry_id"]]),
                signature(conn, case_id, r, case_phones(conn, case_id)))


def attach_theory(db, case_id, entry_id, theory_id, user) -> dict:
    """Attach the list to a theory through the Workspace's own link (the theory's history records it)."""
    from services.workspace_entry_service import add_entry_links, get_entry
    if get(db.connection(), case_id, entry_id) is None:
        raise KeywordListError("That keyword list is not in this case.", 404)
    theory = get_entry(db, case_id=case_id, entry_id=theory_id)
    if theory.get("entry_type") != "theory":
        raise KeywordListError("Keyword lists attach to a theory; that entry is a %s." % theory.get("entry_type"))
    add_entry_links(db, case_id=case_id, entry_id=theory_id, current_user=user,
                    expected_version=theory["version"], ignore_existing=True,
                    links=[{"target_type": "entry", "target_id": str(entry_id), "relationship": "context"}],
                    rationale="Keyword list attached to the theory")
    return get(db.connection(), case_id, entry_id)


# ---- the run ------------------------------------------------------------------------------------------------------

def case_phones(conn, case_id) -> list:
    """Every phone of the case that is not replaced or withdrawn, with its reading state (``pv_extraction``), its
    generation and the time its media text last changed: what a run counts and what makes it due again."""
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT e.id::text AS extraction_id, e.standing::text AS standing, x.state, s.generation, "
        "s.interpreter_version, s.texts_at, (SELECT max(coalesce(d.corrected_at, d.finished_at)) FROM "
        "phone_derived_texts d JOIN pv_file f ON f.file_uid = d.file_uid WHERE f.extraction_id = e.id AND d.state = "
        "'done') AS media_at, (SELECT max(t.finished_at) FROM phone_translations t WHERE t.case_id = e.case_id AND "
        "t.state = 'done') AS translated_at FROM phone_extractions e LEFT JOIN pv_extraction x ON x.extraction_id = "
        "e.id LEFT JOIN phone_interpretation_state s ON s.extraction_id = e.id WHERE e.case_id = :c AND e.standing IN "
        "('pending', 'active') ORDER BY e.id"), {"c": str(case_id)})]


def signature(conn, case_id, row, phones) -> str:
    """What a list's totals rest on: its terms and folding, and each phone's reading state."""
    basis = {"v": RUN_VERSION, "terms": list(row["terms"]),
             "exact": bool(row["exact"]),
             "phones": [[p["extraction_id"], p["standing"], p["state"], p["generation"], p["interpreter_version"],
                         _iso(p["texts_at"]), _iso(p["media_at"]), _iso(p["translated_at"])] for p in phones]}
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()


def _not_counted(phones, labels) -> list:
    out = []
    for p in phones:
        label = labels.get(p["extraction_id"]) or "A phone"
        if p["standing"] != "active":
            msg = "%s is not readable yet and is not counted; the list runs on it when it is." % label
        elif p["state"] in ("partial", "failed"):
            msg = "%s's report could only be partly read, so its counts are incomplete." % label
        elif p["state"] != "ingested":
            msg = "%s is still being read, so its counts are incomplete; the list runs again when it finishes." % label
        else:
            continue
        out.append({"extraction_id": p["extraction_id"], "phone_label": label, "state": p["state"] or p["standing"],
                    "message": msg})
    return out


def count(conn, case_id, terms, exact, phones=None) -> dict:
    """``{"phones": [{extraction_id, phone_label, total, terms: {term: {group: n}}}], "terms": {term: n}, "total"}``
    counted by the search itself, one phone at a time."""
    from services.search import search as S
    from services.phone_analysis.fields import active_phones
    ctx = S._context(conn, case_id)
    labels = active_phones(conn, case_id)
    ids = [p for p in labels if phones is None or p in phones]
    out, by_term, total = [], {t: 0 for t in terms}, 0
    for ext in ids:
        per = {}
        n_phone = 0
        for t in terms:
            groups = {}
            for g in GROUPS:
                groups[g] = int(S._group(conn, case_id, g, t, exact, [ext], None, None, 0, 0, ctx, False)["total"])
            per[t] = groups
            s = sum(groups.values())
            by_term[t] += s
            n_phone += s
        total += n_phone
        out.append({"extraction_id": ext, "phone_label": labels[ext], "total": n_phone, "terms": per})
    return {"phones": out, "terms": by_term, "total": total}


def run_list(conn, case_id, row, phones=None) -> dict:
    """Count one list on every active phone of its case and store the run with its signature."""
    from services.phone.readings import phone_labels
    phones = case_phones(conn, case_id) if phones is None else phones
    sig = signature(conn, case_id, row, phones)
    terms = list(row["terms"])
    counted = count(conn, case_id, terms, bool(row["exact"]))
    now = datetime.now(timezone.utc)
    run = dict(counted, ran_at=now.isoformat(), ran_at_words=now.strftime("%Y-%m-%d %H:%M UTC"),
               groups=list(GROUPS), group_words=GROUP_WORDS,
               not_counted=_not_counted(phones, phone_labels(conn, str(case_id))))
    conn.execute(text(
        "UPDATE phone_keyword_lists SET run = CAST(:r AS jsonb), run_signature = :s, last_run_at = :t, run_error = "
        "NULL WHERE entry_id = :e"), {"r": json.dumps(run), "s": sig, "t": now, "e": str(row["entry_id"])})
    return run


def run_stale(engine) -> dict:
    """The phone worker's after-pass step: run every list whose terms or case phones changed since its last run.
    One list per transaction; a list that fails keeps its last run and records the error."""
    done = {}
    with engine.connect() as conn:
        rows = list(conn.execute(text(
            "SELECT k.entry_id, k.case_id, k.terms, k.exact, k.run_signature FROM phone_keyword_lists k JOIN "
            "workspace_entries w ON w.id = k.entry_id WHERE w.deleted_at IS NULL ORDER BY k.case_id, "
            "k.created_at")).mappings())
    phones_by_case = {}
    for r in rows:
        case = str(r["case_id"])
        try:
            with engine.begin() as conn:
                if case not in phones_by_case:
                    phones_by_case[case] = case_phones(conn, case)
                if signature(conn, case, r, phones_by_case[case]) == r["run_signature"]:
                    continue
                conn.execute(text("UPDATE phone_keyword_lists SET run_started_at = now() WHERE entry_id = :e"),
                             {"e": str(r["entry_id"])})
                run = run_list(conn, case, r, phones_by_case[case])
                done[str(r["entry_id"])] = run["total"]
        except Exception as exc:  # noqa: BLE001
            log.exception("keyword list %s failed", r["entry_id"])
            with engine.begin() as conn:
                conn.execute(text("UPDATE phone_keyword_lists SET run_error = :m WHERE entry_id = :e"),
                             {"m": type(exc).__name__, "e": str(r["entry_id"])})
    return done


def investigator_terms(conn, case_id) -> list:
    """The case's investigator-added terms (05 sections 10.3 step 1 and 12.3 step 1): its case terms (Workspace notes
    tagged ``case term``) and the terms of its keyword lists, deleted notes left out, in a stable order."""
    terms = set()
    for (t,) in conn.execute(text(
            "SELECT k.term FROM pol_key_date k JOIN workspace_entries w ON w.id = k.entry_id WHERE k.case_id = :c AND "
            "k.kind = 'term' AND w.deleted_at IS NULL"), {"c": str(case_id)}):
        if t and t.strip():
            terms.add(t.strip())
    for (ts,) in conn.execute(text(
            "SELECT k.terms FROM phone_keyword_lists k JOIN workspace_entries w ON w.id = k.entry_id WHERE "
            "k.case_id = :c AND w.deleted_at IS NULL"), {"c": str(case_id)}):
        terms.update(t.strip() for t in ts or [] if t and t.strip())
    return sorted(terms)


def for_coverage(conn, case_id) -> list:
    """For the J-13 coverage summary: each keyword list run on the case, its terms, when it last ran, on how many
    phones, its total, and the phones it could not count in full."""
    out = []
    for item in list_for_case(conn, case_id)["items"]:
        run = item["run"] or {}
        out.append({"name": item["name"], "terms": item["terms"], "exact": item["exact"],
                    "last_run_at": item["last_run_at"], "phones": len(run.get("phones", [])),
                    "total": run.get("total"), "terms_totals": run.get("terms", {}),
                    "not_counted": [p["message"] for p in run.get("not_counted", [])], "state": item["state"],
                    "summary": item["summary"]})
    return out


def install():
    """Called by the phone worker (one writer for list runs)."""
    from services.phone import sweep
    sweep.register_after_pass(run_stale)
