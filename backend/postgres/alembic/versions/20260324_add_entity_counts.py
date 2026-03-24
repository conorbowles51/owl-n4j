"""Add entity_count and relationship_count to evidence_files."""

from alembic import op
import sqlalchemy as sa

revision = "20260324_add_entity_counts"
down_revision = "20260322_evidence_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence_files", sa.Column("entity_count", sa.Integer(), nullable=True))
    op.add_column("evidence_files", sa.Column("relationship_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence_files", "relationship_count")
    op.drop_column("evidence_files", "entity_count")
