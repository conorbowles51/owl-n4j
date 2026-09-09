"""Idempotent legacy authored-casework backfill used by the expand migration."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
import uuid

import sqlalchemy as sa
from sqlalchemy.engine import Connection


MIGRATION_NAMESPACE = uuid.UUID("9d3485d8-d427-4a77-ad5b-736cb89e33c5")

# PostgreSQL UUID columns are reflected as NUMERIC by SQLite. Keeping the
# backfill dialect-neutral lets us rehearse it against isolated in-memory
# databases without weakening the production PostgreSQL migration path.
SQLITE_UUID_COLUMNS: dict[str, tuple[str, ...]] = {
    "users": ("id",),
    "evidence_files": (
        "id",
        "case_id",
        "folder_id",
        "duplicate_of_id",
        "created_by_id",
        "last_processed_folder_id",
    ),
    "notebook_notes": ("id", "case_id", "author_user_id"),
    "notebook_note_links": ("id", "note_id", "case_id"),
    "workspace_notes": ("id", "case_id"),
    "workspace_findings": ("id", "case_id"),
    "workspace_theories": ("id", "case_id"),
    "workspace_entries": (
        "id",
        "case_id",
        "author_user_id",
        "updated_by_user_id",
        "source_theory_entry_id",
        "deleted_by_user_id",
    ),
    "workspace_entry_revisions": ("id", "entry_id", "case_id", "editor_user_id"),
    "workspace_entry_links": ("id", "entry_id", "case_id", "created_by_user_id"),
    "workspace_entry_events": ("id", "entry_id", "case_id", "actor_user_id"),
    "workspace_legacy_mappings": ("id", "case_id"),
    "case_profile_note_links": (
        "id",
        "profile_id",
        "case_id",
        "workspace_entry_id",
        "created_by_user_id",
    ),
    "case_profile_finding_links": (
        "id",
        "profile_id",
        "case_id",
        "workspace_entry_id",
        "created_by_user_id",
    ),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _stable_entry_id(source: str, case_id: Any, source_id: str) -> uuid.UUID:
    return uuid.uuid5(MIGRATION_NAMESPACE, f"{source}:{case_id}:{source_id}")


def _relationship(value: Any) -> str:
    normalized = (_text(value) or "unclassified").lower()
    return {
        "support": "supports",
        "supporting": "supports",
        "contradiction": "contradicts",
        "contradicting": "contradicts",
        "background": "context",
    }.get(normalized, normalized if normalized in {"unclassified", "supports", "contradicts", "context"} else "unclassified")


def _table(connection: Connection, metadata: sa.MetaData, name: str) -> sa.Table:
    typed_columns: list[sa.Column[Any]] = []
    if connection.dialect.name == "sqlite":
        typed_columns = [
            sa.Column(
                column_name,
                sa.Uuid(as_uuid=True),
                primary_key=column_name == "id",
            )
            for column_name in SQLITE_UUID_COLUMNS.get(name, ())
        ]
    return sa.Table(
        name,
        metadata,
        *typed_columns,
        autoload_with=connection,
        extend_existing=name in metadata.tables,
    )


def backfill_workspace_entries(connection: Connection) -> dict[str, Any]:
    """Backfill canonical entries and links without deleting or rewriting source rows."""

    metadata = sa.MetaData()
    entries = _table(connection, metadata, "workspace_entries")
    revisions = _table(connection, metadata, "workspace_entry_revisions")
    links = _table(connection, metadata, "workspace_entry_links")
    events = _table(connection, metadata, "workspace_entry_events")
    mappings = _table(connection, metadata, "workspace_legacy_mappings")
    notebook_notes = _table(connection, metadata, "notebook_notes")
    notebook_links = _table(connection, metadata, "notebook_note_links")
    workspace_notes = _table(connection, metadata, "workspace_notes")
    workspace_findings = _table(connection, metadata, "workspace_findings")
    workspace_theories = _table(connection, metadata, "workspace_theories")
    evidence_files = _table(connection, metadata, "evidence_files")
    users = _table(connection, metadata, "users")

    report: dict[str, Any] = {
        "schema_version": 1,
        "sources": {},
        "links": {"migrated": 0, "existing": 0, "warnings": 0},
        "profile_links": {"notes": 0, "findings": 0},
        "warnings": [],
    }
    user_ids = {row.id for row in connection.execute(sa.select(users.c.id))}
    evidence_by_case: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in connection.execute(sa.select(evidence_files)):
        case_key = str(row.case_id)
        for value in (str(row.id), getattr(row, "legacy_id", None), row.original_filename):
            if value:
                evidence_by_case[case_key][str(value)].append(str(row.id))

    existing_mapping_rows = connection.execute(sa.select(mappings)).mappings().all()
    mapping_index: dict[tuple[str, str, str], str] = {
        (str(row["case_id"]), row["source_type"], row["source_id"]): row["target_id"]
        for row in existing_mapping_rows
        if row["target_type"] == "entry"
    }
    existing_entry_ids = {
        str(value) for value in connection.execute(sa.select(entries.c.id)).scalars()
    }

    source_records: list[dict[str, Any]] = []

    def queue_source(
        *,
        source: str,
        row: Any,
        source_id_value: Any,
        entry_type: str,
        title: Any,
        body: Any,
        tags: Any,
        lifecycle_state: str | None,
        significance: str | None,
        confidence: Any,
        confidence_rationale: Any = None,
        author_user_id: Any = None,
        author_email: Any = None,
        author_name: Any = None,
        deleted_at: Any = None,
        migration_metadata: dict[str, Any] | None = None,
        needs_review: bool = False,
        preferred_entry_id: uuid.UUID | None = None,
    ) -> None:
        source_stats = report["sources"].setdefault(
            source, {"source": 0, "migrated": 0, "existing": 0, "warnings": 0}
        )
        source_stats["source"] += 1
        source_id = _text(source_id_value)
        if not source_id:
            source_id = f"__row__:{row.id}"
            needs_review = True
            source_stats["warnings"] += 1
            report["warnings"].append(
                {
                    "source": source,
                    "case_id": str(row.case_id),
                    "source_row_id": str(row.id),
                    "reason": "missing_legacy_identifier",
                }
            )
        mapping_key = (str(row.case_id), source, source_id)
        mapped_id = mapping_index.get(mapping_key)
        entry_id = preferred_entry_id or _stable_entry_id(source, row.case_id, source_id)
        if mapped_id:
            source_records.append(
                {
                    "source": source,
                    "source_id": source_id,
                    "case_id": str(row.case_id),
                    "entry_id": mapped_id,
                    "row": row,
                }
            )
            source_stats["existing"] += 1
            return
        if str(entry_id) in existing_entry_ids:
            target_id = str(entry_id)
            connection.execute(
                mappings.insert().values(
                    id=uuid.uuid4(),
                    case_id=row.case_id,
                    source_type=source,
                    source_id=source_id,
                    target_type="entry",
                    target_id=target_id,
                    migration_state="migrated",
                    warning=None,
                    metadata={},
                    created_at=_now(),
                )
            )
            mapping_index[mapping_key] = target_id
            source_records.append(
                {
                    "source": source,
                    "source_id": source_id,
                    "case_id": str(row.case_id),
                    "entry_id": target_id,
                    "row": row,
                }
            )
            source_stats["existing"] += 1
            return

        normalized_title = _text(title)
        normalized_body = str(body) if body is not None else ""
        normalized_tags = [str(item).strip()[:64] for item in _list(tags) if _text(item)][:20]
        metadata_value = dict(migration_metadata or {})
        if entry_type != "note" and not normalized_title:
            needs_review = True
            metadata_value["missing_title"] = True
        normalized_confidence = confidence if isinstance(confidence, int) and not isinstance(confidence, bool) and 0 <= confidence <= 100 else None
        if confidence is not None and normalized_confidence is None:
            needs_review = True
            metadata_value["original_confidence"] = confidence
        normalized_author_id = _uuid(author_user_id)
        if normalized_author_id not in user_ids:
            if author_user_id is not None:
                metadata_value["original_author_id"] = str(author_user_id)
            normalized_author_id = None
        created_at = row.created_at or _now()
        updated_at = row.updated_at or created_at
        target_id = str(entry_id)
        connection.execute(
            entries.insert().values(
                id=entry_id,
                case_id=row.case_id,
                entry_type=entry_type,
                title=normalized_title,
                body=normalized_body,
                tags=normalized_tags,
                lifecycle_state=lifecycle_state,
                significance=significance,
                confidence=normalized_confidence,
                confidence_rationale=_text(confidence_rationale),
                review_state="accepted",
                author_user_id=normalized_author_id,
                author_email=_text(author_email),
                author_name=_text(author_name),
                updated_by_user_id=normalized_author_id,
                updated_by_email=_text(author_email),
                updated_by_name=_text(author_name),
                version=1,
                source_theory_entry_id=None,
                legacy_source=source,
                legacy_id=source_id,
                migration_metadata=metadata_value,
                needs_migration_review=needs_review,
                deleted_at=deleted_at,
                deleted_by_user_id=None,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            revisions.insert().values(
                id=uuid.uuid4(),
                entry_id=entry_id,
                case_id=row.case_id,
                revision_number=1,
                entry_type=entry_type,
                title=normalized_title,
                body=normalized_body,
                tags=normalized_tags,
                lifecycle_state=lifecycle_state,
                significance=significance,
                confidence=normalized_confidence,
                confidence_rationale=_text(confidence_rationale),
                review_state="accepted",
                editor_user_id=normalized_author_id,
                editor_email=_text(author_email),
                editor_name=_text(author_name),
                created_at=created_at,
            )
        )
        connection.execute(
            events.insert().values(
                id=uuid.uuid4(),
                entry_id=entry_id,
                case_id=row.case_id,
                event_type="migrated",
                before_state={},
                after_state={
                    "version": 1,
                    "entry_type": entry_type,
                    "lifecycle_state": lifecycle_state,
                    "significance": significance,
                    "confidence": normalized_confidence,
                },
                rationale=f"Migrated from {source}",
                actor_user_id=None,
                actor_email=None,
                actor_name=None,
                created_at=created_at,
            )
        )
        connection.execute(
            mappings.insert().values(
                id=uuid.uuid4(),
                case_id=row.case_id,
                source_type=source,
                source_id=source_id,
                target_type="entry",
                target_id=target_id,
                migration_state="needs_review" if needs_review else "migrated",
                warning="Review migrated source fields" if needs_review else None,
                metadata={"source_row_id": str(row.id)},
                created_at=created_at,
            )
        )
        mapping_index[mapping_key] = target_id
        existing_entry_ids.add(target_id)
        source_records.append(
            {
                "source": source,
                "source_id": source_id,
                "case_id": str(row.case_id),
                "entry_id": target_id,
                "row": row,
            }
        )
        source_stats["migrated"] += 1

    for row in connection.execute(sa.select(notebook_notes)):
        queue_source(
            source="notebook_note",
            row=row,
            source_id_value=str(row.id),
            entry_type="note",
            title=row.title,
            body=row.body,
            tags=row.tags,
            lifecycle_state=None,
            significance=None,
            confidence=None,
            author_user_id=row.author_user_id,
            author_email=row.author_email,
            author_name=row.author_name,
            deleted_at=row.deleted_at,
            migration_metadata={
                "legacy_visibility": row.visibility
            } if row.visibility and row.visibility != "case" else {},
            preferred_entry_id=row.id,
        )

    for row in connection.execute(sa.select(workspace_notes)):
        data = _json(row.data)
        queue_source(
            source="workspace_note",
            row=row,
            source_id_value=row.note_id,
            entry_type="note",
            title=data.get("title"),
            body=data.get("content", data.get("body", "")),
            tags=data.get("tags"),
            lifecycle_state=None,
            significance=None,
            confidence=None,
            author_user_id=data.get("author_user_id") or data.get("author_id"),
            author_email=data.get("author_email"),
            author_name=data.get("author_name"),
            migration_metadata={
                "legacy_record_id": str(row.id),
                "legacy_fields": {
                    key: value
                    for key, value in data.items()
                    if key not in {"title", "content", "body", "tags", "author_user_id", "author_id", "author_email", "author_name"}
                },
            },
            needs_review=not bool(_text(data.get("content", data.get("body")))),
        )

    for row in connection.execute(sa.select(workspace_findings)):
        data = _json(row.data)
        raw_significance = (_text(data.get("significance") or data.get("priority")) or "").lower()
        significance = raw_significance if raw_significance in {"high", "medium", "low"} else None
        queue_source(
            source="workspace_finding",
            row=row,
            source_id_value=row.finding_id,
            entry_type="finding",
            title=data.get("title"),
            body=data.get("content", data.get("body", "")),
            tags=data.get("tags"),
            lifecycle_state="active",
            significance=significance,
            confidence=None,
            author_user_id=data.get("author_user_id") or data.get("author_id"),
            author_email=data.get("author_email"),
            author_name=data.get("author_name"),
            migration_metadata={
                "legacy_record_id": str(row.id),
                "original_priority": data.get("priority"),
            },
            needs_review=significance is None,
        )

    for row in connection.execute(sa.select(workspace_theories)):
        data = _json(row.data)
        queue_source(
            source="workspace_theory",
            row=row,
            source_id_value=row.theory_id,
            entry_type="theory",
            title=data.get("title"),
            body=data.get("hypothesis", data.get("content", data.get("body", ""))),
            tags=data.get("tags"),
            lifecycle_state="proposed",
            significance=None,
            confidence=data.get("confidence_score", data.get("confidence")),
            confidence_rationale=data.get("confidence_rationale"),
            author_user_id=data.get("author_user_id") or data.get("author_id"),
            author_email=data.get("author_email"),
            author_name=data.get("author_name"),
            migration_metadata={
                "legacy_record_id": str(row.id),
                "legacy_theory_type": data.get("type"),
                "legacy_privilege_label": data.get("privilege_level"),
                "supporting_evidence_text": data.get("supporting_evidence"),
                "counter_arguments": data.get("counter_arguments"),
                "next_steps": data.get("next_steps"),
                "attached_snapshot_ids": data.get("attached_snapshot_ids"),
            },
        )

    existing_link_keys = {
        (str(row.entry_id), row.target_type, row.target_id)
        for row in connection.execute(sa.select(links))
    }

    def normalize_evidence(case_id: Any, value: Any) -> tuple[str, bool]:
        original = str(value)
        candidates = evidence_by_case[str(case_id)].get(original, [])
        if len(candidates) == 1:
            return candidates[0], False
        return original, True

    def insert_link(
        *,
        entry_id: str,
        case_id: Any,
        target_type: str,
        target_id: Any,
        target_label: Any = None,
        relationship: Any = None,
        source_anchor: Any = None,
        metadata_value: Any = None,
        created_by_user_id: Any = None,
        created_at: Any = None,
        updated_at: Any = None,
        unresolved: bool = False,
    ) -> None:
        value = _text(target_id)
        if not value:
            report["links"]["warnings"] += 1
            return
        link_key = (entry_id, target_type, value)
        if link_key in existing_link_keys:
            report["links"]["existing"] += 1
            return
        metadata_dict = dict(metadata_value) if isinstance(metadata_value, dict) else {}
        if unresolved:
            metadata_dict["migration_unresolved"] = True
            report["links"]["warnings"] += 1
            report["warnings"].append(
                {
                    "source": "workspace_entry_link",
                    "case_id": str(case_id),
                    "entry_id": entry_id,
                    "target_type": target_type,
                    "target_id": value,
                    "reason": "unresolved_target",
                }
            )
        actor_id = _uuid(created_by_user_id)
        if actor_id not in user_ids:
            actor_id = None
        connection.execute(
            links.insert().values(
                id=uuid.uuid4(),
                entry_id=uuid.UUID(entry_id),
                case_id=case_id,
                target_type=target_type,
                target_id=value,
                target_label=_text(target_label),
                relationship=_relationship(relationship),
                source_anchor=source_anchor if isinstance(source_anchor, dict) else {},
                metadata=metadata_dict,
                created_by_user_id=actor_id,
                created_at=created_at or _now(),
                updated_at=updated_at or created_at or _now(),
            )
        )
        existing_link_keys.add(link_key)
        report["links"]["migrated"] += 1

    notebook_entry_by_id = {
        source_id: target_id
        for (case_key, source_type, source_id), target_id in mapping_index.items()
        if source_type == "notebook_note"
    }
    for row in connection.execute(sa.select(notebook_links)):
        entry_id = notebook_entry_by_id.get(str(row.note_id))
        if not entry_id:
            report["links"]["warnings"] += 1
            continue
        target_type = {
            "entity": "graph_entity",
            "document": "evidence",
        }.get(row.target_type, row.target_type)
        target_id = row.target_id
        metadata_value = _json(row.metadata)
        unresolved = False
        if target_type == "evidence":
            target_id, unresolved = normalize_evidence(row.case_id, row.target_id)
        insert_link(
            entry_id=entry_id,
            case_id=row.case_id,
            target_type=target_type,
            target_id=target_id,
            target_label=row.target_label,
            relationship=metadata_value.get("relationship"),
            source_anchor=metadata_value.get("source_anchor"),
            metadata_value=metadata_value,
            created_at=row.created_at,
            updated_at=row.updated_at,
            unresolved=unresolved,
        )

    record_lookup = {
        (item["source"], item["case_id"], item["source_id"]): item
        for item in source_records
    }
    for (case_key, source_type, source_id), entry_id in list(mapping_index.items()):
        item = record_lookup.get((source_type, case_key, source_id))
        if not item or source_type not in {"workspace_note", "workspace_finding", "workspace_theory"}:
            continue
        row = item["row"]
        data = _json(row.data)
        evidence_fields = (
            "linked_evidence_ids",
            "linked_document_ids",
            "attached_evidence_ids",
            "attached_document_ids",
        )
        for field in evidence_fields:
            for value in _list(data.get(field)):
                target_id, unresolved = normalize_evidence(row.case_id, value)
                insert_link(
                    entry_id=entry_id,
                    case_id=row.case_id,
                    target_type="evidence",
                    target_id=target_id,
                    metadata_value={"legacy_field": field, "legacy_target_id": str(value)},
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    unresolved=unresolved,
                )
        for field in ("linked_entity_keys", "attached_entity_keys"):
            for value in _list(data.get(field)):
                insert_link(
                    entry_id=entry_id,
                    case_id=row.case_id,
                    target_type="graph_entity",
                    target_id=value,
                    metadata_value={"legacy_field": field},
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
        attached_graph = _json(data.get("attached_graph_data"))
        for value in _list(attached_graph.get("entity_keys")):
            insert_link(
                entry_id=entry_id,
                case_id=row.case_id,
                target_type="graph_entity",
                target_id=value,
                metadata_value={"legacy_field": "attached_graph_data.entity_keys"},
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        for value in _list(data.get("attached_note_ids")):
            mapped_note = mapping_index.get((case_key, "workspace_note", str(value)))
            insert_link(
                entry_id=entry_id,
                case_id=row.case_id,
                target_type="entry",
                target_id=mapped_note or value,
                metadata_value={"legacy_field": "attached_note_ids", "legacy_target_id": str(value)},
                created_at=row.created_at,
                updated_at=row.updated_at,
                unresolved=mapped_note is None,
            )
        for field, target_type in (("attached_task_ids", "task"), ("attached_witness_ids", "witness")):
            for value in _list(data.get(field)):
                insert_link(
                    entry_id=entry_id,
                    case_id=row.case_id,
                    target_type=target_type,
                    target_id=value,
                    metadata_value={"legacy_field": field, "migration_unresolved": True},
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    unresolved=True,
                )

    for table_name, source_type, counter_name in (
        ("case_profile_note_links", "workspace_note", "notes"),
        ("case_profile_finding_links", "workspace_finding", "findings"),
    ):
        profile_links = _table(connection, metadata, table_name)
        legacy_column = profile_links.c.note_id if counter_name == "notes" else profile_links.c.finding_id
        for row in connection.execute(sa.select(profile_links)):
            source_id = getattr(row, legacy_column.name)
            target_id = mapping_index.get((str(row.case_id), source_type, source_id))
            if not target_id or row.workspace_entry_id is not None:
                continue
            connection.execute(
                profile_links.update()
                .where(profile_links.c.id == row.id)
                .values(workspace_entry_id=uuid.UUID(target_id))
            )
            report["profile_links"][counter_name] += 1

    report["summary"] = {
        "source_records": sum(item["source"] for item in report["sources"].values()),
        "migrated_entries": sum(item["migrated"] for item in report["sources"].values()),
        "existing_entries": sum(item["existing"] for item in report["sources"].values()),
        "migrated_links": report["links"]["migrated"],
        "warnings": len(report["warnings"]),
    }
    return report
