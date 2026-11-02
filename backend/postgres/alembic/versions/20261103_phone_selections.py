"""Frozen phone selections (07 section 6.1; lx-collect's ``phone_selection`` link type).

Add to… on a whole filtered result stores one ``phone_selection`` link instead of thousands of record links. The
selection freezes the record ids the filter matched at that moment, every copy included, together with the filter,
its sentence and the reading generation of each phone, so the link keeps meaning what it meant when it was made.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_phone_selections"
down_revision = "20261103_phone_copies_backfill"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_selections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("filter", postgresql.JSONB(), nullable=False),
        sa.Column("words", sa.Text(), nullable=False),
        sa.Column("record_uids", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("mapping_versions", postgresql.JSONB(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_phone_selections_case", "phone_selections", ["case_id"])


def downgrade():
    op.drop_index("ix_phone_selections_case", table_name="phone_selections")
    op.drop_table("phone_selections")
