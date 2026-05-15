"""add investigator case profiles

Revision ID: 20260515_case_profiles
Revises: 20260515_case_archived
Create Date: 2026-05-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260515_case_profiles"
down_revision: Union[str, None] = "20260515_case_archived"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_type", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("importance", sa.String(32), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "archived_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "profile_type IN ('person', 'address', 'event', 'device', 'organisation', 'vehicle', 'other')",
            name="ck_case_profiles_type",
        ),
    )
    op.create_index("ix_case_profiles_case_id", "case_profiles", ["case_id"])
    op.create_index("ix_case_profiles_case_type_name", "case_profiles", ["case_id", "profile_type", "display_name"])
    op.create_index("ix_case_profiles_case_archived", "case_profiles", ["case_id", "archived_at"])

    op.create_table(
        "case_profile_attributes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('alias', 'tag', 'phone', 'email', 'address', 'identifier', 'device', 'vehicle', 'organisation', 'date', 'custom')",
            name="ck_case_profile_attributes_kind",
        ),
    )
    op.create_index("ix_case_profile_attributes_profile_id", "case_profile_attributes", ["profile_id"])
    op.create_index("ix_case_profile_attributes_case_id", "case_profile_attributes", ["case_id"])
    op.create_index(
        "ix_case_profile_attributes_case_kind_value",
        "case_profile_attributes",
        ["case_id", "kind", "value"],
    )

    op.create_table(
        "case_profile_graph_node_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_key", sa.String(512), nullable=False),
        sa.Column("node_name", sa.String(512), nullable=True),
        sa.Column("node_type", sa.String(128), nullable=True),
        sa.Column("relationship_type", sa.String(64), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("profile_id", "node_key", name="uq_case_profile_graph_node"),
    )
    op.create_index("ix_case_profile_graph_node_links_profile_id", "case_profile_graph_node_links", ["profile_id"])
    op.create_index("ix_case_profile_graph_node_links_case_id", "case_profile_graph_node_links", ["case_id"])
    op.create_index("ix_case_profile_graph_case_node", "case_profile_graph_node_links", ["case_id", "node_key"])

    op.create_table(
        "case_profile_evidence_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(64), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("profile_id", "evidence_file_id", name="uq_case_profile_evidence_file"),
    )
    op.create_index("ix_case_profile_evidence_links_profile_id", "case_profile_evidence_links", ["profile_id"])
    op.create_index("ix_case_profile_evidence_links_case_id", "case_profile_evidence_links", ["case_id"])
    op.create_index("ix_case_profile_evidence_links_evidence_file_id", "case_profile_evidence_links", ["evidence_file_id"])
    op.create_index("ix_case_profile_evidence_case_file", "case_profile_evidence_links", ["case_id", "evidence_file_id"])

    op.create_table(
        "case_profile_note_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("note_id", sa.String(128), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("profile_id", "note_id", name="uq_case_profile_note"),
    )
    op.create_index("ix_case_profile_note_links_profile_id", "case_profile_note_links", ["profile_id"])
    op.create_index("ix_case_profile_note_links_case_id", "case_profile_note_links", ["case_id"])
    op.create_index("ix_case_profile_notes_case_note", "case_profile_note_links", ["case_id", "note_id"])

    op.create_table(
        "case_profile_finding_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("finding_id", sa.String(128), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("profile_id", "finding_id", name="uq_case_profile_finding"),
    )
    op.create_index("ix_case_profile_finding_links_profile_id", "case_profile_finding_links", ["profile_id"])
    op.create_index("ix_case_profile_finding_links_case_id", "case_profile_finding_links", ["case_id"])
    op.create_index("ix_case_profile_findings_case_finding", "case_profile_finding_links", ["case_id", "finding_id"])


def downgrade() -> None:
    op.drop_index("ix_case_profile_findings_case_finding", table_name="case_profile_finding_links")
    op.drop_index("ix_case_profile_finding_links_case_id", table_name="case_profile_finding_links")
    op.drop_index("ix_case_profile_finding_links_profile_id", table_name="case_profile_finding_links")
    op.drop_table("case_profile_finding_links")

    op.drop_index("ix_case_profile_notes_case_note", table_name="case_profile_note_links")
    op.drop_index("ix_case_profile_note_links_case_id", table_name="case_profile_note_links")
    op.drop_index("ix_case_profile_note_links_profile_id", table_name="case_profile_note_links")
    op.drop_table("case_profile_note_links")

    op.drop_index("ix_case_profile_evidence_case_file", table_name="case_profile_evidence_links")
    op.drop_index("ix_case_profile_evidence_links_evidence_file_id", table_name="case_profile_evidence_links")
    op.drop_index("ix_case_profile_evidence_links_case_id", table_name="case_profile_evidence_links")
    op.drop_index("ix_case_profile_evidence_links_profile_id", table_name="case_profile_evidence_links")
    op.drop_table("case_profile_evidence_links")

    op.drop_index("ix_case_profile_graph_case_node", table_name="case_profile_graph_node_links")
    op.drop_index("ix_case_profile_graph_node_links_case_id", table_name="case_profile_graph_node_links")
    op.drop_index("ix_case_profile_graph_node_links_profile_id", table_name="case_profile_graph_node_links")
    op.drop_table("case_profile_graph_node_links")

    op.drop_index("ix_case_profile_attributes_case_kind_value", table_name="case_profile_attributes")
    op.drop_index("ix_case_profile_attributes_case_id", table_name="case_profile_attributes")
    op.drop_index("ix_case_profile_attributes_profile_id", table_name="case_profile_attributes")
    op.drop_table("case_profile_attributes")

    op.drop_index("ix_case_profiles_case_archived", table_name="case_profiles")
    op.drop_index("ix_case_profiles_case_type_name", table_name="case_profiles")
    op.drop_index("ix_case_profiles_case_id", table_name="case_profiles")
    op.drop_table("case_profiles")
