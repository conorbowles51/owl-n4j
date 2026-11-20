"""Store, confirm, correct and list the dates read from document text (lx-docdates B, C).

Readings come from services.document_dates (rules). A reading by Loupe is never saved under a person's name. A
person's correction is a new row; the reading it corrects stays. ``effective`` gives the value to use: the person's
latest correction, else the reading, with the original beside it.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select

from postgres.models.document_date import DocumentDateReading
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
from services.document_dates import RULE_SET, read_dates

log = logging.getLogger(__name__)
READ_LABEL = "Read by Loupe · not confirmed"


def store_for_file(db, file_id, apply: bool = True) -> int:
    """Read the file's stored text and save new readings. Returns how many rows were added (``apply=False``: would be
    added, writing nothing). Safe to repeat."""
    fid = file_id if isinstance(file_id, uuid.UUID) else uuid.UUID(str(file_id))
    row = db.execute(select(EvidenceFile.case_id, EvidenceDocumentText.content, EvidenceDocumentText.source_locations)
                     .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
                     .where(EvidenceFile.id == fid, EvidenceFile.deleted_at.is_(None))).first()
    if not row:
        return 0
    case_id, content, locations = row
    have = {(r.kind, r.source, r.rule, r.date_from, r.date_to) for r in db.execute(
        select(DocumentDateReading).where(DocumentDateReading.evidence_file_id == fid)).scalars()}
    added = 0
    for r in read_dates(content or "", locations):
        rule = f"{RULE_SET}:{r['rule']}"
        if (r["kind"], "rule", rule, r["date_from"], r["date_to"]) in have:
            continue
        if apply:
            db.add(DocumentDateReading(case_id=case_id, evidence_file_id=fid, kind=r["kind"], date_from=r["date_from"],
                                       date_to=r["date_to"], source="rule", rule=rule, words=r["words"], page=r["page"]))
        added += 1
    if added and apply:
        db.flush()
    return added


def store_for_file_safe(db, file_id) -> int:
    """For the ingest path: a failure here costs the dates, never the ingestion. A file the rules date nothing in is
    queued for the model's reading (services.document_dates_model), which never holds up the ingest."""
    try:
        with db.begin_nested():
            added = store_for_file(db, file_id)
            undated = not added and not _has_readings(db, file_id)
    except Exception:  # noqa: BLE001
        log.exception("document dates not read for %s", file_id)
        return 0
    if undated:
        try:
            from services import document_dates_model
            document_dates_model.schedule(file_id)
        except Exception:  # noqa: BLE001
            log.exception("document date model reading not queued for %s", file_id)
    return added


def _has_readings(db, file_id) -> bool:
    fid = file_id if isinstance(file_id, uuid.UUID) else uuid.UUID(str(file_id))
    return db.execute(select(DocumentDateReading.id).where(DocumentDateReading.evidence_file_id == fid).limit(1)
                      ).first() is not None


def store_model_for_file(db, file_id, call, apply: bool = True) -> int:
    """The model's reading of a file no rule dated (services.document_dates_model.read): saved as source 'model',
    shown "Read by Loupe · not confirmed" with its words. A file with any reading already is left alone (no call).
    Returns the rows added (``apply=False``: the call is made, nothing is written)."""
    from services import document_dates_model as M
    fid = file_id if isinstance(file_id, uuid.UUID) else uuid.UUID(str(file_id))
    if _has_readings(db, fid):
        return 0
    row = db.execute(select(EvidenceFile.case_id, EvidenceDocumentText.content, EvidenceDocumentText.source_locations)
                     .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
                     .where(EvidenceFile.id == fid, EvidenceFile.deleted_at.is_(None))).first()
    if not row or not (row.content or "").strip():
        return 0
    found = M.read(row.content, row.source_locations, call)
    if apply:
        for r in found:
            db.add(DocumentDateReading(case_id=row.case_id, evidence_file_id=fid, kind=r["kind"],
                                       date_from=r["date_from"], date_to=r["date_to"], source="model",
                                       rule=M.rule_name(call), words=r["words"], page=r["page"]))
        if found:
            db.flush()
    return len(found)


def _view(r: DocumentDateReading, original: DocumentDateReading | None = None) -> dict:
    return {
        "id": str(r.id), "evidence_file_id": str(r.evidence_file_id), "kind": r.kind,
        "date_from": r.date_from.isoformat(), "date_to": r.date_to.isoformat(), "source": r.source,
        "rule": r.rule, "words": r.words, "page": r.page,
        "confirmed": bool(r.confirmed_at) or r.source == "person",
        "confirmed_by": r.confirmed_by_name, "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
        "label": None if (r.confirmed_at or r.source == "person") else READ_LABEL,
        "original": _view(original) if original is not None else None,
    }


def effective(db, case_id, file_ids=None, confirmed_only: bool = False) -> list[dict]:
    """The date to use for each file and kind. A person's latest correction replaces the reading in use, and the
    reading it corrects is returned as ``original``. ``confirmed_only`` drops readings nobody confirmed."""
    case_id = case_id if isinstance(case_id, uuid.UUID) else uuid.UUID(str(case_id))
    q = select(DocumentDateReading).where(DocumentDateReading.case_id == case_id)
    if file_ids is not None:
        q = q.where(DocumentDateReading.evidence_file_id.in_([x if isinstance(x, uuid.UUID) else uuid.UUID(str(x)) for x in file_ids]))
    rows = list(db.execute(q.order_by(DocumentDateReading.created_at)).scalars())
    by_id = {r.id: r for r in rows}
    corrected = {r.corrects_id for r in rows if r.source == "person" and r.corrects_id}
    latest_person: dict[tuple, DocumentDateReading] = {}
    for r in rows:
        if r.source == "person":
            latest_person[(r.evidence_file_id, r.kind)] = r
    out = []
    for r in rows:
        if r.source == "person":
            if latest_person[(r.evidence_file_id, r.kind)] is not r:
                continue
            out.append(_view(r, by_id.get(r.corrects_id)))
        elif r.id not in corrected and (r.evidence_file_id, r.kind) not in latest_person:
            out.append(_view(r))
    if confirmed_only:
        out = [v for v in out if v["confirmed"]]
    return out


def confirm(db, case_id, reading_id, user_id, user_name: str) -> dict | None:
    r = db.get(DocumentDateReading, uuid.UUID(str(reading_id)))
    if not r or r.case_id != case_id or r.source == "person":
        return None
    r.confirmed_by = user_id
    r.confirmed_by_name = user_name
    r.confirmed_at = datetime.now(timezone.utc)
    db.flush()
    return _view(r)


def correct(db, case_id, reading_id, date_from: date, date_to: date, user_id, user_name: str) -> dict | None:
    """A person's value for the same file and kind. The reading stays, marked as corrected."""
    r = db.get(DocumentDateReading, uuid.UUID(str(reading_id)))
    if not r or r.case_id != case_id or r.source == "person" or date_to < date_from:
        return None
    row = DocumentDateReading(case_id=case_id, evidence_file_id=r.evidence_file_id, kind=r.kind, date_from=date_from,
                              date_to=date_to, source="person", rule="person", words=r.words, page=r.page,
                              corrects_id=r.id, confirmed_by=user_id, confirmed_by_name=user_name,
                              confirmed_at=datetime.now(timezone.utc))
    db.add(row)
    db.flush()
    return _view(row, r)


def backfill(db, case_id=None, limit: int | None = None, apply: bool = False, model=None) -> dict:
    """Read every file with text that has no reading yet, through ``store_for_file`` (the ingest path).

    ``model`` (a model call, services.document_dates_model): files the rules still date nothing in are read by it,
    one call each. A dry run makes no call and counts them as ``model_calls``."""
    q = (select(EvidenceFile.id, EvidenceFile.case_id).join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
         .where(EvidenceFile.deleted_at.is_(None), EvidenceFile.source_type.is_(None)))
    if case_id:
        q = q.where(EvidenceFile.case_id == case_id)
    done = {x for (x,) in db.execute(select(DocumentDateReading.evidence_file_id).distinct())}
    todo = [(f, c) for f, c in db.execute(q) if f not in done]
    if limit:
        todo = todo[:limit]
    per_case: dict[str, dict] = {}
    for f, c in todo:
        s = per_case.setdefault(str(c), {"files": 0, "readings": 0})
        s["files"] += 1
        if apply:
            with db.begin_nested():
                s["readings"] += store_for_file(db, f)
        undated = not _has_readings(db, f) and (apply or not store_for_file(db, f, apply=False))
        if model is not None and undated:
            s["model_calls"] = s.get("model_calls", 0) + 1
            if apply:
                try:
                    with db.begin_nested():
                        s["model_readings"] = s.get("model_readings", 0) + store_model_for_file(db, f, model)
                except Exception:  # noqa: BLE001 - one file's failure costs its date, not the run
                    log.exception("document date not read by model for %s", f)
                    s["model_failed"] = s.get("model_failed", 0) + 1
                db.commit()
    if apply:
        db.commit()
    return per_case


DOC_EVENT_PREFIX = "docdate:"


def document_date_events(db, case_id, confirmed_only: bool = False) -> list[dict]:
    """Timeline events for dated documents. Each states that the date was read from the text, by Loupe or by a
    person, and carries the words it came from. A period is one event on its first day."""
    views = effective(db, case_id, confirmed_only=confirmed_only)
    if not views:
        return []
    names = {str(i): n for i, n in db.execute(select(EvidenceFile.id, EvidenceFile.original_filename).where(
        EvidenceFile.id.in_([uuid.UUID(v["evidence_file_id"]) for v in views]), EvidenceFile.deleted_at.is_(None)))}
    words = {"written": "Document dated", "signed": "Document signed", "received": "Document received",
             "period": "Document period"}
    events = []
    for v in views:
        name = names.get(v["evidence_file_id"])
        if name is None:
            continue
        who = v["label"] or f"Confirmed by {v['confirmed_by'] or 'a person'}"
        span = v["date_from"] if v["date_from"] == v["date_to"] else f"{v['date_from']} to {v['date_to']}"
        quote = f" Words: “{v['words']}”" + (f", page {v['page']}" if v["page"] else "") if v["words"] else ""
        events.append(dict(
            key=f"{DOC_EVENT_PREFIX}{v['id']}", name=words[v["kind"]], type=("Document date" if v["confirmed"] else "Document date, not confirmed"), date=v["date_from"], time=None,
            amount=None, summary=f"{name}. {span}. {who}.{quote}", notes=None, connections=[],
            source_references=[name], evidence_file_id=v["evidence_file_id"],
            source=dict(kind="document_date", id=v["id"], date_basis=who, label=name, state="current"),
            read_date=dict(kind=v["kind"], date_from=v["date_from"], date_to=v["date_to"], source=v["source"],
                           confirmed=v["confirmed"], label=v["label"], words=v["words"], page=v["page"],
                           original=v["original"])))
    return events
