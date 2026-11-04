"""A cell tower without a country code takes the phone's SIM country code (cb-coloc-rest D; 04 section 6.2).

``pol_unplaced_tower.mcc_inferred``: the listed key's MCC came from the SIM, not the tower record. Two new reasons for
a tower that stays unresolved: the SIM data states no MCC, or more than one. Projection rows only (rebuilt by the
places stage); downgrade removes the column and the reasons (rows with them are deleted first, as the places stage
rebuilds them).
"""
from alembic import op

revision = "20261104_pol_mcc_inferred"
down_revision = "20261104_phone_views"
branch_labels = None
depends_on = None

REASONS_OLD = "'no_reference_dataset','tower_not_in_reference_data','key_incomplete','no_time'"
REASONS_NEW = REASONS_OLD + ",'mcc_unknown_no_sim','mcc_unknown_several_sims'"


def _constraint():
    return ("DO $$ DECLARE n text; BEGIN SELECT conname INTO n FROM pg_constraint WHERE conrelid = "
            "'pol_unplaced_tower'::regclass AND contype = 'c' AND pg_get_constraintdef(oid) LIKE '%reason%'; "
            "IF n IS NOT NULL THEN EXECUTE 'ALTER TABLE pol_unplaced_tower DROP CONSTRAINT ' || quote_ident(n); "
            "END IF; END $$")


def upgrade():
    op.execute("ALTER TABLE pol_unplaced_tower ADD COLUMN mcc_inferred boolean NOT NULL DEFAULT false")
    op.execute(_constraint())
    op.execute("ALTER TABLE pol_unplaced_tower ADD CONSTRAINT ck_pol_unplaced_tower_reason CHECK (reason IN (%s))"
               % REASONS_NEW)


def downgrade():
    op.execute("DELETE FROM pol_unplaced_tower WHERE reason IN ('mcc_unknown_no_sim','mcc_unknown_several_sims')")
    op.execute(_constraint())
    op.execute("ALTER TABLE pol_unplaced_tower ADD CONSTRAINT ck_pol_unplaced_tower_reason CHECK (reason IN (%s))"
               % REASONS_OLD)
    op.execute("ALTER TABLE pol_unplaced_tower DROP COLUMN mcc_inferred")
