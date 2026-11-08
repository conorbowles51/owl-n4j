"""Failed evidence files, selected by status and counted by plain reason (lx-chunking, 8 Nov 2026).

The recovery after the OpenAI outage picked failed files by their error text, found 9 and missed the 250 of
'SB4 - Pop & Locke' that had failed for another reason. Every recovery, re-run and watch therefore selects by
``status = 'failed'`` and reports every reason it finds.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile
from services.evidence_failure_words import plain_failure


def failed_files(db: Session, case_id: uuid.UUID | None = None) -> list[tuple[uuid.UUID, uuid.UUID, str | None]]:
    """(file id, case id, stored error) of every failed file, oldest upload first."""
    query = select(EvidenceFile.id, EvidenceFile.case_id, EvidenceFile.last_error).where(
        EvidenceFile.status == "failed")
    query = query.where(EvidenceFile.deleted_at.is_(None))  # a file in the recycle bin is not waiting on anyone
    if case_id is not None:
        query = query.where(EvidenceFile.case_id == case_id)
    return [tuple(row) for row in db.execute(query.order_by(EvidenceFile.created_at, EvidenceFile.id)).all()]


def reasons_by_case(rows) -> dict[str, Counter]:
    """Per case, how many failed files have each plain reason. Every reason found is kept."""
    out: dict[str, Counter] = defaultdict(Counter)
    for _file_id, case_id, last_error in rows:
        out[str(case_id)][plain_failure(last_error) or "Failed with no reason recorded"] += 1
    return out


def report_lines(counts: Counter) -> list[str]:
    return [f"{count} x {reason}" for reason, count in counts.most_common()]


def summary(db: Session, case_id: uuid.UUID | None = None) -> dict[str, Any]:
    rows = failed_files(db, case_id)
    return {"total": len(rows), "file_ids": [str(r[0]) for r in rows], "by_case": reasons_by_case(rows)}
