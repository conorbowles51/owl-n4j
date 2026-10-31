"""request_speed_slow.engine_ms: evidence-engine call time inside a slow request (summed over its calls)."""
from alembic import op
import sqlalchemy as sa

revision = "20261031_slow_engine_ms"
down_revision = "20261031_batches_compact_retry"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('request_speed_slow', sa.Column('engine_ms', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('request_speed_slow', 'engine_ms')
