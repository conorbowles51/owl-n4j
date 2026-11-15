"""Claims an ingestion left unreviewed, per case: how many, and a request to check them (lx-citeproof D).

The check itself runs on the worker (``check_unreviewed_claims``) through app.services.claim_backfill: the ingestion
claim check, cheapest file first, stopped by the case's AI spending limit. One request per case at a time.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.services import claim_backfill

router = APIRouter()


@router.get("/cases/{case_id}/claims/unreviewed")
async def unreviewed(case_id: str, db: AsyncSession = Depends(get_db)):
    found = [c for c in await claim_backfill.unreviewed_counts(db) if c["case_id"] == case_id.lower()]
    entry = found[0] if found else {"unreviewed": 0, "files": []}
    return {"case_id": case_id, "unreviewed": entry["unreviewed"], "files": entry["files"]}


@router.post("/cases/{case_id}/claims/unreviewed/check")
async def check(case_id: str, request: Request):
    job = await request.app.state.arq_pool.enqueue_job(
        "check_unreviewed_claims", case_id.lower(), _job_id=f"claim-check-{case_id.lower()}")
    # None: a check of this case is already queued or running
    return {"case_id": case_id, "queued": job is not None}
