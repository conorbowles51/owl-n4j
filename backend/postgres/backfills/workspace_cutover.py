"""Idempotent Phase 8 cleanup backfills for canonical Workspace data."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import DossierLink
from postgres.models.evidence import EvidenceFile
from postgres.models.work import CaseTask
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
    WorkspaceEntryRevision,
)


HISTORY_NAMESPACE = uuid.UUID("0ea8e78c-81ea-4d22-bbf0-a673709f6963")


def _stable(kind: str, source_id: Any) -> uuid.UUID:
    return uuid.uuid5(HISTORY_NAMESPACE, f"{kind}:{source_id}")


def _entry_snapshot(row: Any) -> dict[str, Any]:
    return {
        "entry_type": row.entry_type,
        "title": row.title,
        "body": row.body,
        "tags": row.tags or [],
        "lifecycle_state": row.lifecycle_state,
        "significance": row.significance,
        "confidence": row.confidence,
        "confidence_rationale": row.confidence_rationale,
        "review_state": row.review_state,
        "version": row.version,
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


def backfill_missing_entry_history(
    connection: Connection, *, case_ids: Iterable[uuid.UUID] | None = None
) -> dict[str, int]:
    """Create one truthful recovery snapshot for entries lacking all history."""
    entries = WorkspaceEntry.__table__
    revisions = WorkspaceEntryRevision.__table__
    events = WorkspaceEntryEvent.__table__
    entry_query = sa.select(entries)
    scoped_case_ids = tuple(case_ids or ())
    if scoped_case_ids:
        entry_query = entry_query.where(entries.c.case_id.in_(scoped_case_ids))
    rows = list(connection.execute(entry_query).mappings())
    revision_entry_ids = set(connection.execute(sa.select(revisions.c.entry_id)).scalars())
    event_entry_ids = set(connection.execute(sa.select(events.c.entry_id)).scalars())
    report = {"entries": len(rows), "revisions_created": 0, "events_created": 0}

    for row in rows:
        created_at = row.created_at or datetime.now(timezone.utc)
        if row.id not in revision_entry_ids:
            connection.execute(
                revisions.insert().values(
                    id=_stable("entry-recovery-revision", row.id),
                    entry_id=row.id,
                    case_id=row.case_id,
                    revision_number=max(1, int(row.version or 1)),
                    entry_type=row.entry_type,
                    title=row.title,
                    body=row.body,
                    tags=row.tags or [],
                    lifecycle_state=row.lifecycle_state,
                    significance=row.significance,
                    confidence=row.confidence,
                    confidence_rationale=row.confidence_rationale,
                    review_state=row.review_state,
                    editor_user_id=row.updated_by_user_id or row.author_user_id,
                    editor_email=row.updated_by_email or row.author_email,
                    editor_name=row.updated_by_name or row.author_name,
                    created_at=created_at,
                )
            )
            report["revisions_created"] += 1
        if row.id not in event_entry_ids:
            connection.execute(
                events.insert().values(
                    id=_stable("entry-recovery-event", row.id),
                    entry_id=row.id,
                    case_id=row.case_id,
                    event_type="migrated" if row.legacy_source else "created",
                    before_state={},
                    after_state=_entry_snapshot(row),
                    rationale="Phase 8 recovery snapshot for an entry that had no history rows",
                    actor_user_id=row.updated_by_user_id or row.author_user_id,
                    actor_email=row.updated_by_email or row.author_email,
                    actor_name=row.updated_by_name or row.author_name,
                    created_at=created_at,
                )
            )
            report["events_created"] += 1
    return report


def resolve_repointed_entry_link_markers(connection: Connection) -> dict[str, int]:
    """Clear migration-unresolved markers only when the canonical target exists."""
    links = WorkspaceEntryLink.__table__
    target_tables = {
        "entry": WorkspaceEntry.__table__,
        "dossier": CaseProfile.__table__,
        "task": CaseTask.__table__,
        "deadline": CaseDeadline.__table__,
        "evidence": EvidenceFile.__table__,
    }
    scanned = resolved = 0
    for row in connection.execute(sa.select(links)).mappings():
        metadata = dict(row.metadata or {})
        if not metadata.get("migration_unresolved"):
            continue
        scanned += 1
        target_table = target_tables.get(row.target_type)
        if target_table is None:
            continue
        try:
            target_id = uuid.UUID(str(row.target_id))
        except (TypeError, ValueError):
            continue
        target = connection.execute(
            sa.select(target_table.c.id).where(
                target_table.c.id == target_id,
                target_table.c.case_id == row.case_id,
            )
        ).scalar_one_or_none()
        if target is None:
            continue
        metadata["migration_unresolved"] = False
        metadata["migration_resolution"] = "canonical_target_verified"
        connection.execute(
            links.update().where(links.c.id == row.id).values(metadata=metadata)
        )
        resolved += 1
    return {"markers_scanned": scanned, "markers_resolved": resolved}


def backfill_legacy_evidence_dossier_links(
    connection: Connection, *, case_ids: Iterable[uuid.UUID] | None = None
) -> dict[str, int]:
    """Copy historical evidence/profile associations into canonical Dossier links.

    The legacy JSON array remains untouched as recoverable source data. Invalid,
    missing, and cross-case references are counted for reconciliation rather than
    silently discarded.
    """
    evidence = EvidenceFile.__table__
    dossiers = CaseProfile.__table__
    links = DossierLink.__table__
    scoped_case_ids = tuple(case_ids or ())
    evidence_query = sa.select(evidence)
    if scoped_case_ids:
        evidence_query = evidence_query.where(evidence.c.case_id.in_(scoped_case_ids))

    dossier_cases = {
        dossier_id: case_id
        for dossier_id, case_id in connection.execute(
            sa.select(dossiers.c.id, dossiers.c.case_id)
        ).all()
    }
    existing = {
        (dossier_id, target_id)
        for dossier_id, target_id in connection.execute(
            sa.select(links.c.dossier_id, links.c.target_id).where(
                links.c.target_type == "evidence"
            )
        ).all()
    }
    report = {
        "evidence_files_scanned": 0,
        "source_links": 0,
        "links_created": 0,
        "links_already_present": 0,
        "unresolved_links": 0,
    }

    for row in connection.execute(evidence_query).mappings():
        report["evidence_files_scanned"] += 1
        seen: set[str] = set()
        for raw_profile_id in row.linked_entity_ids or []:
            source_id = str(raw_profile_id).strip()
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            report["source_links"] += 1
            try:
                dossier_id = uuid.UUID(source_id)
            except (TypeError, ValueError):
                report["unresolved_links"] += 1
                continue
            if dossier_cases.get(dossier_id) != row.case_id:
                report["unresolved_links"] += 1
                continue
            key = (dossier_id, str(row.id))
            if key in existing:
                report["links_already_present"] += 1
                continue
            connection.execute(
                links.insert().values(
                    id=_stable("legacy-evidence-dossier-link", f"{dossier_id}:{row.id}"),
                    dossier_id=dossier_id,
                    case_id=row.case_id,
                    target_type="evidence",
                    target_id=str(row.id),
                    relationship_type="linked evidence",
                    label=row.original_filename,
                    source_anchor={"legacy_source": "evidence_files.linked_entity_ids"},
                    created_by_user_id=row.created_by_id,
                    created_at=row.created_at or datetime.now(timezone.utc),
                    updated_at=row.updated_at or row.created_at or datetime.now(timezone.utc),
                )
            )
            existing.add(key)
            report["links_created"] += 1
    return report


def run_workspace_cutover_backfills(
    connection: Connection, *, case_ids: Iterable[uuid.UUID] | None = None
) -> dict[str, Any]:
    return {
        "entry_history": backfill_missing_entry_history(connection, case_ids=case_ids),
        "entry_link_markers": resolve_repointed_entry_link_markers(connection),
        "legacy_evidence_dossier_links": backfill_legacy_evidence_dossier_links(
            connection, case_ids=case_ids
        ),
    }
