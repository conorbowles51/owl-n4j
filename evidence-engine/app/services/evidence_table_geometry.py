"""Persist extracted table geometry so the click-through path survives the job.

PDF extraction builds ``doc.metadata["table_geometry"]["per_table"]``: one
entry per extracted table, each carrying the table's own rectangle and a
locator for every cell value.  Until this service existed that list died with
the job -- the quality report keeps only its summary counts, and job metadata
is never written anywhere durable.  The backend's transaction read path needs
the cell locators to answer "where on the page is this figure", so the
geometry has to outlive the worker that computed it.

Storage is one row per (evidence file, page), holding the geometry-bearing
entries whose table rectangle landed on that page.  Per-page rows are the
bounding the extraction docstring asked for: the read path always knows which
page it is asking about, and a statement covering a year of a busy account
never becomes a single unbounded JSONB value.

Entries without geometry are not stored.  They carry no page and nothing
drawable, so there is no row to put them in -- but they are not silently
forgotten either: the extraction quality report already counts them, and this
service reports how many it skipped so the orchestrator can log the number
rather than infer it from absence.

Replace, not merge.  A re-process may find fewer tables or fewer pages than
the last run, and a stale page surviving beside fresh ones would be geometry
for a reading that no longer exists.  Delete-then-insert inside one commit
makes the stored geometry always describe exactly one extraction run.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import EvidenceTableGeometry


@dataclass(frozen=True)
class GeometryPersistenceResult:
    """What one persistence run did, in numbers the orchestrator can log."""

    pages_written: int
    entries_written: int
    entries_without_geometry: int
    entries_invalid: int

    @property
    def wrote_anything(self) -> bool:
        return self.pages_written > 0


def group_per_table_by_page(
    metadata: dict[str, Any] | None,
    commit: bool = True,
) -> tuple[dict[int, list[dict[str, Any]]], int, int]:
    """Group geometry-bearing ``per_table`` entries by the page they sit on.

    Returns ``(by_page, without_geometry, invalid)``.  An entry belongs to the
    page its table rectangle reports (``entry["table"]["page"]``).  Entries
    with no ``table`` key are the documented geometry-less case and are
    counted, not stored.  Entries whose shape is neither of those things are
    counted as invalid rather than raised on: geometry is auxiliary to the
    job, and failing an ingestion over a malformed rectangle would cost the
    text and the transactions to save a highlight.
    """
    table_geometry = (metadata or {}).get("table_geometry") or {}
    per_table = table_geometry.get("per_table") or []

    by_page: dict[int, list[dict[str, Any]]] = {}
    without_geometry = 0
    invalid = 0
    for entry in per_table:
        if not isinstance(entry, dict):
            invalid += 1
            continue
        table = entry.get("table")
        if table is None:
            without_geometry += 1
            continue
        page = table.get("page") if isinstance(table, dict) else None
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            invalid += 1
            continue
        by_page.setdefault(page, []).append(entry)
    return by_page, without_geometry, invalid


async def replace_evidence_table_geometry(
    db: AsyncSession,
    *,
    evidence_file_id: uuid.UUID | str,
    engine_job_id: uuid.UUID | str | None,
    metadata: dict[str, Any] | None,
    commit: bool = True,
) -> GeometryPersistenceResult:
    """Replace the stored geometry for one evidence file with this run's.

    The delete runs even when this run produced no geometry, because a file
    re-processed into a form with no tables must not keep last run's
    rectangles.  Everything happens in one commit so a failure partway leaves
    the previous state readable rather than a half-replaced one.
    """
    evidence_uuid = uuid.UUID(str(evidence_file_id))
    job_uuid = uuid.UUID(str(engine_job_id)) if engine_job_id else None

    by_page, without_geometry, invalid = group_per_table_by_page(metadata)

    await db.execute(
        delete(EvidenceTableGeometry).where(
            EvidenceTableGeometry.evidence_file_id == evidence_uuid
        )
    )
    entries_written = 0
    for page in sorted(by_page):
        entries = by_page[page]
        await db.execute(
            insert(EvidenceTableGeometry).values(
                evidence_file_id=evidence_uuid,
                page_number=page,
                engine_job_id=job_uuid,
                payload=entries,
            )
        )
        entries_written += len(entries)
    if commit:
        await db.commit()

    return GeometryPersistenceResult(
        pages_written=len(by_page),
        entries_written=entries_written,
        entries_without_geometry=without_geometry,
        entries_invalid=invalid,
    )
