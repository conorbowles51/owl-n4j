"""add DeepSeek as a generative AI provider

Revision ID: 20260807_deepseek
Revises: 20260803_loupes
"""

from datetime import date
from typing import Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260807_deepseek"
down_revision: Union[str, None] = "20260803_loupes"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_ai_provider_credentials_provider",
        "ai_provider_credentials",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ai_provider_credentials_provider",
        "ai_provider_credentials",
        "provider IN ('openai', 'anthropic', 'gemini', 'deepseek')",
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
    op.bulk_insert(
        pricing_table,
        [
            {
                "id": uuid.uuid4(),
                "provider": "deepseek",
                "model_pattern": model_pattern,
                "operation_kind": "chat_completion",
                "billing_basis": "input_output_tokens",
                "input_cost_per_million": input_cost,
                "output_cost_per_million": output_cost,
                "duration_cost_per_minute": None,
                "pricing_version": "deepseek_docs_2026_08_07",
                "effective_from": date(2026, 8, 7),
                "effective_to": None,
                "priority": 200,
            }
            for model_pattern, input_cost, output_cost in (
                ("deepseek-v4-flash*", "0.14", "0.28"),
                ("deepseek-v4-pro*", "0.435", "0.87"),
            )
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM ai_pricing_rates "
        "WHERE pricing_version = 'deepseek_docs_2026_08_07'"
    )
    op.execute("DELETE FROM ai_provider_credentials WHERE provider = 'deepseek'")
    op.drop_constraint(
        "ck_ai_provider_credentials_provider",
        "ai_provider_credentials",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ai_provider_credentials_provider",
        "ai_provider_credentials",
        "provider IN ('openai', 'anthropic', 'gemini')",
    )
