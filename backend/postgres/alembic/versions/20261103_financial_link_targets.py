"""Workspace entries and dossiers can link the money: a financial account, a party and a ledger row (payment).

Workspace entry links take three more target types (financial_account, financial_party, financial_transaction), so a
pin holds a message (phone_record), the payment (financial_transaction) and the statement page (evidence with its
page in the anchor) as one bundle. Dossier links take the same types in the service (they have no database check).

``workspace_entries.actor_origin`` records that a model drafted an entry ({"kind": "model", "model", "model_id",
"for", "at"}, services/financial/model_work.model_origin); an entry a person accepted keeps it, so it shows
"Drafted by <model>, accepted by <name>". Existing rows are unchanged (nullable, starts empty).

The lists are written out here, not imported, so this migration keeps meaning what it meant when it ran.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_financial_link_targets"
down_revision = "20261103_pol_check_no_record"
branch_labels = None
depends_on = None

PHONE = "'phone_record', 'phone_file', 'phone_thread', 'phone_identity', 'phone_extraction', 'phone_analysis', 'phone_selection', 'phone_view', 'statement_check'"
WORKSPACE_OLD = "'evidence', 'graph_entity', 'dossier', 'entry', 'task', 'deadline', 'timeline_event', 'agent_artifact', 'witness'"
FINANCIAL = "'financial_account', 'financial_party', 'financial_transaction'"


def upgrade():
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links",
                               f"target_type IN ({WORKSPACE_OLD}, {PHONE}, {FINANCIAL})")
    op.add_column("workspace_entries", sa.Column("actor_origin", postgresql.JSONB(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT count(*) FROM workspace_entry_links WHERE target_type IN ({FINANCIAL})")).scalar_one():
        raise RuntimeError("Cannot remove the financial link types: workspace entries hold financial links.")
    op.drop_column("workspace_entries", "actor_origin")
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links",
                               f"target_type IN ({WORKSPACE_OLD}, {PHONE})")
