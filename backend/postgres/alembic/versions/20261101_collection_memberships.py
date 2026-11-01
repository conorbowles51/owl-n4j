"""The per-record membership index for phone_selection links (07 section 6.4 item 7). A new, empty table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261101_collection_memberships'
down_revision = '20261101_link_registry'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'collection_memberships',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('container_type', sa.String(16), nullable=False),
        sa.Column('container_id', sa.String(64), nullable=False),
        sa.Column('link_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('record_id', sa.String(512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("container_type IN ('dossier', 'entry', 'task')", name='ck_collection_memberships_container'),
    )
    op.create_index('ix_collection_memberships_case_record', 'collection_memberships', ['case_id', 'record_id'])
    op.create_index('ix_collection_memberships_link', 'collection_memberships', ['link_id'])


def downgrade():
    op.drop_table('collection_memberships')
