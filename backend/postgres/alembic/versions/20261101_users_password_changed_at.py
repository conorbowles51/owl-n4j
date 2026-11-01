"""users.password_changed_at: a sign-in issued before the password last changed is refused."""
from alembic import op
import sqlalchemy as sa

revision = '20261101_users_password_changed_at'
down_revision = '20261101_phone_supersede_decision'
branch_labels = None
depends_on = None


def upgrade():
    # Empty for every existing user: no current sign-in is ended by the upgrade itself.
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('users', 'password_changed_at')
