"""What people wait for, joinable by minute: request start time, worker and stage times on slow requests;
page timing from every route; per-worker event-loop lag; per-minute host load; an availability probe.

All are telemetry only (services.request_speed, scripts/host_recorder.py). Retention is enforced by the writers.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261031_lx_measure"
down_revision = "20261029_model_work_origin"
branch_labels = None
depends_on = None


def upgrade():
    # request_speed_slow.at is the completion time (the row is queued after the last byte); the start is its own column.
    op.add_column('request_speed_slow', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('request_speed_slow', sa.Column('pid', sa.Integer(), nullable=True))
    op.add_column('request_speed_slow', sa.Column('pg_ms', sa.Float(), nullable=True))
    op.add_column('request_speed_slow', sa.Column('pg_count', sa.Integer(), nullable=True))
    op.add_column('request_speed_slow', sa.Column('gzip_ms', sa.Float(), nullable=True))
    op.add_column('request_speed_slow', sa.Column('cache', sa.String(16), nullable=True))

    op.create_table(
        'request_speed_pages',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('page', sa.String(64), nullable=False),
        sa.Column('method', sa.String(8), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ms', sa.Float(), nullable=False),
        sa.Column('nav_response_ms', sa.Float(), nullable=True),
        sa.Column('nav_dom_ms', sa.Float(), nullable=True),
        sa.Column('nav_load_ms', sa.Float(), nullable=True),
        sa.Column('nav_bytes', sa.BigInteger(), nullable=True),
        sa.Column('resources', sa.Integer(), nullable=True),
        sa.Column('resource_bytes', sa.BigInteger(), nullable=True),
        sa.Column('queue_max_ms', sa.Float(), nullable=True),
        sa.Column('queue_total_ms', sa.Float(), nullable=True),
        sa.Column('transfer_total_ms', sa.Float(), nullable=True),
        sa.Column('largest_ms', sa.Float(), nullable=True),
        sa.Column('largest_route', sa.String(160), nullable=True),
        sa.Column('largest_bytes', sa.BigInteger(), nullable=True),
        sa.Column('longest_task_ms', sa.Float(), nullable=True),
        sa.Column('long_tasks', sa.Integer(), nullable=True),
        sa.Column('heap_used_mb', sa.Float(), nullable=True),
        sa.Column('heap_limit_mb', sa.Float(), nullable=True),
        sa.Column('effective_type', sa.String(8), nullable=True),
        sa.Column('downlink_mbps', sa.Float(), nullable=True),
        sa.Column('rtt_ms', sa.Float(), nullable=True),
    )
    op.create_index('ix_request_speed_pages_at', 'request_speed_pages', ['at'])
    op.create_index('ix_request_speed_pages_page_at', 'request_speed_pages', ['page', 'at'])

    op.create_table(
        'request_speed_loop_lag',
        sa.Column('minute', sa.DateTime(timezone=True), nullable=False),
        sa.Column('pid', sa.Integer(), nullable=False),
        sa.Column('samples', sa.Integer(), nullable=False),
        sa.Column('max_ms', sa.Float(), nullable=False),
        sa.Column('total_ms', sa.Float(), nullable=False),
        sa.Column('over_100ms', sa.Integer(), nullable=False),
        sa.Column('over_1s', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('minute', 'pid'),
    )

    op.create_table(
        'host_load_minute',
        sa.Column('minute', sa.DateTime(timezone=True), primary_key=True),
        sa.Column('interval_s', sa.Float(), nullable=False),
        sa.Column('load1', sa.Float(), nullable=True),
        sa.Column('cpu_busy_cores', sa.Float(), nullable=True),
        sa.Column('psi_cpu_some', sa.Float(), nullable=True),
        sa.Column('psi_cpu_full', sa.Float(), nullable=True),
        sa.Column('psi_mem_some', sa.Float(), nullable=True),
        sa.Column('psi_mem_full', sa.Float(), nullable=True),
        sa.Column('psi_io_some', sa.Float(), nullable=True),
        sa.Column('psi_io_full', sa.Float(), nullable=True),
        sa.Column('mem_available_mb', sa.Float(), nullable=True),
        sa.Column('swap_used_mb', sa.Float(), nullable=True),
        sa.Column('swap_in_pages', sa.BigInteger(), nullable=True),
        sa.Column('swap_out_pages', sa.BigInteger(), nullable=True),
        sa.Column('groups', postgresql.JSONB(), nullable=True),
        sa.Column('top', postgresql.JSONB(), nullable=True),
        sa.Column('recorder_cpu_ms', sa.Float(), nullable=True),
    )

    op.create_table(
        'availability_probe',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('target', sa.String(16), nullable=False),
        sa.Column('status', sa.SmallInteger(), nullable=True),
        sa.Column('ms', sa.Float(), nullable=True),
        sa.Column('bytes', sa.Integer(), nullable=True),
        sa.Column('error', sa.String(120), nullable=True),
    )
    op.create_index('ix_availability_probe_at', 'availability_probe', ['at'])


def downgrade():
    op.drop_table('availability_probe')
    op.drop_table('host_load_minute')
    op.drop_table('request_speed_loop_lag')
    op.drop_table('request_speed_pages')
    for column in ('cache', 'gzip_ms', 'pg_count', 'pg_ms', 'pid', 'started_at'):
        op.drop_column('request_speed_slow', column)
