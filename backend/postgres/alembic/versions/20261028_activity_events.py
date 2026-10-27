"""Activity trail: sign-ins, evidence uploads and Financial entries with source address. Append-only."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261028_activity_events"
down_revision = "20261027_financial_category_rules"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'activity_events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_name', sa.String(255), nullable=True),
        sa.Column('user_email', sa.String(255), nullable=True),
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_address', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('session_ref', sa.String(16), nullable=True),
        sa.Column('origin', sa.String(64), nullable=True),
        sa.Column('request_path', sa.String(255), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index('ix_activity_events_case_at', 'activity_events', ['case_id', 'at'])
    op.create_index('ix_activity_events_user_at', 'activity_events', ['user_id', 'at'])
    op.create_index('ix_activity_events_action_at', 'activity_events', ['action', 'at'])
    op.execute('''CREATE FUNCTION guard_activity_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'The activity trail is append-only'; END $$''')
    op.execute('CREATE TRIGGER activity_events_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON activity_events '
               'FOR EACH STATEMENT EXECUTE FUNCTION guard_activity_events_immutable()')


def downgrade():
    op.execute('DROP TRIGGER activity_events_immutable ON activity_events')
    op.execute('DROP FUNCTION guard_activity_events_immutable()')
    op.drop_table('activity_events')
