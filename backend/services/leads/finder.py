"""The lead finder (lx-leads D). Filled in below the run bookkeeping."""
from __future__ import annotations

from typing import Any


def last_run(db, case_id) -> dict[str, Any]:
    from sqlalchemy import select
    from postgres.models.corroborate import LeadFinderRun
    import uuid
    r = db.scalars(select(LeadFinderRun).where(LeadFinderRun.case_id == uuid.UUID(str(case_id)))
                   .order_by(LeadFinderRun.started_at.desc())).first()
    if r is None:
        return {"status": "never", "words": "Loupe has not looked for leads in this case yet."}
    return {"id": str(r.id), "status": r.status, "step": r.step, "trigger": r.trigger, "counts": r.counts or {},
            "error": r.error, "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None}


def start(db, case_id, *, user=None) -> dict[str, Any]:
    raise NotImplementedError
