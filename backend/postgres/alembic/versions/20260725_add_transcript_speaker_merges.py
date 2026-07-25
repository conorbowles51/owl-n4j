"""add investigator-defined transcript speaker merges

Revision ID: 20260725_speaker_merges
Revises: 20260724_audio_segments
"""

from typing import Union

from alembic import op


revision: str = "20260725_speaker_merges"
down_revision: Union[str, None] = "20260724_audio_segments"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE evidence_files "
        "ADD COLUMN IF NOT EXISTS transcription_speaker_merges JSONB "
        "NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE evidence_files "
        "DROP COLUMN IF EXISTS transcription_speaker_merges"
    )
