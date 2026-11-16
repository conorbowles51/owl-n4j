"""Look into how these relate (lx-overlaps).

- ``relation_query``: one more kind of group in ``case_selections`` and one more link target type, so a group of items
  from any screen can be saved and added to a theory.
- ``relation_runs``: one run of the link analysis on one such group: its status and progress while it works, the
  engine's result (candidate links, searched-no-link, what was out of reach), and the hypotheses a model drafted from
  it, kept as a model reading with its citations until a person accepts them.

The check lists are written out here, not imported, so this migration keeps meaning what it meant when it ran.
"""
from alembic import op

revision = "20261113_relation_queries"
down_revision = "20261112_timeline_event_files"
branch_labels = None
depends_on = None

OLD = ("'evidence', 'graph_entity', 'dossier', 'entry', 'task', 'deadline', 'timeline_event', 'agent_artifact', 'witness', "
       "'phone_record', 'phone_file', 'phone_thread', 'phone_identity', 'phone_extraction', 'phone_analysis', "
       "'phone_selection', 'phone_view', 'statement_check', 'financial_account', 'financial_party', "
       "'financial_transaction', 'evidence_passage', 'graph_selection', 'significant_set', 'timeline_range', "
       "'financial_selection', 'evidence_selection', 'map_selection', 'step_trail', 'agent_answer', 'interview'")
OLD_GROUPS = ("'graph_selection', 'significant_set', 'timeline_range', 'financial_selection', 'evidence_selection', "
              "'map_selection', 'step_trail'")
NEW = "'relation_query'"


def upgrade():
    op.drop_constraint("ck_case_selections_group_type", "case_selections", type_="check")
    op.create_check_constraint("ck_case_selections_group_type", "case_selections", f"group_type IN ({OLD_GROUPS}, {NEW})")
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", f"target_type IN ({OLD}, {NEW})")
    op.execute("""
        CREATE TABLE relation_runs (
          id            uuid PRIMARY KEY,
          case_id       uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          selection_id  uuid NOT NULL REFERENCES case_selections(id) ON DELETE CASCADE,
          status        text NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')),
          step          text NOT NULL DEFAULT '',
          progress      jsonb NOT NULL DEFAULT '{}'::jsonb,
          result        jsonb,
          hypotheses    jsonb,
          error         text,
          requested_by  uuid REFERENCES users(id) ON DELETE SET NULL,
          created_at    timestamptz NOT NULL DEFAULT now(),
          finished_at   timestamptz
        );
        CREATE INDEX ix_relation_runs_case ON relation_runs (case_id, created_at DESC);
        CREATE INDEX ix_relation_runs_selection ON relation_runs (selection_id, created_at DESC);
    """)


def downgrade():
    bind = op.get_bind()
    if bind.exec_driver_sql(f"SELECT count(*) FROM case_selections WHERE group_type IN ({NEW})").scalar():
        raise RuntimeError("Cannot remove the relation query type: cases hold such groups.")
    op.execute("DROP TABLE relation_runs")
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", f"target_type IN ({OLD})")
    op.drop_constraint("ck_case_selections_group_type", "case_selections", type_="check")
    op.create_check_constraint("ck_case_selections_group_type", "case_selections", f"group_type IN ({OLD_GROUPS})")
