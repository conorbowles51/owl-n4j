"""add workspace tables

Revision ID: 20260321_add_workspace_tables
Revises: 20260319_add_evidence_tables
Create Date: 2026-03-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260321_add_workspace_tables'
down_revision: Union[str, None] = '20260319_add_evidence_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create workspace tables to replace JSON-on-disk storage."""

    # --- workspace_contexts (one per case) ---
    op.create_table(
        'workspace_contexts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('data', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', name='uq_workspace_contexts_case_id'),
    )
    op.create_index('ix_workspace_contexts_case_id', 'workspace_contexts', ['case_id'], unique=True)

    # --- workspace_witnesses ---
    op.create_table(
        'workspace_witnesses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('witness_id', sa.String(64), nullable=False),
        sa.Column('data', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', 'witness_id', name='uq_workspace_witnesses_case_witness'),
    )
    op.create_index('ix_workspace_witnesses_case_id', 'workspace_witnesses', ['case_id'], unique=False)

    # --- workspace_theories ---
    op.create_table(
        'workspace_theories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('theory_id', sa.String(64), nullable=False),
        sa.Column('data', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', 'theory_id', name='uq_workspace_theories_case_theory'),
    )
    op.create_index('ix_workspace_theories_case_id', 'workspace_theories', ['case_id'], unique=False)

    # --- workspace_tasks ---
    op.create_table(
        'workspace_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('task_id', sa.String(64), nullable=False),
        sa.Column('data', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', 'task_id', name='uq_workspace_tasks_case_task'),
    )
    op.create_index('ix_workspace_tasks_case_id', 'workspace_tasks', ['case_id'], unique=False)

    # --- workspace_notes ---
    op.create_table(
        'workspace_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('note_id', sa.String(64), nullable=False),
        sa.Column('data', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', 'note_id', name='uq_workspace_notes_case_note'),
    )
    op.create_index('ix_workspace_notes_case_id', 'workspace_notes', ['case_id'], unique=False)

    # --- workspace_pinned_items ---
    op.create_table(
        'workspace_pinned_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('pin_id', sa.String(64), nullable=False),
        sa.Column('item_type', sa.String(64), nullable=False),
        sa.Column('item_id', sa.String(255), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('data', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', 'pin_id', name='uq_workspace_pinned_items_case_pin'),
    )
    op.create_index('ix_workspace_pinned_items_case_id', 'workspace_pinned_items', ['case_id'], unique=False)

    # --- workspace_deadline_configs (one per case) ---
    op.create_table(
        'workspace_deadline_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('data', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('case_id', name='uq_workspace_deadline_configs_case_id'),
    )
    op.create_index('ix_workspace_deadline_configs_case_id', 'workspace_deadline_configs', ['case_id'], unique=True)


def downgrade() -> None:
    """Drop workspace tables."""
    op.drop_table('workspace_deadline_configs')
    op.drop_table('workspace_pinned_items')
    op.drop_table('workspace_notes')
    op.drop_table('workspace_tasks')
    op.drop_table('workspace_theories')
    op.drop_table('workspace_witnesses')
    op.drop_table('workspace_contexts')
