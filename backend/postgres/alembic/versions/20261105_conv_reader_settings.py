"""A person's stream density, and the lookup from a reply to the message it names (03 section 6.6, 07 section 4.4).

``phone_reader_settings``: one row per person, in no case, so the choice follows them across cases and browsers and
a view-only member can keep theirs. New table; no existing row changes.

``ix_phone_texts_message_identifier``: stream windows find a reply's original by the message ``Identifier``, which
sits in ``phone_texts`` already. Without an index that reads every message text of the phone on every window that
holds a reply. Partial (36,256 of the table's rows on 5 Nov, 138 MB table) and keyed on md5, so a long value can
never fail a write. No row changes. A build takes a SHARE lock: writers to ``phone_texts`` (a phone being read) wait
for it, readers do not; the release pauses that work first.
"""
from alembic import op

revision = "20261105_conv_reader_settings"
down_revision = "20261105_pv_identity_seen"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE phone_reader_settings (
          user_id        uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          stream_density varchar(16) NOT NULL DEFAULT 'comfortable'
                         CHECK (stream_density IN ('comfortable', 'compact')),
          updated_at     timestamptz NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_phone_texts_message_identifier
        ON phone_texts (extraction_id, generation, md5(value))
        WHERE model_type = 'InstantMessage' AND field_name = 'Identifier';
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_phone_texts_message_identifier")
    op.execute("DROP TABLE phone_reader_settings")
