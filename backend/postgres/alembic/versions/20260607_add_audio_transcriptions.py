"""add audio transcription storage

Revision ID: 20260607_audio_transcriptions
Revises: 20260524_agent_cost_link
Create Date: 2026-06-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260607_audio_transcriptions"
down_revision: Union[str, None] = "20260524_agent_cost_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS transcription TEXT NULL")
    op.execute("ALTER TABLE evidence_files ADD COLUMN IF NOT EXISTS transcription TEXT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE evidence_files DROP COLUMN IF EXISTS transcription")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS transcription")
