"""add timed audio transcript segments and editable speaker names

Revision ID: 20260724_audio_segments
Revises: 20260722_ai_provider_credentials
"""

from typing import Union

from alembic import op


revision: str = "20260724_audio_segments"
down_revision: Union[str, None] = "20260722_ai_provider_credentials"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE jobs "
        "ADD COLUMN IF NOT EXISTS transcription_segments JSONB NULL"
    )
    op.execute(
        "ALTER TABLE evidence_files "
        "ADD COLUMN IF NOT EXISTS transcription_segments JSONB NULL"
    )
    op.execute(
        "ALTER TABLE evidence_files "
        "ADD COLUMN IF NOT EXISTS transcription_speakers JSONB "
        "NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE evidence_files "
        "DROP COLUMN IF EXISTS transcription_speakers"
    )
    op.execute(
        "ALTER TABLE evidence_files "
        "DROP COLUMN IF EXISTS transcription_segments"
    )
    op.execute(
        "ALTER TABLE jobs "
        "DROP COLUMN IF EXISTS transcription_segments"
    )
