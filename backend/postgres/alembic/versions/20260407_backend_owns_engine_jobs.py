"""consolidate evidence-engine jobs schema under backend alembic

Revision ID: 20260407_jobs_schema_merge
Revises: 20260324_add_entity_counts, 20260407_processing_profiles
Create Date: 2026-04-07 18:10:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260407_jobs_schema_merge"
down_revision: Union[str, tuple[str, str], None] = (
    "20260324_add_entity_counts",
    "20260407_processing_profiles",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'jobstatus') THEN
                CREATE TYPE jobstatus AS ENUM (
                    'pending',
                    'extracting_text',
                    'chunking',
                    'extracting_entities',
                    'resolving_entities',
                    'writing_graph',
                    'completed',
                    'failed'
                );
            END IF;
        END
        $$;
        """
    )
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'resolving_relationships'")
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'generating_summaries'")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id UUID PRIMARY KEY,
            case_id VARCHAR(255) NOT NULL,
            batch_id UUID NULL,
            file_name VARCHAR(500) NOT NULL,
            file_path VARCHAR(1000) NOT NULL,
            status jobstatus NOT NULL DEFAULT 'pending',
            progress DOUBLE PRECISION NOT NULL DEFAULT 0,
            error_message TEXT NULL,
            entity_count INTEGER NOT NULL DEFAULT 0,
            relationship_count INTEGER NOT NULL DEFAULT 0,
            llm_profile TEXT NULL,
            file_size BIGINT NOT NULL DEFAULT 0,
            mime_type VARCHAR(100) NULL,
            sha256 VARCHAR(64) NULL,
            folder_context TEXT NULL,
            sibling_files JSONB NULL,
            document_summary TEXT NULL,
            effective_context TEXT NULL,
            effective_special_entity_types JSONB NULL,
            source_folder_id VARCHAR(36) NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        );
        """
    )

    for ddl in (
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS batch_id UUID NULL",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS file_size BIGINT NOT NULL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS mime_type VARCHAR(100) NULL",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS sha256 VARCHAR(64) NULL",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS folder_context TEXT NULL",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS sibling_files JSONB NULL",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS document_summary TEXT NULL",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS effective_context TEXT NULL",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS effective_special_entity_types JSONB NULL",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_folder_id VARCHAR(36) NULL",
    ):
        op.execute(ddl)

    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_case_id ON jobs (case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jobs_batch_id ON jobs (batch_id)")


def downgrade() -> None:
    # Backend now owns the shared jobs schema. This migration is intentionally
    # non-destructive so a downgrade does not drop job data from the shared DB.
    pass
