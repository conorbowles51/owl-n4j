"""Mapping proposal events (02 sections 3.4 and 6.8, cb-registry-admin B).

``phone_mapping_proposal_events``: append-only history of a proposal's state changes (``draft`` -> ``exported`` when
an admin downloads its file, ``draft``/``exported`` -> ``rejected`` with a reason). Each event is written before the
proposal's state changes, the rule 3.4 sets for registry flags (``decisions.py:22-23``). The registry is global, so
case ``adjudications`` rows cannot hold these. New table; no existing row changes (live 2026-11-04: 0 proposals).
"""
from alembic import op

revision = "20261104_proposal_events"
down_revision = "20261104_phone_views"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS phone_mapping_proposal_events (
            id bigserial PRIMARY KEY,
            proposal_id uuid NOT NULL REFERENCES phone_mapping_proposals(id) ON DELETE CASCADE,
            from_state varchar(16) NOT NULL,
            to_state varchar(16) NOT NULL,
            reason text NOT NULL,
            actor_name varchar(255),
            actor_email varchar(255),
            actor_user_id uuid,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_phone_mapping_proposal_events_proposal
            ON phone_mapping_proposal_events (proposal_id, id);
        CREATE INDEX IF NOT EXISTS ix_phone_mapping_proposals_state_origin
            ON phone_mapping_proposals (state, origin, created_at);
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_phone_mapping_proposals_state_origin; "
               "DROP TABLE IF EXISTS phone_mapping_proposal_events")
