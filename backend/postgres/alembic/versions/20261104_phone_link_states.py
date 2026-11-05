"""Link states (docs/cellebrite/07 section 6.3; CO-8, CO-15).

A link's state is worked out when it is shown and the stored link is never rewritten. Two things a stored link cannot
hold are kept beside it:

``phone_reading_changes``: what a new reading of a phone changed on a collected record, written while both readings
exist (the earlier one is purged after the swap). ``phone_interpretation_state.reading_changes_since`` is the
generation these rows begin at: a link collected on an earlier generation was read again with no record of what
changed, and it says so.

``phone_link_choices``: the Keep or Remove of the person who added a link, one row per choice, never updated. It names
the link by id and has no foreign key to it, so the choice outlives a removal.

``phone_selections.collected_from`` names the finding or dossier a frozen export selection was gathered from, so the
export can carry the state of that container's links.
"""
from alembic import op

revision = "20261104_phone_link_states"
down_revision = "20261104_case_media_blur"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE phone_reading_changes (
  seq              bigserial PRIMARY KEY,
  case_id          uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id    uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  record_uid       uuid NOT NULL,
  field            varchar(16) NOT NULL CHECK (field IN ('sender', 'recipients', 'direction', 'time')),
  was_text         text,
  now_text         text,
  from_generation  integer NOT NULL,
  to_generation    integer NOT NULL,
  decision_id      uuid REFERENCES adjudications(id) ON DELETE RESTRICT,
  decided_by       text,
  changed_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_phone_reading_changes_case_record ON phone_reading_changes (case_id, record_uid);

CREATE TABLE phone_link_choices (
  id                uuid PRIMARY KEY,
  case_id           uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  link_kind         varchar(16) NOT NULL CHECK (link_kind IN ('entry', 'dossier', 'assessment')),
  link_id           uuid NOT NULL,
  container_id      uuid NOT NULL,
  target_type       varchar(32) NOT NULL,
  target_id         varchar(512) NOT NULL,
  choice            varchar(8) NOT NULL CHECK (choice IN ('keep', 'remove')),
  through_seq       bigint NOT NULL,
  records_affected  integer NOT NULL,
  chosen_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  chosen_by         text NOT NULL,
  chosen_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_phone_link_choices_link ON phone_link_choices (link_id, chosen_at);

ALTER TABLE phone_interpretation_state ADD COLUMN reading_changes_since integer NOT NULL DEFAULT 0;
UPDATE phone_interpretation_state SET reading_changes_since = generation;

ALTER TABLE phone_selections ADD COLUMN collected_from jsonb;
"""

DOWNGRADE = """
ALTER TABLE phone_selections DROP COLUMN IF EXISTS collected_from;
ALTER TABLE phone_interpretation_state DROP COLUMN IF EXISTS reading_changes_since;
DROP TABLE IF EXISTS phone_link_choices;
DROP TABLE IF EXISTS phone_reading_changes;
"""


def upgrade():
    op.execute(UPGRADE)


def downgrade():
    op.execute(DOWNGRADE)
