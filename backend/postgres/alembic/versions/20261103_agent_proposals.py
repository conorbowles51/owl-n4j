"""The case agent's only write is a proposal a person decides (agent-proposals A-F).

* ``financial_judgements``: a proposal can be ``rejected`` (wrong, nothing to change), as well as confirmed or
  corrected; a judgement call can be about a proceeds ``calculation`` (each assumption is its own call); a call a
  person set (an assumption with its source) has origin ``person``.
* ``workspace_ai_outputs``: target ``case`` and five drafted kinds (a Workspace entry, a lead card, a timeline
  addition, a link, an alternative explanation from the red cell); the mandate is recorded when the case has one
  (6 of 8 live cases have none on 2026-11-03, and an agent proposal is not a mandate-scoped generation).
* ``agent_proposal_source_opens``: each cited source a person opened from a proposal, so a confirmation records
  whether its source was opened first.
* ``proceeds_calculations``: a deterministic proceeds calculation; its assumptions are judgement calls on it.

Existing rows are unchanged: every check only widens, the new tables start empty, and the mandate column keeps
every stored value.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_agent_proposals"
down_revision = "20261103_merge_audio_review"
branch_labels = None
depends_on = None

OLD = dict(
    subject="subject_type IN ('transaction', 'statement_period', 'source_document', 'account', 'evidence_file')",
    status="status IN ('open', 'confirmed', 'corrected')",
    origin="origin IN ('processor', 'agent')",
    target="target_type IN ('dossier', 'theory')",
    output="output_type IN ('statement_summary', 'statement_comparison', 'theory_analysis', 'statement_claims')",
)
NEW = dict(
    subject="subject_type IN ('transaction', 'statement_period', 'source_document', 'account', 'evidence_file', "
            "'calculation')",
    status="status IN ('open', 'confirmed', 'corrected', 'rejected')",
    origin="origin IN ('processor', 'agent', 'person')",
    target="target_type IN ('dossier', 'theory', 'case')",
    output="output_type IN ('statement_summary', 'statement_comparison', 'theory_analysis', 'statement_claims', "
           "'entry_draft', 'lead_card', 'timeline_addition', 'link_proposal', 'alternative_explanation')",
)
NAMES = dict(subject=("financial_judgements", "ck_financial_judgements_subject"),
             status=("financial_judgements", "ck_financial_judgements_status"),
             origin=("financial_judgements", "ck_financial_judgements_origin"),
             target=("workspace_ai_outputs", "ck_workspace_ai_outputs_target_type"),
             output=("workspace_ai_outputs", "ck_workspace_ai_outputs_output_type"))


def _swap(checks):
    for key, (table, name) in NAMES.items():
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, checks[key])


def upgrade():
    _swap(NEW)
    op.alter_column("workspace_ai_outputs", "mandate_version_id", existing_type=postgresql.UUID(as_uuid=True),
                    nullable=True)
    op.create_table(
        "agent_proposal_source_opens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("proposal_type", sa.String(24), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("citation", sa.String(600), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("proposal_type IN ('judgement', 'workspace_ai')", name="ck_agent_proposal_opens_type"),
    )
    op.create_index("ix_agent_proposal_opens_proposal", "agent_proposal_source_opens",
                    ["proposal_type", "proposal_id", "user_id"])
    op.create_index("ix_agent_proposal_opens_case", "agent_proposal_source_opens", ["case_id", "opened_at"])
    op.create_table(
        "proceeds_calculations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("deposit_categories", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_by_email", sa.String(255), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("proceeds_calculations")
    op.drop_index("ix_agent_proposal_opens_case", table_name="agent_proposal_source_opens")
    op.drop_index("ix_agent_proposal_opens_proposal", table_name="agent_proposal_source_opens")
    op.drop_table("agent_proposal_source_opens")
    op.alter_column("workspace_ai_outputs", "mandate_version_id", existing_type=postgresql.UUID(as_uuid=True),
                    nullable=False)
    _swap(OLD)
