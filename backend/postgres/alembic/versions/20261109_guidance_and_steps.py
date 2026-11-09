"""Guidance and step history (lx-guide).

- ``case_guidance``: a case admin's default for tours and tips, at most one row per case. A person's own choice (kept
  in ``phone_user_marks`` as ``guide:on`` or ``guide:off``) wins over it.
- ``case_steps``: one person's steps through one case (the history strip): the screen, the full view state and a
  plain name. Private to that person; kept 90 days.
- ``step_trail``: a run of steps added to a theory as one group (``case_selections`` and
  ``workspace_entry_links``).

New tables and one more allowed value in two checks; no existing row changes. The lists are written out here, not
imported, so this migration keeps meaning what it meant when it ran.
"""
from alembic import op

revision = "20261109_guidance_and_steps"
down_revision = "20261108_deleted_items_kinds"
branch_labels = None
depends_on = None

OLD = ("'evidence', 'graph_entity', 'dossier', 'entry', 'task', 'deadline', 'timeline_event', 'agent_artifact', 'witness', "
       "'phone_record', 'phone_file', 'phone_thread', 'phone_identity', 'phone_extraction', 'phone_analysis', "
       "'phone_selection', 'phone_view', 'statement_check', 'financial_account', 'financial_party', "
       "'financial_transaction', 'evidence_passage', 'graph_selection', 'significant_set', 'timeline_range', "
       "'financial_selection', 'evidence_selection', 'map_selection', 'agent_answer', 'interview'")
OLD_GROUPS = ("'graph_selection', 'significant_set', 'timeline_range', 'financial_selection', 'evidence_selection', "
              "'map_selection'")
NEW = "'step_trail'"


def upgrade():
    op.execute("""
        CREATE TABLE case_guidance (
          case_id         uuid PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
          guidance        text NOT NULL CHECK (guidance IN ('on', 'off')),
          set_by_user_id  uuid REFERENCES users(id) ON DELETE SET NULL,
          set_at          timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE case_steps (
          id       uuid PRIMARY KEY,
          case_id  uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          user_id  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          at       timestamptz NOT NULL DEFAULT now(),
          name     text NOT NULL,
          screen   text NOT NULL,
          path     text NOT NULL,
          state    jsonb NOT NULL DEFAULT '{}'::jsonb,
          item     jsonb
        );
        CREATE INDEX ix_case_steps_person ON case_steps (user_id, case_id, at DESC);
        CREATE INDEX ix_case_steps_at ON case_steps (at);
    """)
    op.drop_constraint("ck_case_selections_group_type", "case_selections", type_="check")
    op.create_check_constraint("ck_case_selections_group_type", "case_selections",
                               f"group_type IN ({OLD_GROUPS}, {NEW})")
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links",
                               f"target_type IN ({OLD}, {NEW})")


def downgrade():
    bind = op.get_bind()
    if bind.exec_driver_sql(f"SELECT count(*) FROM case_selections WHERE group_type IN ({NEW})").scalar():
        raise RuntimeError("Cannot remove the step trail type: theories hold trails of steps.")
    op.drop_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", type_="check")
    op.create_check_constraint("ck_workspace_entry_links_target_type", "workspace_entry_links", f"target_type IN ({OLD})")
    op.drop_constraint("ck_case_selections_group_type", "case_selections", type_="check")
    op.create_check_constraint("ck_case_selections_group_type", "case_selections", f"group_type IN ({OLD_GROUPS})")
    op.execute("DROP TABLE case_steps; DROP TABLE case_guidance")
