"""add cost records

Revision ID: 20260129_add_cost_records
Revises: 20260128_add_rejected_merge_pairs
Create Date: 2026-01-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260129_add_cost_records'
down_revision: Union[str, None] = '20260128_rejected_pairs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create enum for cost_job_type (only if it doesn't exist)
    from sqlalchemy import text
    connection = op.get_bind()
    result = connection.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_type WHERE typname = 'cost_job_type'
        )
    """))
    enum_exists = result.scalar()
    
    if not enum_exists:
        op.execute("CREATE TYPE cost_job_type AS ENUM ('ingestion', 'ai_assistant')")
    
    # Check if table already exists (in case of partial migration)
    result = connection.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'cost_records'
        )
    """))
    table_exists = result.scalar()
    
    if not table_exists:
        # Create cost_records table
        # Use postgresql.ENUM with create_type=False to avoid auto-creating the enum
        # since we've already handled enum creation above
        job_type_enum = postgresql.ENUM('ingestion', 'ai_assistant', name='cost_job_type', create_type=False)
        
        op.create_table('cost_records',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('job_type', job_type_enum, nullable=False),
            sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('provider', sa.String(length=50), nullable=False),
            sa.Column('model_id', sa.String(length=100), nullable=False),
            sa.Column('prompt_tokens', sa.Integer(), nullable=True),
            sa.Column('completion_tokens', sa.Integer(), nullable=True),
            sa.Column('total_tokens', sa.Integer(), nullable=True),
            sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=False),
            sa.Column('description', sa.String(length=500), nullable=True),
            sa.Column('extra_metadata', postgresql.JSONB(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_cost_records_case_id'), 'cost_records', ['case_id'], unique=False)
        op.create_index(op.f('ix_cost_records_user_id'), 'cost_records', ['user_id'], unique=False)
        op.create_index(op.f('ix_cost_records_job_type'), 'cost_records', ['job_type'], unique=False)
        op.create_index(op.f('ix_cost_records_model_id'), 'cost_records', ['model_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_cost_records_model_id'), table_name='cost_records')
    op.drop_index(op.f('ix_cost_records_job_type'), table_name='cost_records')
    op.drop_index(op.f('ix_cost_records_user_id'), table_name='cost_records')
    op.drop_index(op.f('ix_cost_records_case_id'), table_name='cost_records')
    op.drop_table('cost_records')
    op.execute("DROP TYPE cost_job_type")
