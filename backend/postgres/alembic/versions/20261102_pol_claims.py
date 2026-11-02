"""Pattern of life: statement claims and their evaluations (docs/cellebrite/04 sections 7.8 and 9, unit U11).

- ``pol_claim``: a statement to test. ``confirmed`` needs a confirming user and a window (CHECK).
- ``pol_claim_revision``: an immutable copy of every version.
- ``pol_claim_evaluation`` and ``pol_claim_evaluation_item``: a computed result with the inputs it read and their
  sha256 fingerprint; every item is stored (no limit).
- ``pol_claim_item_dispute``: "This item is wrong", with a typed reason; the outcome is never set by hand.
- Decisions ``dispute_check_item`` and ``withdraw_check_item_dispute`` join ``ck_adjudications_decision``.
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "20261102_pol_claims"
down_revision = "20261102_pol_money"
branch_labels = None
depends_on = None

NEW = ("dispute_check_item", "withdraw_check_item_dispute")

DDL = """
CREATE TABLE pol_claim (
  id                   uuid PRIMARY KEY,
  case_id              uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  version              integer NOT NULL DEFAULT 1,
  status               varchar(12) NOT NULL CHECK (status IN ('draft','confirmed','withdrawn')),
  kind                 varchar(24) NOT NULL CHECK (kind IN ('inactive','active','at_place','not_at_place',
                         'with_subject','apart_from_subject','no_contact','contact')),
  subject              jsonb NOT NULL,
  window_start         timestamptz,
  window_end           timestamptz,
  window_zone          varchar(64),
  window_text          text,
  place                jsonb,
  activity             jsonb,
  counterpart          jsonb,
  origin               varchar(12) NOT NULL CHECK (origin IN ('manual','ai_draft')),
  source_anchor        jsonb,
  ai_output_id         uuid,
  ai_model             varchar(160),
  created_by_user_id   uuid,
  created_by_name      varchar(300) NOT NULL,
  confirmed_by_user_id uuid,
  confirmed_by_name    varchar(300),
  confirmed_at         timestamptz,
  withdrawn_reason     text,
  created_at           timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at           timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ck_pol_claim_confirmed CHECK (status <> 'confirmed' OR (confirmed_by_user_id IS NOT NULL
    AND confirmed_at IS NOT NULL AND window_start IS NOT NULL AND window_end IS NOT NULL AND window_end > window_start)),
  CONSTRAINT ck_pol_claim_ai_draft CHECK (origin <> 'ai_draft' OR ai_output_id IS NOT NULL)
);
CREATE INDEX ix_pol_claim_case ON pol_claim (case_id, status);

CREATE TABLE pol_claim_revision (
  claim_id        uuid NOT NULL REFERENCES pol_claim(id) ON DELETE CASCADE,
  version         integer NOT NULL,
  snapshot        jsonb NOT NULL,
  changed_by_name varchar(300) NOT NULL,
  changed_by_user_id uuid,
  change          varchar(16) NOT NULL CHECK (change IN ('create','edit','confirm','withdraw')),
  changed_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (claim_id, version)
);

CREATE TABLE pol_claim_evaluation (
  id                 uuid PRIMARY KEY,
  case_id            uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  claim_id           uuid NOT NULL REFERENCES pol_claim(id) ON DELETE CASCADE,
  claim_version      integer NOT NULL,
  evaluated_at       timestamptz NOT NULL DEFAULT clock_timestamp(),
  requested_by       varchar(300) NOT NULL,
  inputs             jsonb NOT NULL,
  inputs_fingerprint char(64) NOT NULL,
  outcome            varchar(24) NOT NULL CHECK (outcome IN ('contradicted','contradicted_weakly','consistent',
                       'supported','mixed','insufficient_data')),
  outcome_basis      text NOT NULL,
  summary            jsonb NOT NULL DEFAULT '{}'::jsonb,
  counts             jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ix_pol_claim_evaluation_claim ON pol_claim_evaluation (claim_id, evaluated_at);

CREATE TABLE pol_claim_evaluation_item (
  evaluation_id uuid NOT NULL REFERENCES pol_claim_evaluation(id) ON DELETE CASCADE,
  ordinal       integer NOT NULL,
  role          varchar(16) NOT NULL CHECK (role IN ('contradicting','supporting','context','gap')),
  ref_kind      varchar(20) NOT NULL CHECK (ref_kind IN ('activity_event','place_observation','band','colocation',
                  'transaction','comm_event','window_piece')),
  ref_id        text NOT NULL,
  strength      varchar(8),
  reason_code   varchar(48) NOT NULL,
  explanation   text NOT NULL,
  record_uid    uuid,
  field_path    text,
  extraction_id uuid,
  at_utc        timestamptz,
  end_utc       timestamptz,
  display       jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (evaluation_id, ordinal)
);

CREATE TABLE pol_claim_item_dispute (
  id                    uuid PRIMARY KEY,
  case_id               uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  evaluation_id         uuid NOT NULL REFERENCES pol_claim_evaluation(id) ON DELETE CASCADE,
  ordinal               integer NOT NULL,
  ref_kind              varchar(20) NOT NULL,
  ref_id                text NOT NULL,
  reason                text NOT NULL CHECK (btrim(reason) <> ''),
  decision_id           uuid,
  actor_name            varchar(300) NOT NULL,
  actor_email           varchar(300) NOT NULL,
  created_at            timestamptz NOT NULL DEFAULT clock_timestamp(),
  withdrawn_decision_id uuid,
  withdrawn_at          timestamptz
);
CREATE UNIQUE INDEX ux_pol_claim_item_dispute_open ON pol_claim_item_dispute (evaluation_id, ordinal)
  WHERE withdrawn_at IS NULL;
"""


def _members(bind):
    d = bind.execute(sa.text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_adjudications_decision'")).scalar_one()
    return re.findall(r"'([a-z_]+)'", d)


def _rebuild(members):
    op.drop_constraint("ck_adjudications_decision", "adjudications", type_="check")
    op.create_check_constraint("ck_adjudications_decision", "adjudications",
                               "decision IN (%s)" % ", ".join("'%s'" % m for m in members))


def upgrade():
    bind = op.get_bind()
    have = _members(bind)
    _rebuild(have + [m for m in NEW if m not in have])
    for stmt in [s for s in DDL.split(";") if s.strip()]:
        op.execute(stmt)


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM adjudications WHERE decision IN :d").bindparams(
            sa.bindparam("d", expanding=True)), {"d": list(NEW)}).scalar_one():
        raise RuntimeError("Check item disputes are recorded; removing the members would orphan them.")
    for t in ("pol_claim_item_dispute", "pol_claim_evaluation_item", "pol_claim_evaluation", "pol_claim_revision",
              "pol_claim"):
        op.execute("DROP TABLE %s" % t)
    _rebuild([m for m in _members(bind) if m not in NEW])
