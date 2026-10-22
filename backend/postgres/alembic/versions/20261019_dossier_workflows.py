"""Preserve interview date precision and dossier contact information.

Revision ID: 20261019_dossier_workflows
Revises: 20261002_one_active_statement
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261019_dossier_workflows"
down_revision = "20261002_one_active_statement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dossier_interviews", sa.Column("date_value", sa.String(64), nullable=True))
    op.add_column("case_profiles", sa.Column("contacts", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    # Keep contacts recorded by the older profile interface accessible after cutover.
    op.execute("""
        UPDATE case_profiles AS p SET contacts = saved.contacts
        FROM (
            SELECT profile_id, jsonb_agg(jsonb_build_object(
                'id', id::text, 'kind', kind, 'label', name, 'value', value,
                'evidence_file_id', NULL, 'recorded_by_user_id', NULL
            ) ORDER BY ordinal, id) AS contacts
            FROM case_profile_attributes WHERE kind IN ('phone', 'email', 'address')
            GROUP BY profile_id
        ) AS saved WHERE p.id = saved.profile_id
    """)


def downgrade() -> None:
    # Do not silently drop investigator contacts or partial interview dates.
    raise RuntimeError("Export dossier contacts and partial dates before a reviewed manual rollback")
