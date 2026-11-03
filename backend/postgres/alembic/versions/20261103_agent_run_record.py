"""The agent run record is the disclosure record (report rank 3; AG Guidelines 2024 Annex A paras 47-48).

``agent_runs`` gains the prompt version (sha256 and readable label), the person the run was for as named at the
time, the tool budget and how much of it was used, the calls the budget stopped, and a summary of what was and was
not examined. ``agent_tool_calls`` gains, per call, the result's total, returned and next page, the ledger revision
and phone generation read, the search terms, what the model was shown (its paging notes) and what was clipped.
``agent_prompt_versions`` keeps the full text of every prompt version; ``agent_run_items`` keeps each returned item
and whether the run opened, cited or used it.

Retention: ``agent_threads.owner_user_id`` changes from ON DELETE CASCADE to RESTRICT, so removing a person can
never erase a live case's run records. Records still go with their case (case delete cascades, unchanged).
Existing rows are unchanged; every new column is nullable.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_agent_run_record"
down_revision = "20261103_assessment_agent_message"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade():
    for name, kind in (("prompt_version", sa.String(64)), ("prompt_version_label", sa.String(100)),
                       ("for_user_name", sa.String(255)), ("for_user_email", sa.String(255)),
                       ("tool_budget", sa.Integer()), ("tool_calls_used", sa.Integer()),
                       ("unrun_tool_calls", JSONB), ("record_summary", JSONB)):
        op.add_column("agent_runs", sa.Column(name, kind, nullable=True))
    op.create_index("ix_agent_runs_prompt_version", "agent_runs", ["prompt_version"])
    for name, kind in (("total", sa.Integer()), ("returned", sa.Integer()), ("next_page", JSONB),
                       ("ledger_revision", sa.String(64)), ("page_revision", sa.String(64)),
                       ("phone_generation", sa.Text()), ("search_terms", JSONB), ("model_paging", JSONB),
                       ("model_not_shown", sa.Integer()), ("tool_not_returned", sa.Integer()),
                       ("continuation_of", sa.Integer()), ("record_facts", JSONB)):
        op.add_column("agent_tool_calls", sa.Column(name, kind, nullable=True))
    op.create_table(
        "agent_prompt_versions",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("first_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tool_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_text", JSONB, nullable=False),
        sa.Column("tool_schemas", JSONB, nullable=False),
    )
    op.create_table(
        "agent_run_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_call_sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("ref", sa.String(500), nullable=False),
        sa.Column("label", sa.String(500), nullable=True),
        sa.Column("list_path", sa.String(100), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("shown_to_model", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("opened", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("opened_by_sequence", sa.Integer(), nullable=True),
        sa.Column("cited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("in_artifact", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_agent_run_items_run_id", "agent_run_items", ["run_id"])
    op.drop_constraint("agent_threads_owner_user_id_fkey", "agent_threads", type_="foreignkey")
    op.create_foreign_key("agent_threads_owner_user_id_fkey", "agent_threads", "users", ["owner_user_id"], ["id"],
                          ondelete="RESTRICT")


def downgrade():
    op.drop_constraint("agent_threads_owner_user_id_fkey", "agent_threads", type_="foreignkey")
    op.create_foreign_key("agent_threads_owner_user_id_fkey", "agent_threads", "users", ["owner_user_id"], ["id"],
                          ondelete="CASCADE")
    op.drop_index("ix_agent_run_items_run_id", table_name="agent_run_items")
    op.drop_table("agent_run_items")
    op.drop_table("agent_prompt_versions")
    for name in ("total", "returned", "next_page", "ledger_revision", "page_revision", "phone_generation",
                 "search_terms", "model_paging", "model_not_shown", "tool_not_returned", "continuation_of",
                 "record_facts"):
        op.drop_column("agent_tool_calls", name)
    op.drop_index("ix_agent_runs_prompt_version", table_name="agent_runs")
    for name in ("prompt_version", "prompt_version_label", "for_user_name", "for_user_email", "tool_budget",
                 "tool_calls_used", "unrun_tool_calls", "record_summary"):
        op.drop_column("agent_runs", name)
