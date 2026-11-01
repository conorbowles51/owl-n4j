"""Workspace and task links take their target types from the one link-type registry, which adds the phone types.

The lists are written out here, not imported, so this migration keeps meaning what it meant when it ran.
Existing rows are untouched: every old type stays allowed.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261101_link_registry'
down_revision = '20261101_manual_changes'
branch_labels = None
depends_on = None

PHONE = "'phone_record', 'phone_file', 'phone_thread', 'phone_identity', 'phone_extraction', 'phone_analysis', 'phone_selection', 'phone_view', 'statement_check'"
WORKSPACE_OLD = "'evidence', 'graph_entity', 'dossier', 'entry', 'task', 'deadline', 'timeline_event', 'agent_artifact', 'witness'"
TASK_OLD = "'dossier', 'entry', 'evidence'"


def upgrade():
    op.drop_constraint('ck_workspace_entry_links_target_type', 'workspace_entry_links', type_='check')
    op.create_check_constraint('ck_workspace_entry_links_target_type', 'workspace_entry_links', f"target_type IN ({WORKSPACE_OLD}, {PHONE})")
    op.drop_constraint('ck_case_task_links_target_type', 'case_task_links', type_='check')
    op.create_check_constraint('ck_case_task_links_target_type', 'case_task_links', f"target_type IN ({TASK_OLD}, {PHONE})")


def downgrade():
    bind = op.get_bind()
    for table in ('workspace_entry_links', 'case_task_links'):
        if bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE target_type IN ({PHONE})")).scalar_one():
            raise RuntimeError(f'Cannot remove phone link types: {table} holds phone links.')
    op.drop_constraint('ck_workspace_entry_links_target_type', 'workspace_entry_links', type_='check')
    op.create_check_constraint('ck_workspace_entry_links_target_type', 'workspace_entry_links', f"target_type IN ({WORKSPACE_OLD})")
    op.drop_constraint('ck_case_task_links_target_type', 'case_task_links', type_='check')
    op.create_check_constraint('ck_case_task_links_target_type', 'case_task_links', f"target_type IN ({TASK_OLD})")
