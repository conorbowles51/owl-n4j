"""Mentions in phone texts, checked against the case (lx-mentions): reading a phone, the list and counts, one
mention's checks, a person's correction, the marks on messages and the next steps.

Reading a phone is a run (``PhoneMentionRun``): pages of texts in (time, id) order, each page committed with the run's
cursor, so a run stopped by a restart carries on from its last page (``start`` resumes a stopped or stale run). The
word-rule reader runs on every phone. The model reader runs only on a phone whose Outside services are allowed
(``services.phone.external_processing``) and only when a person asks for it; a phone that does not allow it is read by
the word rules alone, and the screen says so.

Each text of a phone is a copy: a message sent from Phone 1 to Phone 3 is on both. A mention keeps its own record
(so the mark shows on each copy) and a ``copy_key`` (the words and the minute), and the list and counts show one row
per copy key, naming every phone that holds it.
"""
from __future__ import annotations

import hashlib
import threading
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from services.mentions import checks as C, kinds as K, messages as MS, reader as R
from services.mentions.data import CaseData

STALE_AFTER = timedelta(minutes=15)
PAGE = 200
EDITABLE = ("kind", "who", "with", "when", "where")


class MentionError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.now(timezone.utc)


def _name(user):
    return getattr(user, "full_name", None) or getattr(user, "name", None) or getattr(user, "email", None) or "a person"


def copy_key(body: str, at: datetime) -> str:
    words = " ".join(str(body or "").lower().split())
    return hashlib.sha1(f"{words}|{at.astimezone(timezone.utc):%Y-%m-%dT%H:%M}".encode()).hexdigest()[:40]


def phone_labels(db, case_id) -> dict[str, str]:
    from services.phone.readings import phone_labels as labels
    return labels(db.connection(), str(case_id))


def _phones(db, case_id) -> list[str]:
    return [str(r[0]) for r in db.execute(text(
        "SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active' ORDER BY created_at"), {"c": str(case_id)})]


def _outside_allowed(db, case_id, ext) -> bool:
    from services.phone import external_processing
    return external_processing.allowed(db.connection(), str(case_id), str(ext))


# ---- runs ------------------------------------------------------------------------------------------------------

def _run_view(r, labels=None) -> dict:
    stale = r.status == "running" and (r.beat_at or r.started_at) and _now() - (r.beat_at or r.started_at) > STALE_AFTER
    status = "stopped" if stale else r.status
    return {"id": str(r.id), "phone": str(r.extraction_id), "phone_label": (labels or {}).get(str(r.extraction_id)),
            "reader": r.reader, "status": status, "texts_total": r.texts_total, "texts_read": r.texts_read,
            "mentions_found": r.mentions_found, "model_calls": r.model_calls, "cost_usd": float(r.cost_usd or 0),
            "error": r.error, "started_by": r.started_by_name, "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None}


def latest_runs(db, case_id) -> dict[str, dict]:
    from postgres.models.phone_mention import PhoneMentionRun
    out = {}
    for r in db.execute(select(PhoneMentionRun).where(PhoneMentionRun.case_id == uuid.UUID(str(case_id)))
                        .order_by(PhoneMentionRun.started_at)).scalars():
        out[(str(r.extraction_id), r.reader)] = r
    return out


def start(db, case_id, extraction_id, *, user=None, reader: str = "rules", session_factory=None, inline=False) -> dict:
    """Start (or carry on) reading one phone. Returns the run."""
    from postgres.models.phone_mention import PhoneMentionRun
    ext = str(extraction_id)
    if ext not in _phones(db, case_id):
        raise MentionError("That phone is not in this case.", 404)
    if reader not in ("rules", "model"):
        raise MentionError("Choose word rules or the model.")
    if reader == "model" and not _outside_allowed(db, case_id, ext):
        raise MentionError("This phone's Outside services are not allowed, so its texts cannot go to the model. The word "
                           "rules have read it. A system owner can allow it in the case settings.", 409)
    prev = latest_runs(db, case_id).get((ext, reader))
    if prev is not None and _run_view(prev)["status"] == "running":
        return _run_view(prev)
    if prev is not None and _run_view(prev)["status"] in ("stopped", "failed"):
        row = prev  # carry on from its cursor
        row.status, row.error, row.beat_at = "running", None, _now()
    else:
        row = PhoneMentionRun(id=uuid.uuid4(), case_id=uuid.UUID(str(case_id)), extraction_id=uuid.UUID(ext), reader=reader,
                              status="running", texts_total=MS.count(db, case_id, ext), started_by_name=_name(user) if user else "Loupe",
                              beat_at=_now())
        db.add(row)
    db.commit()
    if inline:
        _work(db, str(row.id))
    else:
        if session_factory is None:
            from postgres.session import _get_background_session_local
            session_factory = _get_background_session_local()
        threading.Thread(target=_thread, args=(str(row.id), session_factory), daemon=True,
                         name=f"mentions-{ext[:8]}").start()
    db.refresh(row)
    return _run_view(row)


def _thread(run_id, session_factory):
    db = session_factory()
    try:
        _work(db, run_id)
    finally:
        db.close()


def _work(db, run_id):
    from postgres.models.phone_mention import PhoneMentionRun
    row = db.get(PhoneMentionRun, uuid.UUID(run_id))
    case_id, ext = str(row.case_id), str(row.extraction_id)
    try:
        data = CaseData(db, case_id)
        people, zone, known = data.people(), data.zone(), data.known_places()
        model = None
        if row.reader == "model":
            from services.mentions.model_reader import ModelReader
            model = ModelReader(db, zone=zone, people=people, known=known, run_id=str(row.id), case_id=row.case_id)
        while row.phase == "messages":
            after = (row.cursor_at, row.cursor_uid) if row.cursor_at else None
            page = MS.texts(db, case_id, ext, people, after=after, limit=PAGE)
            if not page:
                row.phase = "notes"
                db.commit()
                break
            found = _read_page(db, data, row, page, people, zone, known, model)
            row.cursor_at, row.cursor_uid = page[-1]["at"], page[-1]["record_uid"]
            row.texts_read += len(page)
            row.mentions_found += found
            row.beat_at = _now()
            db.commit()
        if row.phase == "notes":
            page = MS.notes(db, case_id, ext, people)
            row.mentions_found += _read_page(db, data, row, page, people, zone, known, model) if page else 0
            row.texts_read += len(page)
            row.phase = "done"
        row.status, row.finished_at = "done", _now()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the run says it failed and what with; its cursor stays for a retry
        db.rollback()
        row = db.get(PhoneMentionRun, uuid.UUID(run_id))
        row.status, row.error = "failed", f"Reading stopped: {str(exc)[:300]}"
        db.commit()
        raise


def _read_page(db, data, run, page, people, zone, known, model) -> int:
    from postgres.models.phone_mention import PhoneMention
    readings = []
    by_model = model.read_page(page) if model is not None else {}
    for t in page:
        found = by_model.get(t["record_uid"], []) if model is not None else R.read_message(
            t["body"], at=t["at"], zone=zone, speaker=t["speaker"], addressee=t["addressee"], people=people, known=known)
        readings += [(t, m) for m in found]
    if model is not None:
        run.model_calls, run.tokens_in, run.tokens_out = model.calls, model.tokens_in, model.tokens_out
        run.cost_usd = run_cost(db, run.id)
    uids = [t["record_uid"] for t in page]
    have = {(r.record_uid, r.start): r for r in db.execute(select(PhoneMention).where(
        PhoneMention.case_id == run.case_id, PhoneMention.reader == run.reader, PhoneMention.record_uid.in_(uids))).scalars()}
    n = 0
    for t, m in readings:
        if (t["record_uid"], m["start"]) in have:
            # Read again: the stored mention (and any correction on it) stays; its outcome is worked out afresh, so a
            # change in the rules or the records reaches every mention already found.
            _check_row(data, have[(t["record_uid"], m["start"])])
            n += 1
            continue
        ctx = {"at": t["at"].isoformat(), "record_uid": t["record_uid"], "phone": str(run.extraction_id), "app": t.get("app"),
               "direction": t.get("direction"), "speaker": t.get("speaker"), "addressee": t.get("addressee"),
               "counterpart_values": t.get("counterpart_values"), "body": t["body"][:4000], "record_kind": t["kind"]}
        row = PhoneMention(id=uuid.uuid4(), case_id=run.case_id, extraction_id=run.extraction_id, record_uid=t["record_uid"],
                           record_kind=t["kind"], at=t["at"], copy_key=copy_key(t["body"], t["at"]), kind=m["kind"],
                           start=m["start"], end=m["end"], phrase=m["phrase"], context=ctx, reading=m, reader=run.reader,
                           state="read", run_id=run.id)
        _check_row(data, row)
        db.add(row)
        n += 1
    return n


def run_cost(db, run_id) -> float:
    """The run's cost: the sum of the cost records its model calls wrote (``ai_cost_context`` description)."""
    v = db.execute(text("SELECT COALESCE(sum(cost_usd), 0) FROM cost_records WHERE description = :d"),
                   {"d": f"phone mentions run {run_id}"}).scalar()
    return float(v or 0)


# ---- checking --------------------------------------------------------------------------------------------------

def effective(row) -> dict:
    """The values the checks use: a person's correction where there is one, else Loupe's reading."""
    read = dict(row.reading or {})
    if row.corrected:
        read.update({k: v for k, v in row.corrected.items() if k in EDITABLE})
    return read


def _check_row(data, row):
    res = C.check(data, effective(row), row.context or {})
    row.outcome, row.result, row.checked_at = res["outcome"], res, _now()
    return res


def recheck(db, case_id, mention_id) -> dict:
    row = get(db, case_id, mention_id)
    _check_row(CaseData(db, case_id), row)
    db.commit()
    return detail(db, case_id, mention_id)


# ---- reading back ----------------------------------------------------------------------------------------------

def get(db, case_id, mention_id):
    from postgres.models.phone_mention import PhoneMention
    try:
        row = db.get(PhoneMention, uuid.UUID(str(mention_id)))
    except ValueError:
        row = None
    if row is None or str(row.case_id) != str(case_id):
        raise MentionError("That mention is not in this case.", 404)
    return row


def _people_labels(data):
    return {p["key"]: p["label"] for p in data.people()}


def _view(row, copies, labels, people) -> dict:
    eff = effective(row)
    ctx = row.context or {}
    res = row.result or {}
    who = [people.get(k, k) for k in eff.get("who") or []]
    sender = people.get(ctx.get("speaker")) if ctx.get("speaker") else None
    if not sender and ctx.get("direction") != "outgoing":
        sender = ", ".join(ctx.get("counterpart_values") or []) or "an unknown sender"
    to = [people.get(k, k) for k in ctx.get("addressee") or []] or (ctx.get("counterpart_values") or [])
    return {
        "id": str(row.id), "kind": eff.get("kind") or row.kind, "kind_label": K.LABELS.get(eff.get("kind") or row.kind),
        "phrase": row.phrase, "start": row.start, "end": row.end, "body": ctx.get("body") or "",
        "record_uid": row.record_uid, "record_kind": row.record_kind, "at": row.at.isoformat(),
        "phone": str(row.extraction_id), "phone_label": labels.get(str(row.extraction_id)),
        "copies": [{"record_uid": c.record_uid, "phone": str(c.extraction_id), "phone_label": labels.get(str(c.extraction_id))}
                   for c in copies],
        "app": ctx.get("app"), "from": sender, "to": to, "who": who, "with": [people.get(k, k) for k in eff.get("with") or []],
        "when": eff.get("when"), "where": eff.get("where"), "how": eff.get("how"),
        "amounts_minor": eff.get("amounts_minor") or [], "words": eff.get("words") or [],
        "reader": row.reader, "state": row.state,
        "read_by": K.READ_BY if row.state in ("read",) else None,
        "corrected_fields": list(row.corrected_fields or []), "original": row.reading if row.corrected else None,
        "decided_by": row.decided_by_name, "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "outcome": row.outcome, "outcome_label": K.OUTCOME_LABELS.get(row.outcome or "cant_tell"),
        "basis": res.get("basis"), "why": res.get("why"),
        "checked_at": row.checked_at.isoformat() if row.checked_at else None,
    }


def _rows(db, case_id, phones=None):
    from postgres.models.phone_mention import PhoneMention
    q = select(PhoneMention).where(PhoneMention.case_id == uuid.UUID(str(case_id)))
    if phones:
        q = q.where(PhoneMention.extraction_id.in_([uuid.UUID(p) for p in phones]))
    return list(db.execute(q.order_by(PhoneMention.at.desc(), PhoneMention.start)).scalars())


def _group(rows):
    """One row per copy: the sender's copy leads (it says "I" for its owner), the others are listed with it."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r.copy_key, r.start, r.kind)].append(r)
    out = []
    for g in groups.values():
        g.sort(key=lambda r: ((r.context or {}).get("direction") != "outgoing", r.reader != "rules", str(r.extraction_id)))
        out.append(g)
    out.sort(key=lambda g: g[0].at, reverse=True)
    return out


ORDER = {"contradicts": 0, "contradicts_weakly": 1, "cant_tell": 4, "fits_weakly": 3, "fits_strongly": 2}


def listing(db, case_id, *, phones=None, kind=None, outcome=None, include_rejected=False, limit=200, offset=0) -> dict:
    data = CaseData(db, case_id)
    labels = phone_labels(db, case_id)
    people = _people_labels(data)
    all_phones = _phones(db, case_id)
    phones = [p for p in (phones or all_phones) if p in all_phones]
    groups = [g for g in _group(_rows(db, case_id, phones)) if include_rejected or g[0].state != "rejected"]
    counts = {k: {"fits": 0, "against": 0, "unknown": 0, "total": 0} for k in K.KINDS}
    for g in groups:
        e = effective(g[0])
        k = e.get("kind") or g[0].kind
        col = K.TABLE_COLUMN.get(g[0].outcome or "cant_tell", "unknown")
        counts[k][col] += 1
        counts[k]["total"] += 1
    sel = [g for g in groups if (not kind or (effective(g[0]).get("kind") or g[0].kind) == kind)
           and (not outcome or _outcome_matches(g[0].outcome, outcome))]
    sel.sort(key=lambda g: (ORDER.get(g[0].outcome or "cant_tell", 5), -g[0].at.timestamp()))
    runs = latest_runs(db, case_id)
    phone_state = []
    for p in phones:
        rr = runs.get((p, "rules"))
        mr = runs.get((p, "model"))
        phone_state.append({"phone": p, "phone_label": labels.get(p), "texts": MS.count(db, case_id, p),
                            "rules": _run_view(rr, labels) if rr else None, "model": _run_view(mr, labels) if mr else None,
                            "outside_allowed": _outside_allowed(db, case_id, p)})
    total = len(sel)
    page = sel[offset:offset + limit]
    return {"counts": [{"kind": k, "label": K.LABELS[k], **counts[k]} for k in K.KINDS],
            "total": total, "shown": len(page), "offset": offset,
            "mentions": [_view(g[0], g, labels, people) for g in page],
            "phones": phone_state, "how": K.HOW, "next_steps": next_steps(groups, people, labels),
            "read_by": K.READ_BY}


def _outcome_matches(have, want):
    if want == "against":
        return have in ("contradicts", "contradicts_weakly")
    if want == "fits":
        return have in ("fits_strongly", "fits_weakly")
    if want == "unknown":
        return have in (None, "cant_tell")
    return have == want


def detail(db, case_id, mention_id) -> dict:
    row = get(db, case_id, mention_id)
    data = CaseData(db, case_id)
    labels = phone_labels(db, case_id)
    people = _people_labels(data)
    copies = [r for r in _rows(db, case_id) if r.copy_key == row.copy_key and r.start == row.start and r.kind == row.kind]
    res = C.check(data, effective(row), row.context or {})  # fresh: the case may have changed since it was stored
    if res["outcome"] != row.outcome:
        row.outcome, row.result, row.checked_at = res["outcome"], res, _now()
        db.commit()
    view = _view(row, copies or [row], labels, people)
    view.update({"checks": res["checks"], "would_test": res["would_test"], "window": res["window"],
                 "outcome": res["outcome"], "outcome_label": res["label"], "basis": res["basis"], "why": res["why"]})
    return view


# ---- a person's decision ---------------------------------------------------------------------------------------

def correct(db, case_id, mention_id, *, values: dict | None, action: str, reason: str | None, user) -> dict:
    """``action``: ``correct`` (values replace Loupe's for the fields given; the reading stays beside them),
    ``confirm`` (the person agrees with what is shown), ``reject`` (not a mention; kept, marked rejected),
    ``restore`` (back to Loupe's reading)."""
    row = get(db, case_id, mention_id)
    if action not in ("correct", "confirm", "reject", "restore"):
        raise MentionError("Choose correct, confirm, reject or restore.")
    if action == "correct":
        vals = {k: v for k, v in (values or {}).items() if k in EDITABLE}
        if not vals:
            raise MentionError("Say what to change: the kind, who, who with, when or where.")
        if "kind" in vals and vals["kind"] not in K.KINDS:
            raise MentionError("That is not a kind of mention Loupe checks.")
        if "when" in vals:
            w = vals["when"] or {}
            try:
                lo, hi = (datetime.fromisoformat(str(w[k]).replace("Z", "+00:00")) for k in ("start", "end"))
            except (KeyError, ValueError, TypeError):
                raise MentionError("The time needs a start and an end, each a date and time with its offset.")
            if lo.tzinfo is None or hi.tzinfo is None or hi <= lo:
                raise MentionError("The time must end after it starts and carry its offset.")
            vals["when"] = {"start": lo.astimezone(timezone.utc).isoformat(), "end": hi.astimezone(timezone.utc).isoformat(),
                            "zone": w.get("zone") or "UTC", "label": str(w.get("label") or "")[:200], "words": None,
                            "assumed": None}
        if "where" in vals and vals["where"] is not None:
            w = vals["where"]
            try:
                vals["where"] = {"name": str(w.get("name") or "")[:200], "words": str(w.get("name") or "")[:200],
                                 "located": w.get("lat") is not None, **({"lat": float(w["lat"]), "lon": float(w["lon"]),
                                 "radius_m": float(w.get("radius_m") or 150)} if w.get("lat") is not None else {})}
            except (ValueError, TypeError, KeyError):
                raise MentionError("A place needs a latitude, a longitude and a radius in metres, or a name only.")
        for k in ("who", "with"):
            if k in vals:
                vals[k] = [str(x) for x in (vals[k] or [])][:10]
        row.corrected = {**(row.corrected or {}), **vals}
        row.corrected_fields = sorted(set(row.corrected_fields or []) | set(vals))
        row.state = "corrected"
        if "kind" in vals:
            row.kind = vals["kind"]
    elif action == "restore":
        row.corrected, row.corrected_fields, row.state = None, [], "read"
        row.kind = (row.reading or {}).get("kind", row.kind)
    else:
        row.state = "confirmed" if action == "confirm" else "rejected"
    if action != "restore":
        row.decided_by, row.decided_by_name, row.decided_at = getattr(user, "id", None), _name(user), _now()
        row.decided_reason = (reason or "").strip()[:1000] or None
    else:
        row.decided_by = row.decided_by_name = row.decided_at = row.decided_reason = None
    _check_row(CaseData(db, case_id), row)
    db.commit()
    return detail(db, case_id, mention_id)


# ---- marks on messages -----------------------------------------------------------------------------------------

def marks(db, case_id, record_uids: list[str]) -> dict:
    from postgres.models.phone_mention import PhoneMention
    uids = [u for u in dict.fromkeys(str(x) for x in record_uids or []) if u][:500]
    out: dict[str, list] = {}
    if not uids:
        return {"marks": out}
    rows = db.execute(select(PhoneMention).where(PhoneMention.case_id == uuid.UUID(str(case_id)),
                                                 PhoneMention.record_uid.in_(uids), PhoneMention.state != "rejected")
                      .order_by(PhoneMention.start)).scalars()
    for r in rows:
        k = effective(r).get("kind") or r.kind
        out.setdefault(r.record_uid, []).append({
            "id": str(r.id), "kind": k, "kind_label": K.LABELS.get(k), "start": r.start, "end": r.end, "phrase": r.phrase,
            "outcome": r.outcome, "outcome_label": K.OUTCOME_LABELS.get(r.outcome or "cant_tell"), "state": r.state,
            "read_by": K.READ_BY if r.state == "read" else None})
    return {"marks": out}


# ---- next steps ------------------------------------------------------------------------------------------------

def next_steps(groups, people, labels) -> list[dict]:
    """Ranked from this result: contradictions first, then what cannot be tested and what would test it, then what
    fits and could go on the timeline. Each step names its mentions; none is a fixed line."""
    rows = [g[0] for g in groups if g[0].state != "rejected"]
    against = [r for r in rows if r.outcome in ("contradicts", "contradicts_weakly")]
    unknown = [r for r in rows if r.outcome in (None, "cant_tell")]
    fits = [r for r in rows if r.outcome == "fits_strongly"]
    steps = []
    if against:
        top = sorted(against, key=lambda r: (r.outcome != "contradicts", -r.at.timestamp()))[0]
        res = top.result or {}
        steps.append({"title": f"Look at “{top.phrase}” first",
                      "why": f"{res.get('why') or 'The records go against it.'} A statement the records contradict is worth "
                             "more than one they confirm."
                             + (f" {len(against) - 1} more mention{'s' if len(against) != 2 else ''} {'are' if len(against) != 2 else 'is'} "
                                "contradicted." if len(against) > 1 else ""),
                      "action": "open_mention", "label": "Open the contradiction", "mention_id": str(top.id), "primary": True})
    if unknown:
        by_kind = Counter(effective(r).get("kind") or r.kind for r in unknown)
        k, n = by_kind.most_common(1)[0]
        steps.append({"title": f"Settle the {K.LABELS[k].lower()} mentions Loupe could not test",
                      "why": f"{n} {K.LABELS[k].lower()} mention{'s' if n != 1 else ''} cannot be tested from the case yet. Each says "
                             "what would test it.",
                      "action": "filter", "label": "Show what would test them", "kind": k, "outcome": "unknown"})
    unplaced = Counter(((effective(r).get("where") or {}).get("name")) for r in rows
                       if (effective(r).get("where") or {}).get("name") and not (effective(r).get("where") or {}).get("located")
                       and not (effective(r).get("where") or {}).get("routine")
                       and (effective(r).get("where") or {}).get("name") not in ("outside",))
    if unplaced:
        name, n = unplaced.most_common(1)[0]
        steps.append({"title": f"Put {name} on the map",
                      "why": f"{n} mention{'s' if n != 1 else ''} name {name}, which has no position in the case, so the phones' "
                             "places cannot be tested against it. A labelled place makes each one testable.",
                      "action": "open_map", "label": "Open the map", "place": name})
    if fits:
        top = sorted(fits, key=lambda r: -r.at.timestamp())[0]
        steps.append({"title": f"Put “{top.phrase}” on the case timeline",
                      "why": f"{(top.result or {}).get('basis', 'The records agree').capitalize()}. On the timeline it sits beside "
                             "everything else at that time.",
                      "action": "open_mention", "label": "Open it", "mention_id": str(top.id)})
    if len(against) > 1:
        kinds_ = Counter(effective(r).get("kind") or r.kind for r in against)
        steps.append({"title": "Check the other contradictions",
                      "why": "; ".join(f"{n} {K.LABELS[k].lower()}" for k, n in kinds_.most_common()) + " mentions are "
                             "contradicted by the records.",
                      "action": "filter", "label": "Show all contradictions", "outcome": "against"})
    for i, s in enumerate(steps, 1):
        s["n"] = i
    return steps
