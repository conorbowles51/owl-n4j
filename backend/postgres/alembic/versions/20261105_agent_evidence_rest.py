"""What the agent report promised and only prompt wording held (agent-evidence-rest C, D, E, F).

* ``workspace_ai_outputs``: three more drafted kinds: a statement claim, an entity for the graph, a code-word term.
* ``case_glossary_terms``: a code word whose meaning a named person confirmed. The model's reading stays beside it.
* ``phone_monitoring_app_entries``: a case's edits to the monitoring-app list: an identifier a person added with its
  source, a list entry a person reviewed, or one a person set aside for this case with the reason.

Existing rows are unchanged: the check only widens and both tables start empty.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261105_agent_evidence_rest"
down_revision = "20261105_phone_person_settings"
branch_labels = None
depends_on = None

BASE = ("'statement_summary', 'statement_comparison', 'theory_analysis', 'statement_claims', 'entry_draft', "
        "'lead_card', 'timeline_addition', 'link_proposal', 'alternative_explanation', 'control_claim', "
        "'payment_purpose'")
ADDED = "'statement_claim', 'entity_proposal', 'glossary_term'"
NAME = "ck_workspace_ai_outputs_output_type"


def upgrade():
    op.drop_constraint(NAME, "workspace_ai_outputs", type_="check")
    op.create_check_constraint(NAME, "workspace_ai_outputs", "output_type IN (%s, %s)" % (BASE, ADDED))
    op.create_table(
        "case_glossary_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("term", sa.String(200), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column("model_meaning", sa.Text(), nullable=True),
        sa.Column("speaker", sa.String(255), nullable=True),
        sa.Column("citations", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="confirmed"),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("confirmed_by_name", sa.String(255), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("withdrawn_by_name", sa.String(255), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True),
        sa.Column("keyword_list_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("keyword_list_note", sa.Text(), nullable=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspace_ai_outputs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("origin", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint("status IN ('confirmed', 'withdrawn')", name="ck_case_glossary_terms_status"),
    )
    op.create_index("ix_case_glossary_terms_case", "case_glossary_terms", ["case_id", "status"])
    op.create_index("uq_case_glossary_term_confirmed", "case_glossary_terms",
                    ["case_id", sa.text("lower(term)")], unique=True, postgresql_where=sa.text("status = 'confirmed'"))
    op.create_table(
        "phone_monitoring_app_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("identifier", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_by_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("removed_by_name", sa.String(255), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("action IN ('add', 'reviewed', 'set_aside')", name="ck_phone_monitoring_app_action"),
    )
    op.create_index("uq_phone_monitoring_app_entry", "phone_monitoring_app_entries",
                    ["case_id", sa.text("lower(identifier)")], unique=True,
                    postgresql_where=sa.text("removed_at IS NULL"))


def downgrade():
    op.drop_table("phone_monitoring_app_entries")
    op.drop_table("case_glossary_terms")
    op.drop_constraint(NAME, "workspace_ai_outputs", type_="check")
    op.execute("DELETE FROM workspace_ai_outputs WHERE output_type IN (%s)" % ADDED)
    op.create_check_constraint(NAME, "workspace_ai_outputs", "output_type IN (%s)" % BASE)
