"""The AI spending limits, read by the engine: the same saved setting and the same cost records as the backend's
services/ai_budget.py, which owns the setting, the refusal of new runs and the alerts.

A batch already running is not cut off inside a file: it is checked before each file starts, so files being read finish
and are checkpointed, and the batch then pauses (paused, resumable, status pending) with the reason on its jobs. Resume,
after the limit is raised, reuses every saved model answer at no new cost. No file is dropped. With no limit saved no
spend is read.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text, update

from app.dependencies import async_session
from app.models.cost_tracking import CostRecord
from app.models.job import Job, JobStatus
from app.services.ingestion_checkpoints import IngestionPaused

logger = logging.getLogger(__name__)

SETTINGS_KEY = "ai_budget"


def _number(value) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def hold_sentence(scope: str, spent: float, limit: float) -> str:
    where = "this case's AI spending limit" if scope == "case" else "this month's AI spending limit"
    return (f"Held: {where} is reached, ${spent:,.2f} spent of the ${limit:,.2f} limit. Nothing is lost: "
            "resume after an administrator raises the limit on the AI costs page.")


async def limit_reached(case_id: str) -> str | None:
    """The sentence to show when a limit stops new work for this case, else None. Unreadable: None, logged."""
    try:
        async with async_session() as db:
            stored = await db.scalar(text("SELECT configuration FROM ai_model_policies WHERE key = :key"),
                                     {"key": SETTINGS_KEY})
            stored = stored if isinstance(stored, dict) else {}
            limits = [_number(stored.get("case_limit_usd")),
                      _number((stored.get("case_limits") or {}).get(str(case_id).lower()))]
            limits = [limit for limit in limits if limit is not None]
            if limits:
                spent = float(await db.scalar(select(func.coalesce(func.sum(CostRecord.cost_usd), 0)).where(
                    CostRecord.case_id == uuid.UUID(str(case_id)))) or 0)
                if spent >= min(limits):
                    return hold_sentence("case", spent, min(limits))
            month_limit = _number(stored.get("month_limit_usd"))
            if month_limit is not None:
                start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                spent = float(await db.scalar(select(func.coalesce(func.sum(CostRecord.cost_usd), 0)).where(
                    CostRecord.created_at >= start)) or 0)
                if spent >= month_limit:
                    return hold_sentence("month", spent, month_limit)
    except Exception:  # noqa: BLE001 - as the backend: an unreadable limit is no limit
        logger.exception("AI budget could not be read; the work goes on")
    return None


async def hold_if_reached(case_id: str, predicate) -> None:
    """Pause this batch or job here, with the reason on it, when a limit is reached."""
    reason = await limit_reached(case_id)
    if reason is None:
        return
    async with async_session() as db:
        await db.execute(update(Job).where(predicate, Job.case_id == case_id, Job.status != JobStatus.COMPLETED)
                         .values(error_message=reason))
        await db.commit()
    logger.warning("Holding work of case %s: %s", case_id, reason)
    raise IngestionPaused()
