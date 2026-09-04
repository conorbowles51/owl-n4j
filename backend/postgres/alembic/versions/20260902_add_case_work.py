"""add normalised case work and shared evidence pins

Revision ID: 20260902_case_work
Revises: 20260901_case_context
Create Date: 2026-09-02
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timezone
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260902_case_work"
down_revision: Union[str, None] = "20260901_case_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
NAMESPACE = uuid.UUID("ee08489a-ae88-4eb6-a5d6-50500d6cb342")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(text[:10]), time.min, tzinfo=timezone.utc)
        except ValueError:
            return None


def _as_date(value: Any) -> date | None:
    parsed = _as_datetime(value)
    return parsed.date() if parsed else None


def _stable(kind: str, case_id: Any, source_id: Any) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{case_id}:{source_id}")


def _create_schema() -> None:
    op.create_table(
        "case_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="todo", nullable=False),
        sa.Column("priority", sa.String(32), server_default="standard", nullable=False),
        sa.Column("assignee_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_task_id", UUID, sa.ForeignKey("case_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deadline_id", UUID, sa.ForeignKey("case_deadlines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_id", sa.String(255), nullable=True),
        sa.Column("migration_metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("needs_migration_review", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('todo', 'in_progress', 'done')", name="ck_case_tasks_status"),
        sa.CheckConstraint("priority IN ('low', 'standard', 'high', 'urgent')", name="ck_case_tasks_priority"),
        sa.CheckConstraint("parent_task_id IS NULL OR parent_task_id <> id", name="ck_case_tasks_not_self_parent"),
        sa.UniqueConstraint("case_id", "legacy_id", name="uq_case_tasks_legacy_identity"),
    )
    op.create_index("ix_case_tasks_case_status_due", "case_tasks", ["case_id", "status", "due_at"])
    op.create_index("ix_case_tasks_case_assignee_due", "case_tasks", ["case_id", "assignee_user_id", "due_at"])
    op.create_index("ix_case_tasks_case_parent", "case_tasks", ["case_id", "parent_task_id"])
    op.create_index("ix_case_tasks_case_deleted", "case_tasks", ["case_id", "deleted_at"])

    op.create_table(
        "case_task_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("task_id", UUID, sa.ForeignKey("case_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(512), nullable=False),
        sa.Column("label", sa.String(512), nullable=True),
        sa.Column("source_anchor", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("target_type IN ('dossier', 'entry', 'evidence')", name="ck_case_task_links_target_type"),
        sa.UniqueConstraint("task_id", "target_type", "target_id", name="uq_case_task_link_target"),
    )
    op.create_index("ix_case_task_links_task_id", "case_task_links", ["task_id"])
    op.create_index("ix_case_task_links_case_id", "case_task_links", ["case_id"])
    op.create_index("ix_case_task_links_case_target", "case_task_links", ["case_id", "target_type", "target_id"])

    op.create_table(
        "shared_evidence_pins",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_file_id", UUID, sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pinned_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("legacy_metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("case_id", "evidence_file_id", name="uq_shared_evidence_pin"),
    )
    op.create_index("ix_shared_evidence_pins_case_id", "shared_evidence_pins", ["case_id"])
    op.create_index("ix_shared_evidence_pins_evidence_file_id", "shared_evidence_pins", ["evidence_file_id"])
    op.create_index("ix_shared_evidence_pins_case_created", "shared_evidence_pins", ["case_id", "created_at"])

    op.create_table(
        "work_legacy_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(512), nullable=False),
        sa.Column("canonical_type", sa.String(64), nullable=False),
        sa.Column("canonical_id", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), server_default="migrated", nullable=False),
        sa.Column("migration_metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("case_id", "source_type", "source_id", name="uq_work_legacy_mapping"),
    )
    op.create_index("ix_work_legacy_mappings_case_id", "work_legacy_mappings", ["case_id"])
    op.create_index("ix_work_legacy_mappings_canonical", "work_legacy_mappings", ["canonical_type", "canonical_id"])


def _users_and_members(connection) -> tuple[dict[str, list[uuid.UUID]], set[tuple[uuid.UUID, uuid.UUID]], dict[uuid.UUID, uuid.UUID]]:
    emails: dict[str, list[uuid.UUID]] = {}
    for row in connection.execute(sa.text("SELECT id, email FROM users WHERE is_active = true")).mappings():
        emails.setdefault(str(row["email"]).strip().lower(), []).append(row["id"])
    members = {
        (row["case_id"], row["user_id"])
        for row in connection.execute(sa.text("SELECT case_id, user_id FROM case_memberships")).mappings()
    }
    owners = {
        row["id"]: row["owner_user_id"]
        for row in connection.execute(sa.text("SELECT id, owner_user_id FROM cases")).mappings()
    }
    members.update((case_id, owner_id) for case_id, owner_id in owners.items())
    return emails, members, owners


def _resolve_member(
    raw: Any,
    case_id: uuid.UUID,
    emails: dict[str, list[uuid.UUID]],
    members: set[tuple[uuid.UUID, uuid.UUID]],
) -> tuple[uuid.UUID | None, str | None]:
    if not raw:
        return None, None
    text = str(raw).strip()
    try:
        candidate = uuid.UUID(text)
        return (candidate, None) if (case_id, candidate) in members else (None, text)
    except ValueError:
        candidates = [candidate for candidate in emails.get(text.lower(), []) if (case_id, candidate) in members]
        return (candidates[0], None) if len(candidates) == 1 else (None, text)


def _insert_mapping(
    connection,
    *,
    case_id: uuid.UUID,
    source_type: str,
    source_id: str,
    canonical_type: str,
    canonical_id: str | None,
    status: str = "migrated",
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO work_legacy_mappings
                (id, case_id, source_type, source_id, canonical_type, canonical_id,
                 status, migration_metadata, created_at, updated_at)
            VALUES
                (:id, :case_id, :source_type, :source_id, :canonical_type, :canonical_id,
                 :status, CAST(:metadata AS jsonb), :created_at, :created_at)
            ON CONFLICT (case_id, source_type, source_id) DO UPDATE SET
                canonical_type = EXCLUDED.canonical_type,
                canonical_id = EXCLUDED.canonical_id,
                status = EXCLUDED.status,
                migration_metadata = EXCLUDED.migration_metadata,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": _stable("mapping", case_id, f"{source_type}:{source_id}"),
            "case_id": case_id,
            "source_type": source_type,
            "source_id": source_id,
            "canonical_type": canonical_type,
            "canonical_id": canonical_id,
            "status": status,
            "metadata": json.dumps(metadata or {}),
            "created_at": created_at or datetime.now(timezone.utc),
        },
    )


def _backfill_tasks(connection) -> dict[tuple[uuid.UUID, str], uuid.UUID]:
    emails, members, owners = _users_and_members(connection)
    mappings: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
    status_map = {"PENDING": "todo", "TO DO": "todo", "TODO": "todo", "IN_PROGRESS": "in_progress", "IN PROGRESS": "in_progress", "COMPLETED": "done", "DONE": "done"}
    priority_map = {"LOW": "low", "STANDARD": "standard", "HIGH": "high", "URGENT": "urgent"}
    rows = connection.execute(
        sa.text("SELECT id, case_id, task_id, data, created_at, updated_at FROM workspace_tasks ORDER BY created_at, id")
    ).mappings()
    for row in rows:
        data = _payload(row["data"])
        case_id = row["case_id"]
        legacy_id = str(data.get("task_id") or row["task_id"] or row["id"])
        task_id = _stable("task", case_id, legacy_id)
        raw_status = str(data.get("status") or "PENDING").strip().upper()
        status = status_map.get(raw_status, "todo")
        raw_priority = str(data.get("priority") or "STANDARD").strip().upper()
        priority = priority_map.get(raw_priority, "standard")
        assignee_id, unresolved_assignee = _resolve_member(
            data.get("assignee_user_id") or data.get("assigned_to"), case_id, emails, members
        )
        author_id, _ = _resolve_member(
            data.get("created_by_user_id") or data.get("author_id"), case_id, emails, members
        )
        author_id = author_id or owners.get(case_id)
        due_at = _as_datetime(data.get("due_at") or data.get("due_date"))
        created_at = _as_datetime(data.get("created_at")) or row["created_at"] or datetime.now(timezone.utc)
        updated_at = _as_datetime(data.get("updated_at")) or row["updated_at"] or created_at
        metadata: dict[str, Any] = {"legacy_payload": data, "source_row_id": str(row["id"])}
        if isinstance(data.get("migration_metadata"), dict):
            metadata["previous_migration_metadata"] = data["migration_metadata"]
        needs_review = bool(data.get("needs_migration_review"))
        if raw_status not in status_map:
            metadata["unfamiliar_status"] = raw_status
            needs_review = True
        if raw_priority not in priority_map:
            metadata["unfamiliar_priority"] = raw_priority
            needs_review = True
        if unresolved_assignee:
            metadata["unresolved_assignee"] = unresolved_assignee
            needs_review = True
        title = str(data.get("title") or "Untitled migrated task").strip() or "Untitled migrated task"
        connection.execute(
            sa.text(
                """
                INSERT INTO case_tasks
                    (id, case_id, title, description, status, priority, assignee_user_id,
                     due_at, created_by_user_id, updated_by_user_id, completed_at, deleted_at,
                     legacy_id, migration_metadata, needs_migration_review, created_at, updated_at)
                VALUES
                    (:id, :case_id, :title, :description, :status, :priority, :assignee,
                     :due_at, :author, :author, :completed_at, :deleted_at,
                     :legacy_id, CAST(:metadata AS jsonb), :needs_review, :created_at, :updated_at)
                ON CONFLICT (case_id, legacy_id) DO NOTHING
                """
            ),
            {
                "id": task_id,
                "case_id": case_id,
                "title": title[:512],
                "description": data.get("description") or data.get("status_text"),
                "status": status,
                "priority": priority,
                "assignee": assignee_id,
                "due_at": due_at,
                "author": author_id,
                "completed_at": _as_datetime(data.get("completed_at")) or (updated_at if status == "done" else None),
                "deleted_at": (
                    _as_datetime(data.get("deleted_at")) or updated_at
                    if data.get("deleted_at") or data.get("is_deleted")
                    else None
                ),
                "legacy_id": legacy_id,
                "metadata": json.dumps(metadata, default=str),
                "needs_review": needs_review,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        mappings[(case_id, legacy_id)] = task_id
        _insert_mapping(
            connection,
            case_id=case_id,
            source_type="workspace_task",
            source_id=legacy_id,
            canonical_type="task",
            canonical_id=str(task_id),
            status="needs_review" if needs_review else "migrated",
            metadata=metadata,
            created_at=created_at,
        )
    return mappings


def _backfill_deadlines(connection) -> dict[tuple[uuid.UUID, str], uuid.UUID]:
    mappings: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
    rows = connection.execute(
        sa.text("SELECT id, case_id, data, created_at, updated_at FROM workspace_deadline_configs ORDER BY created_at, id")
    ).mappings()
    for row in rows:
        data = _payload(row["data"])
        candidates: list[tuple[str, str, Any, dict[str, Any]]] = []
        if data.get("trial_date"):
            candidates.append(("trial", "Trial", data.get("trial_date"), {"legacy_trial": True}))
        for index, item in enumerate(data.get("deadlines") or []):
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("deadline_id") or f"deadline_{index}")
            name = str(item.get("title") or item.get("name") or "Untitled deadline").strip()
            candidates.append((source_id, name, item.get("due_date") or item.get("date"), item))
        for source_id, name, raw_date, metadata in candidates:
            due_date = _as_date(raw_date)
            if not due_date:
                _insert_mapping(
                    connection,
                    case_id=row["case_id"],
                    source_type="workspace_deadline",
                    source_id=source_id,
                    canonical_type="deadline",
                    canonical_id=None,
                    status="unresolved",
                    metadata={"reason": "invalid_date", "legacy_payload": metadata},
                    created_at=row["created_at"],
                )
                continue
            existing = connection.execute(
                sa.text("SELECT id FROM case_deadlines WHERE case_id=:case_id AND name=:name AND due_date=:due_date ORDER BY created_at, id LIMIT 1"),
                {"case_id": row["case_id"], "name": name, "due_date": due_date},
            ).scalar_one_or_none()
            deadline_id = existing or _stable("deadline", row["case_id"], f"{source_id}:{name}:{due_date.isoformat()}")
            if not existing:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO case_deadlines
                            (id, case_id, name, due_date, created_by_user_id, created_at, updated_at)
                        VALUES (:id, :case_id, :name, :due_date, NULL, :created_at, :updated_at)
                        """
                    ),
                    {
                        "id": deadline_id,
                        "case_id": row["case_id"],
                        "name": name[:255],
                        "due_date": due_date,
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    },
                )
            mappings[(row["case_id"], source_id)] = deadline_id
            _insert_mapping(
                connection,
                case_id=row["case_id"],
                source_type="workspace_deadline",
                source_id=source_id,
                canonical_type="deadline",
                canonical_id=str(deadline_id),
                metadata={"legacy_payload": metadata, "deduplicated": bool(existing)},
                created_at=row["created_at"],
            )
    return mappings


def _canonical_uuid_in_case(
    connection,
    *,
    table_name: str,
    case_id: uuid.UUID,
    raw_id: Any,
) -> uuid.UUID | None:
    if not raw_id:
        return None
    try:
        candidate = uuid.UUID(str(raw_id))
    except ValueError:
        return None
    return connection.execute(
        sa.text(f"SELECT id FROM {table_name} WHERE case_id=:case_id AND id=:id"),
        {"case_id": case_id, "id": candidate},
    ).scalar_one_or_none()


def _backfill_task_relationships(
    connection,
    task_mappings: dict[tuple[uuid.UUID, str], uuid.UUID],
    deadline_mappings: dict[tuple[uuid.UUID, str], uuid.UUID],
) -> None:
    """Restore parent/deadline/link relationships after all targets exist."""

    rows = list(
        connection.execute(
            sa.text(
                "SELECT id, case_id, task_id, data, created_at "
                "FROM workspace_tasks ORDER BY created_at, id"
            )
        ).mappings()
    )
    records: list[tuple[Any, dict[str, Any], str, uuid.UUID]] = []
    desired_parents: dict[uuid.UUID, uuid.UUID] = {}
    for row in rows:
        data = _payload(row["data"])
        legacy_id = str(data.get("task_id") or row["task_id"] or row["id"])
        task_id = task_mappings[(row["case_id"], legacy_id)]
        records.append((row, data, legacy_id, task_id))
        raw_parent = data.get("parent_task_id")
        if raw_parent:
            parent_id = task_mappings.get((row["case_id"], str(raw_parent)))
            parent_id = parent_id or _canonical_uuid_in_case(
                connection,
                table_name="case_tasks",
                case_id=row["case_id"],
                raw_id=raw_parent,
            )
            if parent_id and parent_id != task_id:
                desired_parents[task_id] = parent_id

    for row, data, legacy_id, task_id in records:
        warnings: list[dict[str, Any]] = []
        parent_id = desired_parents.get(task_id)
        if data.get("parent_task_id") and not parent_id:
            warnings.append({"relationship": "parent_task", "target": str(data["parent_task_id"]), "reason": "not_found_or_self"})
        elif parent_id and desired_parents.get(parent_id):
            warnings.append({"relationship": "parent_task", "target": str(data["parent_task_id"]), "reason": "deeper_than_one_level"})
            parent_id = None

        raw_deadline = data.get("deadline_id")
        deadline_id = None
        if raw_deadline:
            deadline_id = deadline_mappings.get((row["case_id"], str(raw_deadline)))
            deadline_id = deadline_id or _canonical_uuid_in_case(
                connection,
                table_name="case_deadlines",
                case_id=row["case_id"],
                raw_id=raw_deadline,
            )
            if not deadline_id:
                warnings.append({"relationship": "deadline", "target": str(raw_deadline), "reason": "not_found"})

        for index, raw_link in enumerate(data.get("links") or []):
            if not isinstance(raw_link, dict):
                warnings.append({"relationship": "link", "index": index, "reason": "invalid_payload"})
                continue
            target_type = str(raw_link.get("target_type") or raw_link.get("item_type") or "").lower()
            target_type = "evidence" if target_type == "document" else target_type
            raw_target = raw_link.get("target_id") or raw_link.get("item_id")
            target_id: uuid.UUID | None = None
            if target_type == "evidence":
                target_id = _resolve_evidence(connection, row["case_id"], str(raw_target or ""))
            elif target_type == "entry":
                target_id = _canonical_uuid_in_case(
                    connection, table_name="workspace_entries", case_id=row["case_id"], raw_id=raw_target
                )
            elif target_type == "dossier":
                target_id = _canonical_uuid_in_case(
                    connection, table_name="case_profiles", case_id=row["case_id"], raw_id=raw_target
                )
            if target_type not in {"dossier", "entry", "evidence"} or not target_id:
                warnings.append({
                    "relationship": "link",
                    "index": index,
                    "target_type": target_type,
                    "target": str(raw_target or ""),
                    "reason": "unsupported_or_not_found",
                })
                continue
            connection.execute(
                sa.text(
                    """
                    INSERT INTO case_task_links
                        (id, task_id, case_id, target_type, target_id, label,
                         source_anchor, created_by_user_id, created_at, updated_at)
                    SELECT :id, :task_id, :case_id, :target_type, :target_id, :label,
                           CAST(:source_anchor AS jsonb), created_by_user_id, :created_at, :created_at
                    FROM case_tasks WHERE id=:task_id
                    ON CONFLICT (task_id, target_type, target_id) DO NOTHING
                    """
                ),
                {
                    "id": _stable("task-link", row["case_id"], f"{legacy_id}:{target_type}:{target_id}"),
                    "task_id": task_id,
                    "case_id": row["case_id"],
                    "target_type": target_type,
                    "target_id": str(target_id),
                    "label": (raw_link.get("label") or raw_link.get("target_label")),
                    "source_anchor": json.dumps(raw_link.get("source_anchor") or {}),
                    "created_at": row["created_at"] or datetime.now(timezone.utc),
                },
            )

        current_metadata = connection.execute(
            sa.text("SELECT migration_metadata FROM case_tasks WHERE id=:id"),
            {"id": task_id},
        ).scalar_one()
        metadata = _payload(current_metadata)
        if warnings:
            metadata["relationship_warnings"] = warnings
        connection.execute(
            sa.text(
                "UPDATE case_tasks SET parent_task_id=:parent_id, deadline_id=:deadline_id, "
                "migration_metadata=CAST(:metadata AS jsonb), "
                "needs_migration_review=(needs_migration_review OR :needs_review) WHERE id=:id"
            ),
            {
                "id": task_id,
                "parent_id": parent_id,
                "deadline_id": deadline_id,
                "metadata": json.dumps(metadata, default=str),
                "needs_review": bool(warnings),
            },
        )
        if warnings:
            connection.execute(
                sa.text(
                    "UPDATE work_legacy_mappings SET status='needs_review', "
                    "migration_metadata=CAST(:metadata AS jsonb), updated_at=now() "
                    "WHERE case_id=:case_id AND source_type='workspace_task' AND source_id=:source_id"
                ),
                {
                    "case_id": row["case_id"],
                    "source_id": legacy_id,
                    "metadata": json.dumps(metadata, default=str),
                },
            )


def _resolve_evidence(connection, case_id: uuid.UUID, raw_id: str) -> uuid.UUID | None:
    try:
        candidate = uuid.UUID(raw_id)
    except ValueError:
        candidate = None
    if candidate:
        found = connection.execute(
            sa.text("SELECT id FROM evidence_files WHERE case_id=:case_id AND id=:id"),
            {"case_id": case_id, "id": candidate},
        ).scalar_one_or_none()
        if found:
            return found
    return connection.execute(
        sa.text("SELECT id FROM evidence_files WHERE case_id=:case_id AND legacy_id=:legacy_id ORDER BY created_at, id LIMIT 1"),
        {"case_id": case_id, "legacy_id": raw_id},
    ).scalar_one_or_none()


def _backfill_pins(connection) -> None:
    emails, members, _ = _users_and_members(connection)
    rows = connection.execute(
        sa.text("SELECT id, case_id, pin_id, item_type, item_id, user_id, data, created_at, updated_at FROM workspace_pinned_items ORDER BY created_at, id")
    ).mappings()
    for row in rows:
        data = _payload(row["data"])
        source_id = str(data.get("pin_id") or row["pin_id"] or row["id"])
        raw_evidence_id = str(data.get("item_id") or row["item_id"] or "")
        evidence_id = _resolve_evidence(connection, row["case_id"], raw_evidence_id)
        created_at = _as_datetime(data.get("pinned_at")) or row["created_at"] or datetime.now(timezone.utc)
        if not evidence_id:
            _insert_mapping(
                connection,
                case_id=row["case_id"],
                source_type="workspace_pin",
                source_id=source_id,
                canonical_type="evidence_pin",
                canonical_id=None,
                status="unresolved",
                metadata={"reason": "missing_evidence", "legacy_payload": data},
                created_at=created_at,
            )
            continue
        existing = connection.execute(
            sa.text("SELECT id FROM shared_evidence_pins WHERE case_id=:case_id AND evidence_file_id=:evidence_id"),
            {"case_id": row["case_id"], "evidence_id": evidence_id},
        ).scalar_one_or_none()
        pin_id = existing or _stable("pin", row["case_id"], evidence_id)
        raw_user = data.get("pinned_by_user_id") or data.get("user_id") or row["user_id"]
        user_id, unresolved_user = _resolve_member(raw_user, row["case_id"], emails, members)
        metadata = {"source_pin_id": source_id, "legacy_payload": data}
        if unresolved_user:
            metadata["unresolved_attribution"] = unresolved_user
        if not existing:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO shared_evidence_pins
                        (id, case_id, evidence_file_id, pinned_by_user_id, legacy_metadata, created_at, updated_at)
                    VALUES
                        (:id, :case_id, :evidence_id, :user_id, CAST(:metadata AS jsonb), :created_at, :updated_at)
                    """
                ),
                {
                    "id": pin_id,
                    "case_id": row["case_id"],
                    "evidence_id": evidence_id,
                    "user_id": user_id,
                    "metadata": json.dumps(metadata, default=str),
                    "created_at": created_at,
                    "updated_at": row["updated_at"] or created_at,
                },
            )
        _insert_mapping(
            connection,
            case_id=row["case_id"],
            source_type="workspace_pin",
            source_id=source_id,
            canonical_type="evidence_pin",
            canonical_id=str(pin_id),
            status="needs_review" if unresolved_user else "migrated",
            metadata={**metadata, "deduplicated": bool(existing)},
            created_at=created_at,
        )


def _repoint_links(connection) -> None:
    for table_name in ("workspace_entry_links", "dossier_links"):
        exists = connection.scalar(sa.text("SELECT to_regclass(:name) IS NOT NULL"), {"name": table_name})
        if not exists:
            continue
        connection.execute(
            sa.text(
                f"""
                UPDATE {table_name} AS links
                SET target_id = mappings.canonical_id
                FROM work_legacy_mappings AS mappings
                WHERE links.case_id = mappings.case_id
                  AND links.target_id = mappings.source_id
                  AND ((links.target_type = 'task' AND mappings.canonical_type = 'task')
                    OR (links.target_type = 'deadline' AND mappings.canonical_type = 'deadline'))
                  AND mappings.canonical_id IS NOT NULL
                """
            )
        )


def upgrade() -> None:
    _create_schema()
    connection = op.get_bind()
    task_mappings = _backfill_tasks(connection)
    deadline_mappings = _backfill_deadlines(connection)
    _backfill_task_relationships(connection, task_mappings, deadline_mappings)
    _backfill_pins(connection)
    _repoint_links(connection)


def _restore_legacy_links(connection) -> None:
    for table_name in ("workspace_entry_links", "dossier_links"):
        exists = connection.scalar(sa.text("SELECT to_regclass(:name) IS NOT NULL"), {"name": table_name})
        if not exists:
            continue
        connection.execute(
            sa.text(
                f"""
                UPDATE {table_name} AS links
                SET target_id = mappings.source_id
                FROM work_legacy_mappings AS mappings
                WHERE links.case_id = mappings.case_id
                  AND links.target_id = mappings.canonical_id
                  AND ((links.target_type = 'task' AND mappings.canonical_type = 'task')
                    OR (links.target_type = 'deadline' AND mappings.canonical_type = 'deadline'))
                  AND mappings.canonical_id IS NOT NULL
                """
            )
        )


def _export_tasks(connection) -> None:
    rows = connection.execute(sa.text("SELECT * FROM case_tasks ORDER BY created_at, id")).mappings()
    for row in rows:
        # Use the canonical UUID as the fallback source identity. External links
        # still targeting that UUID can then be repointed after a re-upgrade.
        legacy_id = row["legacy_id"] or str(row["id"])
        links = [
            dict(link)
            for link in connection.execute(
                sa.text("SELECT target_type, target_id, label, source_anchor FROM case_task_links WHERE task_id=:task_id ORDER BY created_at, id"),
                {"task_id": row["id"]},
            ).mappings()
        ]
        payload = {
            "task_id": legacy_id,
            "case_id": str(row["case_id"]),
            "title": row["title"],
            "description": row["description"],
            "status": {"todo": "PENDING", "in_progress": "IN_PROGRESS", "done": "COMPLETED"}[row["status"]],
            "priority": row["priority"].upper(),
            "assignee_user_id": str(row["assignee_user_id"]) if row["assignee_user_id"] else None,
            "due_at": row["due_at"].isoformat() if row["due_at"] else None,
            "parent_task_id": str(row["parent_task_id"]) if row["parent_task_id"] else None,
            "deadline_id": str(row["deadline_id"]) if row["deadline_id"] else None,
            "created_by_user_id": str(row["created_by_user_id"]) if row["created_by_user_id"] else None,
            "updated_by_user_id": str(row["updated_by_user_id"]) if row["updated_by_user_id"] else None,
            "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
            "deleted_at": row["deleted_at"].isoformat() if row["deleted_at"] else None,
            "links": links,
            "migration_metadata": row["migration_metadata"],
            "needs_migration_review": row["needs_migration_review"],
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }
        existing = connection.execute(
            sa.text("SELECT id FROM workspace_tasks WHERE case_id=:case_id AND task_id=:task_id ORDER BY created_at, id LIMIT 1"),
            {"case_id": row["case_id"], "task_id": legacy_id},
        ).scalar_one_or_none()
        if existing:
            connection.execute(
                sa.text("UPDATE workspace_tasks SET data=CAST(:data AS jsonb), updated_at=:updated_at WHERE id=:id"),
                {"data": json.dumps(payload, default=str), "updated_at": row["updated_at"], "id": existing},
            )
        else:
            connection.execute(
                sa.text("INSERT INTO workspace_tasks (id, case_id, task_id, data, created_at, updated_at) VALUES (:id,:case_id,:task_id,CAST(:data AS jsonb),:created_at,:updated_at)"),
                {"id": uuid.uuid4(), "case_id": row["case_id"], "task_id": legacy_id, "data": json.dumps(payload, default=str), "created_at": row["created_at"], "updated_at": row["updated_at"]},
            )


def _export_pins(connection) -> None:
    rows = connection.execute(sa.text("SELECT p.*, e.legacy_id FROM shared_evidence_pins p JOIN evidence_files e ON e.id=p.evidence_file_id ORDER BY p.created_at, p.id")).mappings()
    for row in rows:
        legacy_pin = connection.execute(
            sa.text("SELECT source_id FROM work_legacy_mappings WHERE case_id=:case_id AND canonical_type='evidence_pin' AND canonical_id=:canonical_id ORDER BY created_at LIMIT 1"),
            {"case_id": row["case_id"], "canonical_id": str(row["id"])},
        ).scalar_one_or_none() or f"pin_{str(row['id']).replace('-', '')[:12]}"
        payload = {
            "pin_id": legacy_pin,
            "case_id": str(row["case_id"]),
            "item_type": "evidence",
            "item_id": str(row["evidence_file_id"]),
            "user_id": str(row["pinned_by_user_id"]) if row["pinned_by_user_id"] else "migration-unresolved",
            "pinned_at": row["created_at"].isoformat(),
            "legacy_metadata": row["legacy_metadata"],
        }
        existing = connection.execute(
            sa.text("SELECT id FROM workspace_pinned_items WHERE case_id=:case_id AND pin_id=:pin_id ORDER BY created_at, id LIMIT 1"),
            {"case_id": row["case_id"], "pin_id": legacy_pin},
        ).scalar_one_or_none()
        if existing:
            connection.execute(
                sa.text("UPDATE workspace_pinned_items SET data=CAST(:data AS jsonb), item_type='evidence', item_id=:item_id, updated_at=:updated_at WHERE id=:id"),
                {"data": json.dumps(payload, default=str), "item_id": str(row["evidence_file_id"]), "updated_at": row["updated_at"], "id": existing},
            )
        else:
            connection.execute(
                sa.text("INSERT INTO workspace_pinned_items (id, case_id, pin_id, item_type, item_id, user_id, data, created_at, updated_at) VALUES (:id,:case_id,:pin_id,'evidence',:item_id,:user_id,CAST(:data AS jsonb),:created_at,:updated_at)"),
                {"id": uuid.uuid4(), "case_id": row["case_id"], "pin_id": legacy_pin, "item_id": str(row["evidence_file_id"]), "user_id": payload["user_id"], "data": json.dumps(payload, default=str), "created_at": row["created_at"], "updated_at": row["updated_at"]},
            )


def _export_deadlines(connection) -> None:
    case_ids = connection.execute(sa.text("SELECT DISTINCT case_id FROM case_deadlines")).scalars()
    for case_id in case_ids:
        existing_row = connection.execute(
            sa.text("SELECT id, data FROM workspace_deadline_configs WHERE case_id=:case_id"),
            {"case_id": case_id},
        ).mappings().first()
        payload = _payload(existing_row["data"]) if existing_row else {}
        existing_items = payload.get("deadlines") if isinstance(payload.get("deadlines"), list) else []
        seen = {
            (str(item.get("title") or item.get("name") or ""), str(item.get("due_date") or item.get("date") or ""))
            for item in existing_items if isinstance(item, dict)
        }
        deadlines = connection.execute(
            sa.text("SELECT id, name, due_date FROM case_deadlines WHERE case_id=:case_id ORDER BY due_date, name, id"),
            {"case_id": case_id},
        ).mappings()
        for deadline in deadlines:
            key = (deadline["name"], deadline["due_date"].isoformat())
            if key in seen:
                continue
            existing_items.append({"deadline_id": str(deadline["id"]), "title": deadline["name"], "due_date": deadline["due_date"].isoformat()})
            seen.add(key)
        payload["deadlines"] = existing_items
        if existing_row:
            connection.execute(sa.text("UPDATE workspace_deadline_configs SET data=CAST(:data AS jsonb), updated_at=now() WHERE id=:id"), {"data": json.dumps(payload), "id": existing_row["id"]})
        else:
            connection.execute(sa.text("INSERT INTO workspace_deadline_configs (id, case_id, data, created_at, updated_at) VALUES (:id,:case_id,CAST(:data AS jsonb),now(),now())"), {"id": uuid.uuid4(), "case_id": case_id, "data": json.dumps(payload)})


def downgrade() -> None:
    connection = op.get_bind()
    _restore_legacy_links(connection)
    _export_tasks(connection)
    _export_pins(connection)
    _export_deadlines(connection)
    op.drop_table("case_task_links")
    op.drop_table("shared_evidence_pins")
    op.drop_table("case_tasks")
    op.drop_table("work_legacy_mappings")
