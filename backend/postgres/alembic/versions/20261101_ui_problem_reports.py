"""Report a problem on phone screens (07 section 9): one new table, ui_problem_reports. Additive."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261101_ui_problem_reports"
down_revision = "20261101_manual_changes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ui_problem_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("screen", sa.String(64), nullable=False),
        sa.Column("action_kind", sa.String(32), nullable=False),
        sa.Column("refresh_changes", sa.String(16), nullable=False),
        sa.Column("build_id", sa.String(64), nullable=False),
        sa.Column("last_request_id", sa.String(64), nullable=True),
        sa.Column("viewport_w", sa.Integer(), nullable=True),
        sa.Column("viewport_h", sa.Integer(), nullable=True),
        sa.Column("scope", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("components", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ui_problem_reports_case_id", "ui_problem_reports", ["case_id"])
    op.create_index("ix_ui_problem_reports_undelivered", "ui_problem_reports", ["created_at"],
                    postgresql_where=sa.text("delivered_at IS NULL"))


def downgrade():
    op.drop_index("ix_ui_problem_reports_undelivered", table_name="ui_problem_reports")
    op.drop_index("ix_ui_problem_reports_case_id", table_name="ui_problem_reports")
    op.drop_table("ui_problem_reports")
