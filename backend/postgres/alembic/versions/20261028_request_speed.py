"""Request speed: hourly per route/case/person timings with a mergeable histogram, and slow requests (30 days)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261028_request_speed"
down_revision = "20261028_activity_events"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'request_speed_hourly',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('hour', sa.DateTime(timezone=True), nullable=False),
        sa.Column('kind', sa.String(8), nullable=False),
        sa.Column('method', sa.String(8), nullable=False),
        sa.Column('route', sa.String(255), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('total_ms', sa.Float(), nullable=False),
        sa.Column('max_ms', sa.Float(), nullable=False),
        sa.Column('p50_ms', sa.Float(), nullable=True),
        sa.Column('p95_ms', sa.Float(), nullable=True),
        sa.Column('bytes', sa.BigInteger(), nullable=False),
        sa.Column('errors', sa.Integer(), nullable=False),
        sa.Column('buckets', postgresql.ARRAY(sa.Integer()), nullable=False),
    )
    # NULLS NOT DISTINCT (Postgres 15+): requests without a case or person still share one row per hour.
    op.execute('CREATE UNIQUE INDEX ux_request_speed_hourly_key ON request_speed_hourly '
               '(hour, kind, method, route, case_id, user_id) NULLS NOT DISTINCT')
    op.create_index('ix_request_speed_hourly_hour', 'request_speed_hourly', ['hour'])
    op.create_index('ix_request_speed_hourly_case_hour', 'request_speed_hourly', ['case_id', 'hour'])
    op.create_table(
        'request_speed_slow',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('kind', sa.String(8), nullable=False),
        sa.Column('method', sa.String(8), nullable=False),
        sa.Column('route', sa.String(255), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.SmallInteger(), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=False),
        sa.Column('bytes', sa.BigInteger(), nullable=False),
    )
    op.create_index('ix_request_speed_slow_at', 'request_speed_slow', ['at'])
    op.create_index('ix_request_speed_slow_case_at', 'request_speed_slow', ['case_id', 'at'])


def downgrade():
    op.drop_table('request_speed_slow')
    op.drop_table('request_speed_hourly')
