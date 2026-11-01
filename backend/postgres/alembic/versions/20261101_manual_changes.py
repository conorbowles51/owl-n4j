"""manual_changes: every change, confirmation or setting-aside a person makes to what the system produced."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261101_manual_changes"
down_revision = "20261031_slow_engine_ms"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'manual_changes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('kind', sa.String(80), nullable=False),
        sa.Column('change_type', sa.String(16), nullable=False),
        sa.Column('subject_type', sa.String(40), nullable=False, server_default=''),
        sa.Column('subject_id', sa.String(200), nullable=False, server_default=''),
        sa.Column('field', sa.String(300), nullable=False, server_default=''),
        sa.Column('producer', sa.String(300), nullable=False, server_default=''),
        sa.Column('layout', sa.String(300), nullable=False, server_default=''),
        sa.Column('pattern_key', sa.String(1000), nullable=False),
        sa.Column('before', postgresql.JSONB(), nullable=True),
        sa.Column('after', postgresql.JSONB(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('link', sa.Text(), nullable=False, server_default=''),
        sa.Column('actor_name', sa.String(300), nullable=False, server_default=''),
        sa.Column('actor_email', sa.String(300), nullable=False, server_default=''),
        sa.Column('actor_user_id', sa.String(64), nullable=False, server_default=''),
        sa.Column('is_test', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('historic', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('source', sa.String(20), nullable=False, server_default='app'),
        sa.Column('source_ref', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("change_type IN ('change', 'confirm', 'set_aside')", name='ck_manual_changes_type'),
    )
    op.create_index('ix_manual_changes_case', 'manual_changes', ['case_id', 'created_at'])
    op.create_index('ix_manual_changes_pattern', 'manual_changes', ['pattern_key'])
    op.create_index('uq_manual_changes_source_ref', 'manual_changes', ['source_ref'], unique=True)


def downgrade():
    op.drop_table('manual_changes')
