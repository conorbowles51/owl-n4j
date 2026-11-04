"""Saved phone views (07 section 6, the ``phone_view`` link type): Save this view in Conversations.

A saved view keeps the filter and the screen address it was saved from, its sentence and how many messages it listed
then. Opening it re-runs the filter live and states the count then and now. Unlike a frozen selection it keeps no
record ids: a view means "this filter", whatever the reports now hold.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261104_phone_views"
down_revision = "20261104_meaning_search_health"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("filter", postgresql.JSONB(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("words", sa.Text(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("mapping_versions", postgresql.JSONB(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_phone_views_case", "phone_views", ["case_id"])


def downgrade():
    op.drop_index("ix_phone_views_case", table_name="phone_views")
    op.drop_table("phone_views")
