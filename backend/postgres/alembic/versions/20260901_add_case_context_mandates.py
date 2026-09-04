"""add universal case context and immutable mandate versions

Revision ID: 20260901_case_context
Revises: 20260901_dossier_importance
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260901_case_context"
down_revision: Union[str, None] = "20260901_dossier_importance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _text(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if str(item).strip()) or None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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


def _seed_templates(connection) -> dict[str, dict[str, uuid.UUID]]:
    now = datetime.utcnow()
    template_table = sa.table(
        "case_context_templates",
        sa.column("id", UUID), sa.column("key", sa.String), sa.column("name", sa.String),
        sa.column("description", sa.Text), sa.column("is_builtin", sa.Boolean),
        sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
    )
    field_table = sa.table(
        "case_context_template_fields",
        sa.column("id", UUID), sa.column("template_id", UUID), sa.column("field_key", sa.String),
        sa.column("label", sa.String), sa.column("field_type", sa.String), sa.column("choices", JSONB),
        sa.column("required", sa.Boolean), sa.column("position", sa.Integer),
        sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime),
    )
    result: dict[str, dict[str, uuid.UUID]] = {}
    definitions = {
        "generic": ("General investigation", "Universal context suitable for any investigation.", []),
        "criminal_defense": (
            "Criminal defence",
            "Preserves criminal-defence orientation without making it the platform default.",
            [
                ("client_profile", "Client profile", "long_text"),
                ("charges", "Charges", "long_text"),
                ("allegations", "Allegations", "long_text"),
                ("denials", "Denials", "long_text"),
                ("legal_exposure", "Legal exposure", "long_text"),
                ("defense_strategy", "Defence strategy", "long_text"),
                ("court_info", "Court information", "long_text"),
            ],
        ),
    }
    for key, (name, description, fields) in definitions.items():
        template_id = uuid.uuid4()
        connection.execute(template_table.insert().values(
            id=template_id, key=key, name=name, description=description, is_builtin=True,
            created_at=now, updated_at=now,
        ))
        result[key] = {}
        for position, (field_key, label, field_type) in enumerate(fields):
            field_id = uuid.uuid4()
            connection.execute(field_table.insert().values(
                id=field_id, template_id=template_id, field_key=field_key, label=label,
                field_type=field_type, choices=[], required=False, position=position,
                created_at=now, updated_at=now,
            ))
            result[key][field_key] = field_id
    return result


def _backfill(connection, fields: dict[str, dict[str, uuid.UUID]]) -> None:
    legacy_rows = connection.execute(sa.text("SELECT id, case_id, data FROM workspace_contexts")).mappings().all()
    contexts = sa.table(
        "case_contexts", sa.column("id", UUID), sa.column("case_id", UUID),
        sa.column("case_summary", sa.Text), sa.column("background", sa.Text),
        sa.column("investigation_type", sa.String), sa.column("jurisdiction", sa.Text),
        sa.column("active_template_key", sa.String), sa.column("active_mandate_version_id", UUID),
        sa.column("created_by_user_id", UUID), sa.column("updated_by_user_id", UUID),
    )
    values = sa.table(
        "case_context_values", sa.column("id", UUID), sa.column("context_id", UUID),
        sa.column("case_id", UUID), sa.column("template_field_id", UUID), sa.column("value", JSONB),
    )
    mandates = sa.table(
        "case_mandate_versions", sa.column("id", UUID), sa.column("case_id", UUID),
        sa.column("version_number", sa.Integer), sa.column("objective", sa.Text),
        sa.column("key_questions", JSONB), sa.column("in_scope", sa.Text),
        sa.column("out_of_scope", sa.Text), sa.column("perspective", sa.Text),
        sa.column("success_criteria", sa.Text), sa.column("constraints", sa.Text),
        sa.column("author_user_id", UUID),
    )
    mappings = sa.table(
        "case_context_legacy_mappings", sa.column("id", UUID), sa.column("case_id", UUID),
        sa.column("workspace_context_id", UUID), sa.column("migrated_payload", JSONB), sa.column("warnings", JSONB),
    )
    for row in legacy_rows:
        data = _payload(row["data"])
        case_id = row["case_id"]
        context_id = uuid.uuid4()
        specialized = any(data.get(key) not in (None, "", [], {}) for key in fields["criminal_defense"])
        template_key = "criminal_defense" if specialized else "generic"
        restored = data.get("_phase4_context") if isinstance(data.get("_phase4_context"), dict) else {}
        connection.execute(contexts.insert().values(
            id=context_id,
            case_id=case_id,
            case_summary=restored.get("case_summary") or _text(data.get("summary")),
            background=restored.get("background") or _text(data.get("background")),
            investigation_type=restored.get("investigation_type"),
            jurisdiction=restored.get("jurisdiction"),
            active_template_key=restored.get("active_template_key") or template_key,
            created_by_user_id=None,
            updated_by_user_id=None,
        ))
        restored_values = restored.get("values") if isinstance(restored.get("values"), dict) else {}
        for field_key, field_id in fields["criminal_defense"].items():
            raw = restored_values.get(field_key, data.get(field_key))
            rendered = _text(raw)
            if rendered:
                connection.execute(values.insert().values(
                    id=uuid.uuid4(), context_id=context_id, case_id=case_id,
                    template_field_id=field_id, value=rendered,
                ))

        restored_mandates = data.get("_phase4_mandates") if isinstance(data.get("_phase4_mandates"), list) else []
        active_mandate_id = None
        if restored_mandates:
            for index, payload in enumerate(restored_mandates, start=1):
                mandate_id = uuid.uuid4()
                connection.execute(mandates.insert().values(
                    id=mandate_id, case_id=case_id, version_number=index,
                    objective=_text(payload.get("objective")), key_questions=payload.get("key_questions") or [],
                    in_scope=_text(payload.get("in_scope")), out_of_scope=_text(payload.get("out_of_scope")),
                    perspective=_text(payload.get("perspective")), success_criteria=_text(payload.get("success_criteria")),
                    constraints=_text(payload.get("constraints")), author_user_id=None,
                ))
                if payload.get("active"):
                    active_mandate_id = mandate_id
            active_mandate_id = active_mandate_id or mandate_id
        else:
            objective = _text(data.get("objectives"))
            perspective = _text(data.get("defense_strategy"))
            if objective or perspective:
                active_mandate_id = uuid.uuid4()
                connection.execute(mandates.insert().values(
                    id=active_mandate_id, case_id=case_id, version_number=1,
                    objective=objective, key_questions=[], in_scope=None, out_of_scope=None,
                    perspective=perspective, success_criteria=None, constraints=None, author_user_id=None,
                ))
        if active_mandate_id:
            connection.execute(sa.text("UPDATE case_contexts SET active_mandate_version_id = :version WHERE id = :context"), {
                "version": active_mandate_id, "context": context_id,
            })

        warnings: list[str] = []
        trial_date = data.get("trial_date")
        if trial_date:
            try:
                parsed_date = date.fromisoformat(str(trial_date)[:10])
                exact = connection.scalar(sa.text(
                    "SELECT count(*) FROM case_deadlines WHERE case_id = :case_id AND due_date = :due_date"
                ), {"case_id": case_id, "due_date": parsed_date})
                if not exact:
                    connection.execute(sa.text(
                        "INSERT INTO case_deadlines (id, case_id, name, due_date, created_by_user_id) "
                        "VALUES (:id, :case_id, 'Trial date', :due_date, NULL)"
                    ), {"id": uuid.uuid4(), "case_id": case_id, "due_date": parsed_date})
            except ValueError:
                warnings.append(f"Invalid trial_date preserved in legacy payload: {trial_date}")
        connection.execute(mappings.insert().values(
            id=uuid.uuid4(), case_id=case_id, workspace_context_id=row["id"],
            migrated_payload=data, warnings=warnings,
        ))


def upgrade() -> None:
    op.create_table(
        "case_context_templates",
        sa.Column("id", UUID, primary_key=True), sa.Column("key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False), sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), server_default=sa.false(), nullable=False), *_timestamps(),
    )
    op.create_index("ix_case_context_templates_key", "case_context_templates", ["key"], unique=True)
    op.create_table(
        "case_context_template_fields",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("template_id", UUID, sa.ForeignKey("case_context_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_key", sa.String(64), nullable=False), sa.Column("label", sa.String(128), nullable=False),
        sa.Column("field_type", sa.String(32), nullable=False),
        sa.Column("choices", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False), *_timestamps(),
        sa.UniqueConstraint("template_id", "field_key", name="uq_case_context_template_field"),
    )
    op.create_index("ix_case_context_template_fields_template_id", "case_context_template_fields", ["template_id"])
    op.create_table(
        "case_contexts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("case_summary", sa.Text(), nullable=True), sa.Column("background", sa.Text(), nullable=True),
        sa.Column("investigation_type", sa.String(128), nullable=True), sa.Column("jurisdiction", sa.Text(), nullable=True),
        sa.Column("active_template_key", sa.String(64), server_default="generic", nullable=False),
        sa.Column("active_mandate_version_id", UUID, nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True), *_timestamps(),
    )
    op.create_index("ix_case_contexts_case_id", "case_contexts", ["case_id"], unique=True)
    op.create_table(
        "case_mandate_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("key_questions", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("in_scope", sa.Text(), nullable=True), sa.Column("out_of_scope", sa.Text(), nullable=True),
        sa.Column("perspective", sa.Text(), nullable=True), sa.Column("success_criteria", sa.Text(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column("author_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("case_id", "version_number", name="uq_case_mandate_version"),
    )
    op.create_index("ix_case_mandate_versions_case_id", "case_mandate_versions", ["case_id"])
    op.create_index("ix_case_mandate_versions_author_user_id", "case_mandate_versions", ["author_user_id"])
    op.create_foreign_key(
        "fk_case_contexts_active_mandate", "case_contexts", "case_mandate_versions",
        ["active_mandate_version_id"], ["id"], ondelete="SET NULL",
    )
    op.create_table(
        "case_context_values",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("context_id", UUID, sa.ForeignKey("case_contexts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_field_id", UUID, sa.ForeignKey("case_context_template_fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", JSONB, nullable=False), *_timestamps(),
        sa.UniqueConstraint("context_id", "template_field_id", name="uq_case_context_value_field"),
    )
    op.create_index("ix_case_context_values_context_id", "case_context_values", ["context_id"])
    op.create_index("ix_case_context_values_case_id", "case_context_values", ["case_id"])
    op.create_index("ix_case_context_values_template_field_id", "case_context_values", ["template_field_id"])
    op.create_index("ix_case_context_values_case_context", "case_context_values", ["case_id", "context_id"])
    op.create_table(
        "case_context_legacy_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("case_id", UUID, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("workspace_context_id", UUID, sa.ForeignKey("workspace_contexts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("migrated_payload", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("warnings", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("migrated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_case_context_legacy_mappings_case_id", "case_context_legacy_mappings", ["case_id"], unique=True)

    for table in ("chat_conversations", "chat_messages", "agent_threads", "agent_runs", "dossier_generated_outputs"):
        op.add_column(table, sa.Column("mandate_version_id", UUID, nullable=True))
        op.create_index(f"ix_{table}_mandate_version_id", table, ["mandate_version_id"])
        op.create_foreign_key(
            f"fk_{table}_mandate_version", table, "case_mandate_versions",
            ["mandate_version_id"], ["id"], ondelete="SET NULL",
        )
    op.add_column("chat_messages", sa.Column("mandate_override", JSONB, nullable=True))
    op.add_column("agent_runs", sa.Column("mandate_override", JSONB, nullable=True))

    connection = op.get_bind()
    fields = _seed_templates(connection)
    _backfill(connection, fields)


def downgrade() -> None:
    connection = op.get_bind()
    # Preserve every new context and mandate in the retained legacy row so a
    # subsequent re-upgrade can restore it without data loss.
    contexts = connection.execute(sa.text(
        "SELECT id, case_id, case_summary, background, investigation_type, jurisdiction, "
        "active_template_key, active_mandate_version_id FROM case_contexts"
    )).mappings().all()
    for context in contexts:
        legacy = connection.execute(sa.text(
            "SELECT id, data FROM workspace_contexts WHERE case_id = :case_id"
        ), {"case_id": context["case_id"]}).mappings().first()
        values = connection.execute(sa.text(
            "SELECT f.field_key, v.value FROM case_context_values v "
            "JOIN case_context_template_fields f ON f.id = v.template_field_id WHERE v.context_id = :context_id"
        ), {"context_id": context["id"]}).mappings().all()
        mandates = connection.execute(sa.text(
            "SELECT id, objective, key_questions, in_scope, out_of_scope, perspective, success_criteria, constraints "
            "FROM case_mandate_versions WHERE case_id = :case_id ORDER BY version_number"
        ), {"case_id": context["case_id"]}).mappings().all()
        snapshot = {
            "case_summary": context["case_summary"], "background": context["background"],
            "investigation_type": context["investigation_type"], "jurisdiction": context["jurisdiction"],
            "active_template_key": context["active_template_key"],
            "values": {row["field_key"]: row["value"] for row in values},
        }
        mandate_snapshots = [
            {**{key: row[key] for key in ("objective", "key_questions", "in_scope", "out_of_scope", "perspective", "success_criteria", "constraints")},
             "active": row["id"] == context["active_mandate_version_id"]}
            for row in mandates
        ]
        payload = _payload(legacy["data"]) if legacy else {}
        payload["_phase4_context"] = snapshot
        payload["_phase4_mandates"] = mandate_snapshots
        if legacy:
            connection.execute(sa.text("UPDATE workspace_contexts SET data = :data WHERE id = :id"), {
                "data": json.dumps(payload), "id": legacy["id"],
            })
        else:
            connection.execute(sa.text(
                "INSERT INTO workspace_contexts (id, case_id, data) VALUES (:id, :case_id, :data)"
            ), {"id": uuid.uuid4(), "case_id": context["case_id"], "data": json.dumps(payload)})

    op.drop_column("agent_runs", "mandate_override")
    op.drop_column("chat_messages", "mandate_override")
    for table in reversed(("chat_conversations", "chat_messages", "agent_threads", "agent_runs", "dossier_generated_outputs")):
        op.drop_constraint(f"fk_{table}_mandate_version", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_mandate_version_id", table_name=table)
        op.drop_column(table, "mandate_version_id")
    op.drop_table("case_context_legacy_mappings")
    op.drop_table("case_context_values")
    op.drop_constraint("fk_case_contexts_active_mandate", "case_contexts", type_="foreignkey")
    op.drop_table("case_mandate_versions")
    op.drop_table("case_contexts")
    op.drop_table("case_context_template_fields")
    op.drop_table("case_context_templates")
