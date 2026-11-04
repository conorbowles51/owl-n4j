"""Printable transaction numbers (lx-feedback-data D, BACKLOG FEAT-006).

People print the ledger, take it to a client meeting and need to say "number 412" and find the same payment back in
Loupe. ``financial_transaction_numbers`` gives every ledger row a short number per case; a trigger numbers each new
row whatever path inserted it. A corrected version (``provenance.correction.previous_transaction_id``) keeps the
number of the row it replaces. Numbers are never reused: the per-case counter only goes up.

Existing rows are numbered once here: each original payment (a row no other row replaced into) in date order
(ordering date, then when it was recorded, then its position in the statement), and every later version of it takes
the same number. The ledger rows themselves are not updated, so no audit event is written for them.
On live 2026-11-04 08:20 UTC: 42,470 rows over 7 cases with payments (counted in
financial_transactions; the migration numbers whatever is present).
"""
from alembic import op

revision = "20261104_transaction_numbers"
down_revision = "20261104_pol_mcc_inferred"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS financial_transaction_numbers (
            transaction_id uuid PRIMARY KEY REFERENCES financial_transactions(id) ON DELETE CASCADE,
            case_id uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            number integer NOT NULL,
            assigned_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_financial_transaction_numbers_positive CHECK (number >= 1)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_financial_transaction_numbers_case_number "
               "ON financial_transaction_numbers (case_id, number)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS financial_transaction_number_counters (
            case_id uuid PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
            last_number integer NOT NULL
        )
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION assign_financial_transaction_number() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
          previous_id text := NEW.provenance -> 'correction' ->> 'previous_transaction_id';
          assigned integer := NULL;
        BEGIN
          IF previous_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
            SELECT number INTO assigned FROM financial_transaction_numbers
              WHERE transaction_id = previous_id::uuid AND case_id = NEW.case_id;
          END IF;
          IF assigned IS NULL THEN
            INSERT INTO financial_transaction_number_counters AS c (case_id, last_number) VALUES (NEW.case_id, 1)
              ON CONFLICT (case_id) DO UPDATE SET last_number = c.last_number + 1
              RETURNING last_number INTO assigned;
          END IF;
          INSERT INTO financial_transaction_numbers (transaction_id, case_id, number)
            VALUES (NEW.id, NEW.case_id, assigned) ON CONFLICT (transaction_id) DO NOTHING;
          RETURN NULL;
        END $$
    """)
    op.execute("DROP TRIGGER IF EXISTS number_financial_transaction ON financial_transactions")
    # Backfill before the trigger exists, inside the migration's transaction: nothing else numbers rows meanwhile.
    op.execute("""
        WITH RECURSIVE edges AS (
            SELECT p.id AS parent, p.superseded_by_id AS child FROM financial_transactions p
             WHERE p.superseded_by_id IS NOT NULL
            UNION
            SELECT p.id, c.id FROM financial_transactions c
              JOIN financial_transactions p
                ON p.id::text = c.provenance -> 'correction' ->> 'previous_transaction_id' AND p.case_id = c.case_id
        ), roots AS (
            SELECT t.id, t.case_id, row_number() OVER (PARTITION BY t.case_id
                     ORDER BY t.ordering_date, t.created_at, t.row_index, t.id) AS number
              FROM financial_transactions t
             WHERE NOT EXISTS (SELECT 1 FROM edges e WHERE e.child = t.id)
        ), chain(id, number, depth) AS (
            SELECT id, number, 0 FROM roots
            UNION ALL
            SELECT e.child, ch.number, ch.depth + 1 FROM chain ch JOIN edges e ON e.parent = ch.id WHERE ch.depth < 200
        )
        INSERT INTO financial_transaction_numbers (transaction_id, case_id, number)
        SELECT ch.id, t.case_id, min(ch.number) FROM chain ch JOIN financial_transactions t ON t.id = ch.id
         GROUP BY ch.id, t.case_id
        ON CONFLICT (transaction_id) DO NOTHING
    """)
    # Rows only reachable through a cycle (none expected) still get a number, after the case's last.
    op.execute("""
        INSERT INTO financial_transaction_numbers (transaction_id, case_id, number)
        SELECT t.id, t.case_id, coalesce(m.top, 0) + row_number() OVER (PARTITION BY t.case_id ORDER BY t.ordering_date, t.row_index, t.id)
          FROM financial_transactions t
          LEFT JOIN (SELECT case_id, max(number) AS top FROM financial_transaction_numbers GROUP BY case_id) m
            ON m.case_id = t.case_id
         WHERE NOT EXISTS (SELECT 1 FROM financial_transaction_numbers n WHERE n.transaction_id = t.id)
    """)
    op.execute("""
        INSERT INTO financial_transaction_number_counters (case_id, last_number)
        SELECT case_id, max(number) FROM financial_transaction_numbers GROUP BY case_id
        ON CONFLICT (case_id) DO UPDATE SET last_number = GREATEST(financial_transaction_number_counters.last_number,
                                                                   EXCLUDED.last_number)
    """)
    op.execute("CREATE TRIGGER number_financial_transaction AFTER INSERT ON financial_transactions "
               "FOR EACH ROW EXECUTE FUNCTION assign_financial_transaction_number()")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS number_financial_transaction ON financial_transactions")
    op.execute("DROP FUNCTION IF EXISTS assign_financial_transaction_number()")
    op.execute("DROP TABLE IF EXISTS financial_transaction_number_counters")
    op.execute("DROP TABLE IF EXISTS financial_transaction_numbers")
