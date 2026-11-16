"""Index of everything embedded for meaning search outside the document chunks (lx-embedall).

One row per embedded item: its area, its citation, the hash of the text that was embedded and, for items that have no
text of their own elsewhere, the text (so words can be searched with it). Phone conversation files keep their text in
``evidence_document_texts``; their row holds the hash only.

Revision ID: 20261116_embed_items
Revises: 20261113_relation_queries
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261116_embed_items"
down_revision = "20261113_relation_queries"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("embed_items",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("area", sa.String(40), nullable=False),
        sa.Column("item_key", sa.String(300), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("cite", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("body_folded", sa.Text(), nullable=True),
        sa.Column("item_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("person", sa.Text(), nullable=True),
        sa.Column("extraction_id", sa.String(64), nullable=True),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("case_id", "area", "item_key", name="pk_embed_items"))
    op.create_index("ix_embed_items_case_area", "embed_items", ["case_id", "area"])
    op.create_table("embed_area_state",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("area", sa.String(40), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_counts", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("case_id", "area", name="pk_embed_area_state"))


def downgrade():
    op.drop_table("embed_area_state")
    op.drop_table("embed_items")
