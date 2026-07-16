"""repair workspace note uniqueness for migrated installs

Revision ID: 20260716_workspace_note_uniqueness
Revises: 20260705_timeline_views
Create Date: 2026-07-16 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260716_workspace_note_uniqueness"
down_revision: Union[str, None] = "20260705_timeline_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                case_id,
                note_id,
                data,
                created_at,
                updated_at,
                row_number() OVER (
                    PARTITION BY case_id, note_id
                    ORDER BY updated_at DESC, created_at DESC, id DESC
                ) AS row_number
            FROM workspace_notes
        ),
        duplicate_payloads AS (
            SELECT
                keeper.id AS keeper_id,
                jsonb_agg(
                    jsonb_build_object(
                        'id', duplicate.id::text,
                        'data', duplicate.data,
                        'created_at', duplicate.created_at,
                        'updated_at', duplicate.updated_at
                    )
                    ORDER BY duplicate.updated_at, duplicate.created_at, duplicate.id
                ) AS records
            FROM ranked keeper
            JOIN ranked duplicate
                ON duplicate.case_id = keeper.case_id
                AND duplicate.note_id = keeper.note_id
                AND duplicate.row_number > 1
            WHERE keeper.row_number = 1
            GROUP BY keeper.id
        )
        UPDATE workspace_notes AS note
        SET data = jsonb_set(
            COALESCE(note.data, '{}'::jsonb),
            '{migration_duplicate_records}',
            COALESCE(note.data->'migration_duplicate_records', '[]'::jsonb)
                || duplicate_payloads.records,
            true
        )
        FROM duplicate_payloads
        WHERE note.id = duplicate_payloads.keeper_id
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY case_id, note_id
                    ORDER BY updated_at DESC, created_at DESC, id DESC
                ) AS row_number
            FROM workspace_notes
        )
        DELETE FROM workspace_notes AS note
        USING ranked
        WHERE note.id = ranked.id
            AND ranked.row_number > 1
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_workspace_notes_case_note'
                    AND conrelid = 'workspace_notes'::regclass
            ) THEN
                ALTER TABLE workspace_notes
                    ADD CONSTRAINT uq_workspace_notes_case_note
                    UNIQUE (case_id, note_id);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE workspace_notes
            DROP CONSTRAINT IF EXISTS uq_workspace_notes_case_note
        """
    )
