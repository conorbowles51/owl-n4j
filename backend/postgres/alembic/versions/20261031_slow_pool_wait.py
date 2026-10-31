"""request_speed_slow.pool_ms: the time a slow request waited for a database connection from the pool."""
from alembic import op
import sqlalchemy as sa

revision = "20261031_slow_pool_wait"
down_revision = "20261031_pg_stat_statements"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('request_speed_slow', sa.Column('pool_ms', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('request_speed_slow', 'pool_ms')
