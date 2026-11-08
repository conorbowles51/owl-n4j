"""Production numbers: numbered sets, issued ranges, received ranges, stamped copies. New tables only."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261106_production_numbers"
down_revision = "20261108_upload_group_members_total"
branch_labels = None
depends_on = None


def _stamps():
    return (sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def _id():
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _case():
    return sa.Column("case_id", UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)


def _user(name):
    return sa.Column(name, UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade():
    op.create_table(
        "production_sets", _id(), _case(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("prefix", sa.String(32), nullable=False),
        sa.Column("prefix_key", sa.String(32), nullable=False),
        sa.Column("start_number", sa.BigInteger(), nullable=False),
        sa.Column("padding", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.BigInteger(), nullable=False),
        _user("created_by_user_id"), *_stamps(),
        sa.UniqueConstraint("case_id", "prefix_key", name="uq_production_sets_case_prefix"),
        sa.CheckConstraint("start_number >= 0", name="ck_production_sets_start"),
        sa.CheckConstraint("padding BETWEEN 1 AND 12", name="ck_production_sets_padding"),
        sa.CheckConstraint("next_number >= start_number", name="ck_production_sets_next"))
    op.create_table(
        "production_assignments", _id(), _case(),
        sa.Column("set_id", UUID(as_uuid=True), sa.ForeignKey("production_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_file_id", UUID(as_uuid=True), sa.ForeignKey("evidence_files.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("first_number", sa.BigInteger(), nullable=False),
        sa.Column("last_number", sa.BigInteger(), nullable=False),
        _user("assigned_by_user_id"),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        _user("withdrawn_by_user_id"),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True), *_stamps(),
        sa.UniqueConstraint("set_id", "first_number", name="uq_production_assignments_set_first"),
        sa.CheckConstraint("last_number >= first_number", name="ck_production_assignments_range"),
        sa.CheckConstraint("level IN ('page', 'file')", name="ck_production_assignments_level"))
    op.create_index("ix_production_assignments_case", "production_assignments", ["case_id", "first_number"])
    op.create_index("ix_production_assignments_file", "production_assignments", ["evidence_file_id"])
    op.create_index("uq_production_assignments_live_file", "production_assignments", ["set_id", "evidence_file_id"],
                    unique=True, postgresql_where=sa.text("withdrawn_at IS NULL"))
    op.create_table(
        "received_numbers", _id(), _case(),
        sa.Column("evidence_file_id", UUID(as_uuid=True), sa.ForeignKey("evidence_files.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("prefix_key", sa.String(32), nullable=False),
        sa.Column("first_number", sa.BigInteger(), nullable=False),
        sa.Column("last_number", sa.BigInteger(), nullable=False),
        sa.Column("first_text", sa.String(64), nullable=False),
        sa.Column("last_text", sa.String(64), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        _user("decided_by_user_id"),
        sa.Column("decided_by_name", sa.String(255), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        _user("withdrawn_by_user_id"),
        sa.Column("note", sa.Text(), nullable=True), *_stamps(),
        sa.CheckConstraint("last_number >= first_number", name="ck_received_numbers_range"),
        sa.CheckConstraint("source IN ('person', 'import', 'file_name')", name="ck_received_numbers_source"),
        sa.CheckConstraint("status IN ('confirmed', 'rejected', 'withdrawn')", name="ck_received_numbers_status"))
    op.create_index("ix_received_numbers_case", "received_numbers", ["case_id", "first_number"])
    op.create_index("ix_received_numbers_file", "received_numbers", ["evidence_file_id"])
    op.create_index("uq_received_numbers_live", "received_numbers", ["evidence_file_id", "first_text", "last_text"],
                    unique=True, postgresql_where=sa.text("status <> 'withdrawn'"))
    op.create_table(
        "production_stamped_copies", _id(), _case(),
        sa.Column("assignment_id", UUID(as_uuid=True), sa.ForeignKey("production_assignments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        _user("created_by_user_id"), *_stamps())
    op.create_index("ix_production_stamped_copies_assignment", "production_stamped_copies", ["assignment_id"])


def downgrade():
    op.drop_table("production_stamped_copies")
    op.drop_table("received_numbers")
    op.drop_table("production_assignments")
    op.drop_table("production_sets")
