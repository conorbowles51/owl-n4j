"""Phone communications: comm events and threads from the type mappings (docs/cellebrite/02 sections 6.9, 12.2).

- ``phone_comm_events``: one row per message, call, email, voicemail or chat activity record a ``type`` mapping
  with a ``comm_kind`` covers; the event time is the mapping's event-time field, the body is complete.
- ``phone_threads``: one row per thread key (a chat, a counterpart set of top-level messages, a call log, an
  email folder and subject).
- ``phone_participations.implied_role``: the side an ``owner_implicit`` row fills (``caller``, ``callee``,
  ``sender``, ``recipient``), decided from the direction (5.3, owner side), so every call has both sides.

Views ``pv_comm_event``, ``pv_comm_party`` and ``pv_thread`` (12.2) read the current generation of active
extractions, as the generic views do. Downgrade drops them.
"""
from alembic import op

revision = "20261102_phone_comms"
down_revision = "20261102_phone_mappings"
branch_labels = None
depends_on = None

COMMON = """
  case_id              uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  extraction_id        uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
  interpretation_level varchar(24) NOT NULL
                       CHECK (interpretation_level IN ('captured_only','generic','applied_unconfirmed','reviewed')),
  mapping_version_id   uuid,
  mapping_row_id       varchar(160),
  generation           integer NOT NULL"""

UPGRADE = """
CREATE TABLE phone_comm_events (%(common)s,
  event_uid        uuid NOT NULL,
  record_uid       uuid NOT NULL,
  document_index   smallint NOT NULL,
  ordinal          integer NOT NULL,
  locator          text NOT NULL,
  model_type       varchar(128) NOT NULL,
  kind             varchar(16) NOT NULL CHECK (kind IN ('message','call','email','voicemail','chat_activity')),
  thread_key       text,
  app              text,
  direction        varchar(16) NOT NULL CHECK (direction IN ('incoming','outgoing','unknown')),
  direction_basis  varchar(24),
  sort_instant     timestamptz,
  time_field       varchar(256),
  time_uid         uuid,
  end_instant      timestamptz,
  end_basis        varchar(16),
  body             text,
  subject          text,
  status           text,
  call_duration_s  numeric(18,7),
  call_status      text,
  video            boolean,
  deleted_state    varchar(32),
  flags            text[] NOT NULL DEFAULT '{}',
  dup_group_uid    text,
  dup_rule_version integer,
  PRIMARY KEY (event_uid, generation)
);
CREATE INDEX ix_phone_comm_events_ext ON phone_comm_events (case_id, extraction_id, kind);
CREATE INDEX ix_phone_comm_events_thread ON phone_comm_events (thread_key, sort_instant);
CREATE INDEX ix_phone_comm_events_instant ON phone_comm_events (case_id, sort_instant);
CREATE INDEX ix_phone_comm_events_record ON phone_comm_events (record_uid);

CREATE TABLE phone_threads (%(common)s,
  thread_key          text NOT NULL,
  record_uid          uuid,
  app                 text,
  thread_kind         varchar(16) NOT NULL CHECK (thread_kind IN ('chat','sms_group','call_log','email_folder','voicemail')),
  chat_type           text,
  title_in_record     text,
  first_instant       timestamptz,
  last_instant        timestamptz,
  event_count         integer NOT NULL DEFAULT 0,
  party_identity_keys text[] NOT NULL DEFAULT '{}',
  PRIMARY KEY (thread_key, generation)
);
CREATE INDEX ix_phone_threads_ext ON phone_threads (case_id, extraction_id);

ALTER TABLE phone_participations ADD COLUMN implied_role varchar(16);
"""

VIEWS = """
CREATE VIEW pv_comm_event AS
SELECT ev.event_uid, ev.record_uid, ev.extraction_id, ev.case_id, ev.kind, ev.thread_key, ev.app, ev.direction,
       ev.sort_instant, ev.time_field, ev.end_instant, ev.end_basis, ev.body, ev.subject, ev.status,
       ev.call_duration_s, ev.call_status, ev.video, ev.dup_group_uid, ev.dup_rule_version, ev.interpretation_level,
       ev.mapping_version_id, ev.mapping_row_id, ev.deleted_state, ev.flags, ev.locator, ev.model_type
FROM phone_comm_events ev
JOIN phone_interpretation_state s ON s.extraction_id = ev.extraction_id AND s.generation = ev.generation
JOIN phone_extractions e ON e.id = ev.extraction_id AND e.standing = 'active';

CREATE VIEW pv_comm_party AS
SELECT ev.event_uid, p.participation_uid, p.identity_key, p.role, p.role_basis, p.implied_role, p.role_in_record,
       p.name_in_record, p.identifier_raw, p.is_phone_owner, p.date_read, p.date_delivered, p.date_played,
       p.interpretation_level, p.mapping_version_id, p.mapping_row_id, p.flags, ev.extraction_id, ev.case_id
FROM phone_comm_events ev
JOIN phone_participations p ON p.record_uid = ev.record_uid AND p.generation = ev.generation
JOIN phone_interpretation_state s ON s.extraction_id = ev.extraction_id AND s.generation = ev.generation
JOIN phone_extractions e ON e.id = ev.extraction_id AND e.standing = 'active';

CREATE VIEW pv_thread AS
SELECT t.thread_key, t.extraction_id, t.case_id, t.record_uid, t.app, t.thread_kind, t.chat_type, t.title_in_record,
       t.first_instant, t.last_instant, t.event_count, t.party_identity_keys, t.interpretation_level,
       t.mapping_version_id, t.mapping_row_id
FROM phone_threads t
JOIN phone_interpretation_state s ON s.extraction_id = t.extraction_id AND s.generation = t.generation
JOIN phone_extractions e ON e.id = t.extraction_id AND e.standing = 'active';
"""


def upgrade():
    op.execute(UPGRADE % {"common": COMMON})
    op.execute(VIEWS)


def downgrade():
    op.execute("DROP VIEW pv_thread; DROP VIEW pv_comm_party; DROP VIEW pv_comm_event;")
    op.execute("ALTER TABLE phone_participations DROP COLUMN implied_role;")
    op.execute("DROP TABLE phone_threads; DROP TABLE phone_comm_events;")
