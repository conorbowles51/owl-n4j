"""Work running on the server, in one list, and a Stop for each kind (Background Tasks, /admin/tasks).

Kinds, each stopped through the stop it already had:
- ``processing``: a case's files with the processing service (uploads and processing again). The engine's cancel
  stops each batch after the step it is on; files that finished stay in the case, the rest end "Cancelled on
  request." and can be processed again. A batch already writing to the case cannot be stopped and finishes.
- ``export``: a whole-case export (case_exports). No export file is offered after a stop.
- ``statement_import``: a Financial statement batch being prepared. Stopping pauses it: statements already
  prepared stay, the ones not started are left as they were and Resume continues them.

Administrators may stop any of it; a case's owner may stop work in that case. Each stop is recorded in the activity
trail as ``background_task_stopped`` with what finished and what did not, and listed under "Stopped" afterwards.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from postgres.models.activity_event import ActivityEvent
from postgres.models.case import Case
from postgres.models.case_export import CaseExport
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole, GlobalRole
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from postgres.models.user import User
from services import activity_trail

KINDS = ("processing", "export", "statement_import")
STOPPED_ACTION = "background_task_stopped"
STOPPED_SHOWN_DAYS = 7
STOPPED_SHOWN = 50
_EXPORT_RUNNING = ("queued", "running")
_BATCH_RUNNING = ("preparing",)


class StopRefused(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def is_admin(user: User) -> bool:
    return user.global_role in (GlobalRole.admin, GlobalRole.super_admin)


def owned_case_ids(db: Session, user: User) -> set[UUID]:
    return set(db.scalars(select(CaseMembership.case_id).where(
        CaseMembership.user_id == user.id, CaseMembership.membership_role == CaseMembershipRole.owner)))


def _scope(db: Session, user: User):
    """None: every case (administrators). Otherwise the cases this person owns."""
    return None if is_admin(user) else owned_case_ids(db, user)


def _in(column, cases):
    return True if cases is None else column.in_(cases)


def _iso(value):
    return value.isoformat() if value else None


def list_running(db: Session, user: User) -> dict:
    cases = _scope(db, user)
    if cases is not None and not cases:
        return dict(scope="owned_cases", tasks=[], stopped=[])
    tasks = []
    for case_id, count, since in db.execute(
            select(EvidenceFile.case_id, func.count(), func.min(EvidenceFile.updated_at))
            .where(EvidenceFile.status == "processing", _in(EvidenceFile.case_id, cases))
            .group_by(EvidenceFile.case_id)):
        tasks.append(dict(kind="processing", id=str(case_id), case_id=str(case_id),
            name=f"Processing {count} file{'s' if count != 1 else ''}", started_at=_iso(since), started_by=None,
            progress=dict(total=count)))
    for row in db.scalars(select(CaseExport).where(CaseExport.status.in_(_EXPORT_RUNNING),
                                                   _in(CaseExport.case_id, cases))):
        tasks.append(dict(kind="export", id=str(row.id), case_id=str(row.case_id), name="Whole-case export",
            started_at=_iso(row.created_at), started_by=row.requested_by_name or row.requested_by_email,
            progress=dict(total=row.total or 0, completed=row.done or 0)))
    for batch in db.scalars(select(FinancialImportBatch).where(FinancialImportBatch.status.in_(_BATCH_RUNNING),
                                                               _in(FinancialImportBatch.case_id, cases))):
        prepared = _prepared(db, batch.id)
        tasks.append(dict(kind="statement_import", id=str(batch.id), case_id=str(batch.case_id),
            name="Preparing statements for Financial", started_at=None,
            started_by=(batch.actor or {}).get("name") or (batch.actor or {}).get("email"),
            progress=dict(total=len(batch.files or []), completed=prepared)))
    titles = {row.id: row.title for row in db.execute(select(Case.id, Case.title).where(
        Case.id.in_({UUID(t["case_id"]) for t in tasks})))} if tasks else {}
    for task in tasks:
        task["case_title"] = titles.get(UUID(task["case_id"]))
        task["status"] = "running"
    return dict(scope="all" if cases is None else "owned_cases", tasks=tasks, stopped=_stopped(db, cases))


def _prepared(db, batch_id):
    return db.scalar(select(func.count()).select_from(FinancialImportBatchItem)
                     .where(FinancialImportBatchItem.batch_id == batch_id)) or 0


def _stopped(db, cases):
    since = datetime.now(timezone.utc) - timedelta(days=STOPPED_SHOWN_DAYS)
    rows = db.scalars(select(ActivityEvent).where(ActivityEvent.action == STOPPED_ACTION, ActivityEvent.at >= since,
                                                  _in(ActivityEvent.case_id, cases))
                      .order_by(ActivityEvent.at.desc()).limit(STOPPED_SHOWN))
    return [dict(kind=(r.details or {}).get("kind"), id=(r.details or {}).get("task_id"),
                 case_id=str(r.case_id) if r.case_id else None, name=(r.details or {}).get("name"),
                 status="stopped", stopped_by=r.user_name or r.user_email, stopped_at=_iso(r.at),
                 summary=(r.details or {}).get("summary")) for r in rows]


def _authorize(db, user, case_id):
    if is_admin(user):
        return
    if case_id not in owned_case_ids(db, user):
        raise StopRefused("Only an administrator or this case's owner can stop its work.", 403)


def _who(user):
    return user.name or user.email


async def stop(db: Session, user: User, kind: str, task_id: str) -> dict:
    """Database work runs in a thread, never on the event loop (a session held across awaits deadlocked, 1 Nov)."""
    from fastapi.concurrency import run_in_threadpool
    if kind not in KINDS:
        raise StopRefused("Unknown kind of work.", 404)
    try:
        key = UUID(str(task_id))
    except ValueError:
        raise StopRefused("Unknown task.", 404) from None
    if kind == "processing":
        result = await _stop_processing(db, user, key)
    elif kind == "export":
        result = await run_in_threadpool(_stop_export, db, user, key)
    else:
        result = await run_in_threadpool(_stop_batch, db, user, key)
    who = _who(user)
    result["summary"] = f"Stopped by {who}. {result['summary']}"
    result.update(kind=kind, id=str(task_id), stopped_by=who, status="stopped")

    def record():
        activity_trail.record(STOPPED_ACTION, db=db, user=user, case_id=result["case_id"],
            details=dict(kind=kind, task_id=str(task_id), name=result["name"], summary=result["summary"],
                         counts=result["counts"]))
        db.commit()
    await run_in_threadpool(record)
    result["case_id"] = str(result["case_id"])
    return result


async def _stop_processing(db, user, case_id):
    from services import evidence_engine_client
    from services.evidence_db_storage import EvidenceDBStorage
    from fastapi.concurrency import run_in_threadpool

    def read():
        _authorize(db, user, case_id)
        found = list(db.execute(select(EvidenceFile.id, EvidenceFile.engine_job_id)
                                .where(EvidenceFile.case_id == case_id, EvidenceFile.status == "processing")))
        db.rollback()  # no transaction stays open while the engine is asked
        return found
    rows = await run_in_threadpool(read)
    if not rows:
        raise StopRefused("Nothing is processing in this case now.", 409)
    asked, refused, no_job = 0, {}, 0
    for job_id in dict.fromkeys(str(r.engine_job_id) for r in rows if r.engine_job_id):
        try:
            outcome = await evidence_engine_client.control_job(job_id, str(case_id), "cancel")
            asked += int(outcome.get("affected_jobs") or 0)
        except httpx.HTTPStatusError as exc:
            try:
                reason = exc.response.json().get("detail") or "The processing service refused the stop."
            except ValueError:
                reason = "The processing service refused the stop."
            refused[reason] = refused.get(reason, 0) + 1
    no_job = sum(1 for r in rows if not r.engine_job_id)
    total = len(rows)
    parts = [f"Of {total} file{'s' if total != 1 else ''} processing: {asked} asked to stop after the step "
             "each is on (they end cancelled and can be processed again; anything already finished stays in "
             "the case)"]
    for reason, count in refused.items():
        parts.append(f"{count} batch{'es' if count != 1 else ''} could not be stopped: {reason}")
    if no_job:
        parts.append(f"{no_job} had no processing job to stop")
    await run_in_threadpool(EvidenceDBStorage.add_log, db, case_id=case_id, level="info",
                            message=f"Stop of processing in this case requested by {user.email}: "
                                    f"{asked} file(s) asked to stop")
    return dict(case_id=case_id, name=f"Processing {total} file{'s' if total != 1 else ''}",
                summary="; ".join(parts) + ".",
                counts=dict(processing=total, asked_to_stop=asked, could_not_stop=sum(refused.values()),
                            without_job=no_job))


def _stop_export(db, user, export_id):
    row = db.get(CaseExport, export_id, with_for_update=True)
    if row is None:
        raise StopRefused("Unknown task.", 404)
    _authorize(db, user, row.case_id)
    if row.status == "queued":
        row.status = "cancelled"
    elif row.status == "running":
        row.status = "cancelling"
    else:
        raise StopRefused("This export is not running.", 409)
    done, total = row.done or 0, row.total or 0
    return dict(case_id=row.case_id, name="Whole-case export",
                summary=f"{done} of {total} items were written before the stop; no export file is offered. "
                        "Ask for the export again to make a whole one.",
                counts=dict(done=done, total=total))


def _stop_batch(db, user, batch_id):
    from services.financial import import_batches
    batch = db.get(FinancialImportBatch, batch_id)
    if batch is None:
        raise StopRefused("Unknown task.", 404)
    _authorize(db, user, batch.case_id)
    if batch.status not in _BATCH_RUNNING:
        raise StopRefused("This batch is not being prepared now.", 409)
    case_id, total, prepared = batch.case_id, len(batch.files or []), _prepared(db, batch_id)
    out = import_batches.control_batch(db, case_id=case_id, batch_id=batch_id, action="pause")
    rest = max(total - prepared, 0)
    finishing = " The statement being read now finishes first." if out.get("status") == "pausing" else ""
    return dict(case_id=case_id, name="Preparing statements for Financial",
                summary=f"{prepared} of {total} statements were prepared and stay in the batch; {rest} were not "
                        f"started and are left as they were. Resume on the batch continues them.{finishing}",
                counts=dict(prepared=prepared, total=total, not_started=rest))
