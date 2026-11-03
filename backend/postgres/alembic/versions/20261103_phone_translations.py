"""Translations of phone messages and machine transcripts, made on this server (05 section 17.5).

Each row is a machine-generated translation beside its original (a message, keyed by the communication event's
stable ``event_uid``, or a finished machine text in ``phone_derived_texts``), never replacing it. It records the
detected language with its confidence and the detector, the model with its pinned revision and weights hash, the
parameters, and the SHA-256 of the exact text translated, so a translation of a text corrected since is known to be
of an earlier text. Text found to be English, or whose language is not identified with confidence, is stored with
that outcome and no translation.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_phone_translations"
down_revision = "20261103_phone_derive_batches"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "phone_translations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("source_sha256", sa.Text(), nullable=True),
        sa.Column("source_chars", sa.Integer(), nullable=True),
        sa.Column("detected_language", sa.Text(), nullable=True),
        sa.Column("detected_language_name", sa.Text(), nullable=True),
        sa.Column("detected_confidence", sa.Float(), nullable=True),
        sa.Column("detector", sa.Text(), nullable=True),
        sa.Column("detector_version", sa.Text(), nullable=True),
        sa.Column("target_language", sa.Text(), nullable=False, server_default="en"),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("text_folded", sa.Text(), nullable=True),
        sa.Column("segments", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("weights_sha256", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("solo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("source_type IN ('message', 'derived_text')", name="ck_phone_translations_source_type"),
        sa.CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name="ck_phone_translations_state"),
        sa.CheckConstraint("outcome IS NULL OR outcome IN ('translated', 'already_english', 'unsure')",
                           name="ck_phone_translations_outcome"),
        sa.CheckConstraint("state <> 'done' OR (outcome IS NOT NULL AND source_sha256 IS NOT NULL)",
                           name="ck_phone_translations_done"),
        sa.CheckConstraint("outcome IS DISTINCT FROM 'translated' OR (text IS NOT NULL AND model IS NOT NULL)",
                           name="ck_phone_translations_translated"),
    )
    op.create_index("ix_phone_translations_source", "phone_translations",
                    ["case_id", "source_type", "source_key", "created_at"])
    op.create_index("ix_phone_translations_queued", "phone_translations", ["created_at"],
                    postgresql_where=sa.text("state IN ('queued', 'running')"))
    # one open translation per source: a second request at the same moment inserts nothing and gets the open one
    op.execute("CREATE UNIQUE INDEX uq_phone_translations_open ON phone_translations (case_id, source_type, "
               "source_key) WHERE state IN ('queued', 'running')")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_phone_translations_open")
    op.drop_index("ix_phone_translations_queued", table_name="phone_translations")
    op.drop_index("ix_phone_translations_source", table_name="phone_translations")
    op.drop_table("phone_translations")
