"""Everything in a case can be added to a theory, one item or a group (lx-theorybuild).

A group (a graph selection, a set from the Significant layer, a timeline range, a ledger selection, a set of
evidence files or a map area) is stored once in ``case_selections`` with every member and how it was chosen, and
linked as one row. A chat answer from the agent is linked as ``agent_answer``; an interview as ``interview``. Each addition, and each theory as a
whole, carries narratives in ``theory_narratives`` (person-written or a model reading). Existing rows are unchanged.

The lists are written out here, not imported, so this migration keeps meaning what it meant when it ran.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261108_case_selections"
down_revision = "20261106_vision_spend_recorded"
branch_labels = None
depends_on = None

OLD = ("'evidence', 'graph_entity', 'dossier', 'entry', 'task', 'deadline', 'timeline_event', 'agent_artifact', 'witness', "
       "'phone_record', 'phone_file', 'phone_thread', 'phone_identity', 'phone_extraction', 'phone_analysis', "
       "'phone_selection', 'phone_view', 'statement_check', 'financial_account', 'financial_party', "
       "'financial_transaction', 'evidence_passage'")
NEW = ("'graph_selection', 'significant_set', 'timeline_range', 'financial_selection', 'evidence_selection', "
       "'map_selection', 'agent_answer', 'interview'")
GROUPS = ("'graph_selection', 'significant_set', 'timeline_range', 'financial_selection', 'evidence_selection', "
          "'map_selection'")


def upgrade():
    op.create_table(
        "case_selections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_type", sa.String(32), nullable=False),
        sa.Column("words", sa.Text(), nullable=False),
        sa.Column("how", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("members", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("left_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"group_type IN ({GROUPS})", name="ck_case_selections_group_type"),
        sa.CheckConstraint("member_count >= 0 AND left_out >= 0", name="ck_case_selections_counts"),
    )
    op.create_index("ix_case_selections_case", "case_selections", ["case_id", "created_at"])
    op.create_table(
        "theory_narratives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspace_entries.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspace_entry_links.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("citations", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("basis", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("replaces_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("theory_narratives.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("origin IN ('person', 'agent')", name="ck_theory_narratives_origin"),
        sa.CheckConstraint("origin = 'person' OR model IS NOT NULL", name="ck_theory_narratives_model_named"),
    )
    op.create_index("ix_theory_narratives_entry", "theory_narratives", ["entry_id", "link_id", "created_at"])
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links",
                               f"target_type IN ({OLD}, {NEW})")


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT count(*) FROM workspace_entry_links WHERE target_type IN ({NEW})")).scalar_one():
        raise RuntimeError("Cannot remove the group link types: workspace entries hold groups or agent answers.")
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links",
                               f"target_type IN ({OLD})")
    op.drop_index("ix_theory_narratives_entry", table_name="theory_narratives")
    op.drop_table("theory_narratives")
    op.drop_index("ix_case_selections_case", table_name="case_selections")
    op.drop_table("case_selections")
