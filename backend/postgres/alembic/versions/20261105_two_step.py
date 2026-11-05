"""Two-step sign-in, recovery codes, account reset codes and the sign-in policy row. New tables only."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20261105_two_step"
down_revision = "20261105_pending_chunk_vectors"
branch_labels = None
depends_on = None


def _stamps():
    return (sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def _user(primary_key=False):
    return sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"),
                     primary_key=primary_key, nullable=False)


def upgrade():
    op.create_table(
        "user_two_step", _user(primary_key=True),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        *_stamps())
    op.create_table(
        "user_recovery_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True), _user(),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps())
    op.create_index("ix_user_recovery_codes_user", "user_recovery_codes", ["user_id"])
    op.create_table(
        "account_reset_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True), _user(),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("issued_by", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps())
    op.create_index("ix_account_reset_codes_user", "account_reset_codes", ["user_id"])
    op.create_table(
        "login_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("require_two_step_for_admins", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("changed_by", sa.String(255), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_login_policy_single_row"))


def downgrade():
    op.drop_table("login_policy")
    op.drop_index("ix_account_reset_codes_user", table_name="account_reset_codes")
    op.drop_table("account_reset_codes")
    op.drop_index("ix_user_recovery_codes_user", table_name="user_recovery_codes")
    op.drop_table("user_recovery_codes")
    op.drop_table("user_two_step")
