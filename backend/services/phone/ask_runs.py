"""Keeping questions asked of the phones: start one (answered in the background), read it, list a case's earlier
questions (lx-phoneask D).

An answer takes about a minute (measured 52 s on the synthetic Halloran case, 25 Nov), longer than a page should
wait on one request, so the question is saved as running and answered on a thread; the page reads it until it is
done. A release restart ends the thread: a question still running after ``STALE_S`` reads as stopped, with why.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, select

from postgres.models.phone_ask import PhoneAsk

logger = logging.getLogger(__name__)

STALE_S = 15 * 60
MAX_QUESTION = 1000
LIST_LIMIT = 20


class AskError(ValueError):
    status = 422


def _stale(row: PhoneAsk, now: datetime) -> bool:
    at = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
    return row.status == "running" and now - at > timedelta(seconds=STALE_S)


def view(row: PhoneAsk, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    status, error = row.status, row.error
    if _stale(row, now):
        status, error = "failed", ("This question stopped before it was answered (the server restarted). Ask it "
                                   "again.")
    return {"id": str(row.id), "case_id": str(row.case_id), "question": row.question, "phones": row.phones or [],
            "status": status, "error": error, "answer": row.answer if status == "done" else None,
            "cost_usd": float(row.cost_usd) if row.cost_usd is not None else None,
            "seconds": float(row.seconds) if row.seconds is not None else None,
            "asked_by_name": row.asked_by_name, "created_at": row.created_at.isoformat() if row.created_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None}


def start(db, *, case_id, question: str, phones: list[str] | None, user, run: bool = True,
          answer: Callable | None = None) -> dict[str, Any]:
    """Save the question as running and answer it on a thread (``run=False``: save only, for tests)."""
    q = (question or "").strip()
    if not q:
        raise AskError("Write a question first.")
    if len(q) > MAX_QUESTION:
        raise AskError("A question can be up to %d characters; this one has %d." % (MAX_QUESTION, len(q)))
    now = datetime.now(timezone.utc)
    if user is not None:
        busy = db.execute(select(PhoneAsk).where(PhoneAsk.case_id == case_id, PhoneAsk.asked_by == user.id,
                                                 PhoneAsk.status == "running")).scalars().all()
        if any(not _stale(b, now) for b in busy):
            err = AskError("Your last question in this case is still being answered. Wait for it, then ask again.")
            err.status = 409
            raise err
    row = PhoneAsk(id=uuid.uuid4(), case_id=case_id, question=q, phones=[str(p) for p in (phones or [])],
                   status="running", asked_by=getattr(user, "id", None),
                   asked_by_name=(getattr(user, "name", None) or getattr(user, "email", None) or "")[:300],
                   created_at=now)
    db.add(row)
    db.commit()
    out = view(row, now)
    if run:
        threading.Thread(target=_answer, args=(row.id, case_id, q, row.phones or None, getattr(user, "id", None),
                                               answer), name="phone-ask-%s" % str(row.id)[:8], daemon=True).start()
    return out


def _answer(ask_id, case_id, question, phones, user_id, answer: Callable | None = None) -> None:
    from postgres.models.cost_record import CostJobType
    from postgres.session import get_background_session
    from services.ai_costs_service import ai_cost_context
    from services.phone import ask as A
    result, error = None, None
    try:
        with ai_cost_context(job_type=CostJobType.AI_ASSISTANT, case_id=case_id, user_id=user_id,
                             description="Phone question", extra_metadata={"phone_ask_id": str(ask_id)},
                             meter_calls=True):
            with get_background_session() as db:
                result = (answer or A.ask)(db.connection(), case_id, question, phones=phones)
                db.rollback()
    except Exception as exc:  # noqa: BLE001 - the row says it failed and why; nothing is shown as an answer
        logger.exception("Phone question %s failed", ask_id)
        error = "The question could not be answered (%s). Ask it again." % type(exc).__name__
    finish(ask_id, result, error)


def finish(ask_id, result: dict | None, error: str | None) -> None:
    from postgres.session import get_background_session
    with get_background_session() as db:
        row = db.get(PhoneAsk, ask_id)
        if row is None:
            return
        row.finished_at = datetime.now(timezone.utc)
        if result is not None:
            row.answer = json.loads(json.dumps(result, default=str))
            row.status = "done"
            row.error = result.get("error")
            row.cost_usd = (result.get("usage") or {}).get("usd")
            row.seconds = (result.get("seconds") or {}).get("total")
        else:
            row.status, row.error = "failed", error
        db.commit()


def read(db, case_id, ask_id) -> dict[str, Any] | None:
    row = db.get(PhoneAsk, ask_id)
    if row is None or str(row.case_id) != str(case_id):
        return None
    return view(row)


def earlier(db, case_id, *, offset: int = 0, limit: int = LIST_LIMIT) -> dict[str, Any]:
    """The case's questions, newest first, every one counted (``total``) and paged."""
    offset, limit = max(0, int(offset)), max(1, min(int(limit), 100))
    total = db.execute(select(func.count()).select_from(PhoneAsk).where(PhoneAsk.case_id == case_id)).scalar_one()
    rows = db.execute(select(PhoneAsk).where(PhoneAsk.case_id == case_id)
                      .order_by(PhoneAsk.created_at.desc(), PhoneAsk.id).offset(offset).limit(limit)).scalars().all()
    now = datetime.now(timezone.utc)
    items = []
    for r in rows:
        v = view(r, now)
        items.append({k: v[k] for k in ("id", "question", "status", "asked_by_name", "created_at")}
                     | {"statements": len((r.answer or {}).get("statements") or []) if v["status"] == "done" else None})
    nxt = offset + len(items) if offset + len(items) < total else None
    return {"total": int(total), "shown": len(items), "offset": offset, "next_offset": nxt, "items": items}
