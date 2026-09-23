"""Retained folder/archive selections and atomic registration receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '20260923_upload_groups'
down_revision = '20260923_money_trails'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('evidence_upload_groups',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('case_id', pg.UUID(as_uuid=True), sa.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', pg.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('folder_id', pg.UUID(as_uuid=True), sa.ForeignKey('evidence_folders.id', ondelete='CASCADE')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('replace_existing', sa.Boolean(), nullable=False),
        sa.Column('manifest', pg.JSONB(), nullable=False),
        sa.Column('receipt', pg.JSONB()),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_evidence_upload_groups_case_id', 'evidence_upload_groups', ['case_id'])
    op.add_column('evidence_upload_sessions', sa.Column('group_id', pg.UUID(as_uuid=True), sa.ForeignKey('evidence_upload_groups.id', ondelete='CASCADE')))
    op.create_index('ix_evidence_upload_sessions_group_id', 'evidence_upload_sessions', ['group_id'])


def downgrade():
    op.drop_index('ix_evidence_upload_sessions_group_id', table_name='evidence_upload_sessions')
    op.drop_column('evidence_upload_sessions', 'group_id')
    op.drop_table('evidence_upload_groups')
