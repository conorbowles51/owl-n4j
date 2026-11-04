"""Perceptual hashes of phone pictures (05 section 11.3 step 3; cb-gated-spread D).

``phone_file_perceptual_hashes``: one row per picture file of a case with two or more phones, holding a 64-bit
pHash and dHash computed on this server from the file's bytes (stored as signed 64-bit integers), or the reason the
picture could not be hashed. A projection: rebuilt from the files, never edited by a person. New table; no existing
row changes. Downgrade drops it.
"""
from alembic import op

revision = "20261104_phone_perceptual_hash"
down_revision = "20261104_pol_mcc_inferred"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS phone_file_perceptual_hashes (
            file_uid       uuid PRIMARY KEY,
            case_id        uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            extraction_id  uuid NOT NULL REFERENCES phone_extractions(id) ON DELETE CASCADE,
            algorithm      varchar(32) NOT NULL,
            state          varchar(8) NOT NULL CHECK (state IN ('done', 'failed')),
            phash          bigint,
            dhash          bigint,
            reason         varchar(32),
            cpu_ms         integer,
            computed_at    timestamptz NOT NULL DEFAULT now(),
            CHECK (state = 'failed' OR (phash IS NOT NULL AND dhash IS NOT NULL))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_phone_file_perceptual_hashes_case ON phone_file_perceptual_hashes "
               "(case_id, state)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS phone_file_perceptual_hashes")
