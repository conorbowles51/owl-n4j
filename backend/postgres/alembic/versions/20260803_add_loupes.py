"""add loupes, members, links and revisions

Revision ID: 20260803_loupes
Revises: 20260725_speaker_merges
"""

from typing import Union

from alembic import op


revision: str = "20260803_loupes"
down_revision: Union[str, None] = "20260725_speaker_merges"
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loupes (
            id              UUID PRIMARY KEY,
            case_id         UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            owner_user_id   UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            title           VARCHAR(255) NOT NULL,
            description     TEXT NULL,
            significance    TEXT NULL,
            kind            VARCHAR(32) NOT NULL DEFAULT 'finding',
            confidence      DOUBLE PRECISION NULL,
            visibility      VARCHAR(32) NOT NULL DEFAULT 'case',
            filter_snapshot JSONB NOT NULL DEFAULT '{}',
            deleted_at      TIMESTAMPTZ NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_loupes_case_id ON loupes (case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_loupes_owner_user_id ON loupes (owner_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_loupes_case_updated ON loupes (case_id, updated_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_loupes_case_active ON loupes (case_id, deleted_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_loupes_deleted_at ON loupes (deleted_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loupe_members (
            id               UUID PRIMARY KEY,
            loupe_id         UUID NOT NULL REFERENCES loupes(id) ON DELETE CASCADE,
            member_type      VARCHAR(32) NOT NULL,
            member_ref       VARCHAR(512) NOT NULL,
            position         INTEGER NOT NULL DEFAULT 0,
            note             TEXT NULL,
            context          JSONB NOT NULL DEFAULT '{}',
            added_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            addition_source  VARCHAR(32) NOT NULL DEFAULT 'manual',
            accepted_at      TIMESTAMPTZ NULL,
            removed_at       TIMESTAMPTZ NULL,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_loupe_members_ref UNIQUE (loupe_id, member_type, member_ref),
            CONSTRAINT ck_loupe_members_type CHECK (member_type IN (
                'entity','event','claim','document','passage',
                'transaction','call','location','loupe'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_loupe_members_loupe_id ON loupe_members (loupe_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_loupe_members_loupe_active "
        "ON loupe_members (loupe_id, removed_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_loupe_members_ref "
        "ON loupe_members (member_type, member_ref)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loupe_links (
            id                 UUID PRIMARY KEY,
            from_loupe_id      UUID NOT NULL REFERENCES loupes(id) ON DELETE CASCADE,
            to_loupe_id        UUID NOT NULL REFERENCES loupes(id) ON DELETE CASCADE,
            relation           VARCHAR(32) NOT NULL,
            rationale          TEXT NULL,
            created_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            removed_at         TIMESTAMPTZ NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_loupe_links_edge UNIQUE (from_loupe_id, to_loupe_id, relation),
            CONSTRAINT ck_loupe_links_no_self CHECK (from_loupe_id <> to_loupe_id),
            CONSTRAINT ck_loupe_links_relation CHECK (relation IN (
                'supports','contradicts','refines','precedes','duplicates','depends_on'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_loupe_links_from ON loupe_links (from_loupe_id, removed_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_loupe_links_to ON loupe_links (to_loupe_id, removed_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loupe_revisions (
            id            UUID PRIMARY KEY,
            loupe_id      UUID NOT NULL REFERENCES loupes(id) ON DELETE CASCADE,
            action        VARCHAR(48) NOT NULL,
            actor_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            detail        JSONB NOT NULL DEFAULT '{}',
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_loupe_revisions_loupe_id ON loupe_revisions (loupe_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_loupe_revisions_loupe_created "
        "ON loupe_revisions (loupe_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS loupe_revisions")
    op.execute("DROP TABLE IF EXISTS loupe_links")
    op.execute("DROP TABLE IF EXISTS loupe_members")
    op.execute("DROP TABLE IF EXISTS loupes")
