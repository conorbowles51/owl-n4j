"""add centralized AI model routing policy

Revision ID: 20260722_ai_model_policy
Revises: 20260722_geocode_ambiguous
Create Date: 2026-07-22
"""

from datetime import date
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260722_ai_model_policy"
down_revision: Union[str, Sequence[str], None] = "20260722_geocode_ambiguous"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_model_policies",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.execute(
        """
        INSERT INTO ai_model_policies (key, revision, configuration)
        VALUES (
          'default',
          1,
          '{
            "chat": {"provider": "openai", "model_id": "gpt-5.6-terra"},
            "agent": {"provider": "openai", "model_id": "gpt-5.6-sol"},
            "ingestion_extraction": {"provider": "openai", "model_id": "gpt-5.6-terra"},
            "ingestion_resolution": {"provider": "openai", "model_id": "gpt-5.6-terra"},
            "ingestion_entity_summary": {"provider": "openai", "model_id": "gpt-5.6-terra"},
            "ingestion_document_summary": {"provider": "openai", "model_id": "gpt-5.6-sol"},
            "ingestion_quality": {"provider": "openai", "model_id": "gpt-5.6-terra"}
          }'::jsonb
        )
        """
    )
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
    rows = [
        ("openai", "gpt-5.6-sol*", "5.00", "30.00"),
        ("openai", "gpt-5.6-terra*", "2.50", "15.00"),
        ("openai", "gpt-5.6-luna*", "1.00", "6.00"),
        # Anthropic's introductory Sonnet 5 rate is effective through 2026-08-31.
        ("anthropic", "claude-sonnet-5*", "2.00", "10.00"),
        ("anthropic", "claude-opus-4-8*", "5.00", "25.00"),
        ("anthropic", "claude-haiku-4-5*", "1.00", "5.00"),
        ("gemini", "gemini-3.6-flash*", "1.50", "7.50"),
        ("gemini", "gemini-3.5-flash*", "1.50", "9.00"),
        ("gemini", "gemini-3.5-flash-lite*", "0.30", "2.50"),
    ]
    op.bulk_insert(
        pricing_table,
        [
            {
                "id": uuid.uuid4(),
                "provider": provider,
                "model_pattern": model_pattern,
                "operation_kind": "chat_completion",
                "billing_basis": "input_output_tokens",
                "input_cost_per_million": input_cost,
                "output_cost_per_million": output_cost,
                "duration_cost_per_minute": None,
                "pricing_version": "provider_docs_2026_07_22",
                "effective_from": date(2026, 7, 22),
                "effective_to": None,
                "priority": 200,
            }
            for provider, model_pattern, input_cost, output_cost in rows
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ai_pricing_rates WHERE pricing_version = "
        "'provider_docs_2026_07_22'"
    )
    op.drop_table("ai_model_policies")
