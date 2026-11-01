"""manual_changes.replaces_id: the record a later record corrects (the original stays, the correction counts)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261101_manual_change_replaces"
down_revision = "20261101_manual_changes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('manual_changes', sa.Column('replaces_id', postgresql.UUID(as_uuid=True), nullable=True))


def downgrade():
    op.drop_column('manual_changes', 'replaces_id')
