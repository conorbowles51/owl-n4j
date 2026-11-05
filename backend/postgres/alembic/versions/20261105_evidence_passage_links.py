"""Workspace entries can hold a quote: one range of a document's stored text (lx-textbench).

A new target type because an entry holds a target once and may hold several quotes of one document. Dossier links take
the same type in the service (they have no database check). Existing rows are unchanged.

The lists are written out here, not imported, so this migration keeps meaning what it meant when it ran.
"""
import sqlalchemy as sa
from alembic import op

revision = "20261105_evidence_passage_links"
down_revision = "20261105_agent_disconfirm"
branch_labels = None
depends_on = None

OLD = ("'evidence', 'graph_entity', 'dossier', 'entry', 'task', 'deadline', 'timeline_event', 'agent_artifact', 'witness', "
       "'phone_record', 'phone_file', 'phone_thread', 'phone_identity', 'phone_extraction', 'phone_analysis', "
       "'phone_selection', 'phone_view', 'statement_check', 'financial_account', 'financial_party', "
       "'financial_transaction'")


def upgrade():
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links",
                               f"target_type IN ({OLD}, 'evidence_passage')")


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM workspace_entry_links WHERE target_type = 'evidence_passage'")).scalar_one():
        raise RuntimeError("Cannot remove the quote link type: workspace entries hold quotes.")
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links",
                               f"target_type IN ({OLD})")
