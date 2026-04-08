"""add ai cost tracking dimensions and pricing rates

Revision ID: 20260408_add_ai_cost_tracking
Revises: 20260408_add_workspace_findings
Create Date: 2026-04-08 18:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union
import uuid
from datetime import date

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260408_add_ai_cost_tracking"
down_revision: Union[str, Sequence[str], None] = "20260408_add_workspace_findings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_pricing_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_pattern", sa.String(length=128), nullable=False),
        sa.Column("operation_kind", sa.String(length=64), nullable=False),
        sa.Column("billing_basis", sa.String(length=32), nullable=False),
        sa.Column("input_cost_per_million", sa.Numeric(12, 6), nullable=True),
        sa.Column("output_cost_per_million", sa.Numeric(12, 6), nullable=True),
        sa.Column("duration_cost_per_minute", sa.Numeric(12, 6), nullable=True),
        sa.Column("pricing_version", sa.String(length=64), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_pricing_rates_provider", "ai_pricing_rates", ["provider"], unique=False)
    op.create_index("ix_ai_pricing_rates_model_pattern", "ai_pricing_rates", ["model_pattern"], unique=False)
    op.create_index("ix_ai_pricing_rates_operation_kind", "ai_pricing_rates", ["operation_kind"], unique=False)
    op.create_index("ix_ai_pricing_rates_effective_from", "ai_pricing_rates", ["effective_from"], unique=False)
    op.create_index("ix_ai_pricing_rates_effective_to", "ai_pricing_rates", ["effective_to"], unique=False)

    op.add_column("cost_records", sa.Column("operation_kind", sa.String(length=64), nullable=True))
    op.add_column("cost_records", sa.Column("engine_job_id", sa.String(length=36), nullable=True))
    op.add_column("cost_records", sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("cost_records", sa.Column("pricing_version", sa.String(length=64), nullable=True))
    op.create_index("ix_cost_records_operation_kind", "cost_records", ["operation_kind"], unique=False)
    op.create_index("ix_cost_records_engine_job_id", "cost_records", ["engine_job_id"], unique=False)
    op.create_index("ix_cost_records_evidence_file_id", "cost_records", ["evidence_file_id"], unique=False)
    op.create_foreign_key(
        "fk_cost_records_evidence_file_id",
        "cost_records",
        "evidence_files",
        ["evidence_file_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS requested_by_user_id UUID NULL")
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_evidence_file_id UUID NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_requested_by_user_id ON jobs (requested_by_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_source_evidence_file_id ON jobs (source_evidence_file_id)")

    pricing_version = "openai_docs_2026_04"
    effective_from = date(2026, 4, 8)
    seed_rows = [
        ("openai", "gpt-4o*", "chat_completion", "input_output_tokens", "2.50", "10.00", None, pricing_version, effective_from, None, 120),
        ("openai", "gpt-4o*", "vision", "input_output_tokens", "2.50", "10.00", None, pricing_version, effective_from, None, 120),
        ("openai", "gpt-4o-mini*", "chat_completion", "input_output_tokens", "0.15", "0.60", None, pricing_version, effective_from, None, 120),
        ("openai", "gpt-4o-mini*", "vision", "input_output_tokens", "0.15", "0.60", None, pricing_version, effective_from, None, 120),
        ("openai", "gpt-4.1*", "chat_completion", "input_output_tokens", "2.00", "8.00", None, pricing_version, effective_from, None, 110),
        ("openai", "gpt-5.2*", "chat_completion", "input_output_tokens", "1.75", "14.00", None, pricing_version, effective_from, None, 130),
        ("openai", "gpt-5-mini*", "chat_completion", "input_output_tokens", "0.25", "2.00", None, pricing_version, effective_from, None, 125),
        ("openai", "text-embedding-3-small*", "embedding", "input_tokens", "0.02", None, None, pricing_version, effective_from, None, 120),
        ("openai", "text-embedding-3-large*", "embedding", "input_tokens", "0.13", None, None, pricing_version, effective_from, None, 120),
        ("openai", "gpt-4o-mini-transcribe*", "transcription", "duration_minutes", None, None, "0.003", pricing_version, effective_from, None, 130),
        ("openai", "gpt-4o-transcribe*", "transcription", "duration_minutes", None, None, "0.006", pricing_version, effective_from, None, 130),
    ]
    pricing_table = sa.table(
        "ai_pricing_rates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("provider", sa.String),
        sa.column("model_pattern", sa.String),
        sa.column("operation_kind", sa.String),
        sa.column("billing_basis", sa.String),
        sa.column("input_cost_per_million", sa.Numeric),
        sa.column("output_cost_per_million", sa.Numeric),
        sa.column("duration_cost_per_minute", sa.Numeric),
        sa.column("pricing_version", sa.String),
        sa.column("effective_from", sa.Date),
        sa.column("effective_to", sa.Date),
        sa.column("priority", sa.Integer),
    )
    op.bulk_insert(
        pricing_table,
        [
            {
                "id": uuid.uuid4(),
                "provider": provider,
                "model_pattern": model_pattern,
                "operation_kind": operation_kind,
                "billing_basis": billing_basis,
                "input_cost_per_million": input_cost,
                "output_cost_per_million": output_cost,
                "duration_cost_per_minute": duration_cost,
                "pricing_version": version,
                "effective_from": seeded_from,
                "effective_to": seeded_to,
                "priority": priority,
            }
            for provider, model_pattern, operation_kind, billing_basis, input_cost, output_cost, duration_cost, version, seeded_from, seeded_to, priority in seed_rows
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_records_evidence_file_id", table_name="cost_records")
    op.drop_index("ix_cost_records_engine_job_id", table_name="cost_records")
    op.drop_index("ix_cost_records_operation_kind", table_name="cost_records")
    op.drop_constraint("fk_cost_records_evidence_file_id", "cost_records", type_="foreignkey")
    op.drop_column("cost_records", "pricing_version")
    op.drop_column("cost_records", "evidence_file_id")
    op.drop_column("cost_records", "engine_job_id")
    op.drop_column("cost_records", "operation_kind")

    op.execute("DROP INDEX IF EXISTS ix_jobs_source_evidence_file_id")
    op.execute("DROP INDEX IF EXISTS ix_jobs_requested_by_user_id")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS source_evidence_file_id")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS requested_by_user_id")

    op.drop_index("ix_ai_pricing_rates_effective_to", table_name="ai_pricing_rates")
    op.drop_index("ix_ai_pricing_rates_effective_from", table_name="ai_pricing_rates")
    op.drop_index("ix_ai_pricing_rates_operation_kind", table_name="ai_pricing_rates")
    op.drop_index("ix_ai_pricing_rates_model_pattern", table_name="ai_pricing_rates")
    op.drop_index("ix_ai_pricing_rates_provider", table_name="ai_pricing_rates")
    op.drop_table("ai_pricing_rates")
