"""add saved timeline view tables

Revision ID: 20260705_timeline_views
Revises: 20260705_notebook_tables
Create Date: 2026-07-05 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260705_timeline_views"
down_revision: Union[str, None] = "20260705_notebook_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "timeline_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_email", sa.String(length=255), nullable=True),
        sa.Column("owner_name", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=32), server_default="case", nullable=False),
        sa.Column("filter_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("export_defaults", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_timeline_views_case_id", "timeline_views", ["case_id"], unique=False)
    op.create_index("ix_timeline_views_owner_user_id", "timeline_views", ["owner_user_id"], unique=False)
    op.create_index("ix_timeline_views_deleted_at", "timeline_views", ["deleted_at"], unique=False)
    op.create_index("ix_timeline_views_case_updated", "timeline_views", ["case_id", "updated_at"], unique=False)
    op.create_index("ix_timeline_views_owner_case", "timeline_views", ["owner_user_id", "case_id"], unique=False)

    op.create_table(
        "timeline_view_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("view_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(length=512), nullable=False),
        sa.Column("event_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("sort_date", sa.String(length=10), nullable=True),
        sa.Column("sort_time", sa.String(length=5), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["added_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["view_id"], ["timeline_views.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("view_id", "event_key", name="uq_timeline_view_event"),
    )
    op.create_index("ix_timeline_view_events_view_id", "timeline_view_events", ["view_id"], unique=False)
    op.create_index("ix_timeline_view_events_case_id", "timeline_view_events", ["case_id"], unique=False)
    op.create_index("ix_timeline_view_events_added_by_user_id", "timeline_view_events", ["added_by_user_id"], unique=False)
    op.create_index("ix_timeline_view_events_case_key", "timeline_view_events", ["case_id", "event_key"], unique=False)
    op.create_index(
        "ix_timeline_view_events_view_sort",
        "timeline_view_events",
        ["view_id", "sort_date", "sort_time", "position"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_timeline_view_events_view_sort", table_name="timeline_view_events")
    op.drop_index("ix_timeline_view_events_case_key", table_name="timeline_view_events")
    op.drop_index("ix_timeline_view_events_added_by_user_id", table_name="timeline_view_events")
    op.drop_index("ix_timeline_view_events_case_id", table_name="timeline_view_events")
    op.drop_index("ix_timeline_view_events_view_id", table_name="timeline_view_events")
    op.drop_table("timeline_view_events")

    op.drop_index("ix_timeline_views_owner_case", table_name="timeline_views")
    op.drop_index("ix_timeline_views_case_updated", table_name="timeline_views")
    op.drop_index("ix_timeline_views_deleted_at", table_name="timeline_views")
    op.drop_index("ix_timeline_views_owner_user_id", table_name="timeline_views")
    op.drop_index("ix_timeline_views_case_id", table_name="timeline_views")
    op.drop_table("timeline_views")
