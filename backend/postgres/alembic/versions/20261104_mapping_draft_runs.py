"""AI mapping draft runs (02 section 6.8 step 2, cb-mapdrafts C).

``phone_mapping_draft_runs``: one row per ``POST /api/phones/registry/mapping-drafts``. A draft reads the registry's
structure for one type (or named set) and asks the ``phone_mapping_draft`` workload's model for a mapping; at max
thinking that takes minutes, so it runs in the background and the admin page reads its state here. A finished run
names the proposal it stored (``phone_mapping_proposals``, ``origin = ai_draft``: state ``draft`` when the answer is a
valid mapping, ``rejected`` with the reason when it is not) or, when no answer came back, the error. The model, time,
tokens and cost are kept on the run. Nothing at interpretation time reads this table. New table; no existing row
changes.
"""
from alembic import op

revision = "20261104_mapping_draft_runs"
down_revision = "20261104_transaction_numbers"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS phone_mapping_draft_runs (
            id uuid PRIMARY KEY,
            kind varchar(32) NOT NULL,
            name varchar(128) NOT NULL,
            status varchar(16) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','drafted','invalid','failed')),
            provider varchar(32),
            model varchar(128),
            input_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            proposal_id uuid REFERENCES phone_mapping_proposals(id) ON DELETE SET NULL,
            error text,
            seconds double precision,
            prompt_tokens integer,
            completion_tokens integer,
            cost_usd double precision,
            requested_by_name varchar(255),
            requested_by_email varchar(255),
            requested_by_user_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            finished_at timestamptz
        );
        CREATE INDEX IF NOT EXISTS ix_phone_mapping_draft_runs_created ON phone_mapping_draft_runs (created_at DESC);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS phone_mapping_draft_runs")
