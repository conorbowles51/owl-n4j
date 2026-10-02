"""At most one active saved copy of each statement.

Two workers confirming the same accepted statement are kept apart only by the
Case row lock taken in the statement writer.  This adds the database's own
guarantee behind that lock: among saved statement reviews that still count
(admitted and not removed from the import), one per case, evidence file and
statement within the file.

The constraint is checked at commit, not per statement.  A reread inserts its
replacement before superseding the copy it replaces, and recovery inserts its
sections before superseding their parent; both are legitimate and both would
be refused by an immediate check.

The upgrade refuses to run, listing every offending group, if the data already
holds two active copies of one statement.  Those need an investigator's
decision; choosing one here would be a silent exclusion.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261002_one_active_statement'
down_revision = '20260924_statement_recovery'
branch_labels = None
depends_on = None

CONSTRAINT = 'ex_financial_source_documents_one_active_statement'
STATEMENT_KEY = "(coalesce(metadata ->> 'statement_import_statement_id', ''))"
ACTIVE = ("document_type = 'statement_review' AND status = 'admitted' "
          "AND NOT (metadata ? 'financial_import_removal')")
CONSTRAINT_DDL = (
    f"EXCLUDE USING btree (case_id WITH =, evidence_file_id WITH =, {STATEMENT_KEY} WITH =) "
    f"WHERE ({ACTIVE}) DEFERRABLE INITIALLY DEFERRED")
OFFENDERS = (
    f"SELECT case_id::text, evidence_file_id::text, {STATEMENT_KEY} AS statement_id, "
    f"string_agg(id::text, ', ' ORDER BY id) AS documents "
    f"FROM financial_source_documents WHERE {ACTIVE} "
    f"GROUP BY case_id, evidence_file_id, {STATEMENT_KEY} HAVING count(*) > 1 "
    f"ORDER BY 1, 2, 3")


def offender_message(rows):
    lines = [f'case {case_id}, evidence file {file_id}, statement {statement_id or "(whole file)"}: documents {documents}'
             for case_id, file_id, statement_id, documents in rows]
    return ('Refusing to add ' + CONSTRAINT + ': these statements already have more than one active saved copy. '
            'Resolve each group (keep one copy, supersede or remove the others) and rerun the upgrade.\n'
            + '\n'.join(lines))


def upgrade():
    bind = op.get_bind()
    # Hold the table so the check and the constraint see the same rows.
    bind.execute(sa.text('LOCK TABLE financial_source_documents IN ACCESS EXCLUSIVE MODE'))
    rows = bind.execute(sa.text(OFFENDERS)).all()
    if rows:
        raise RuntimeError(offender_message(rows))
    op.execute(f'ALTER TABLE financial_source_documents ADD CONSTRAINT {CONSTRAINT} {CONSTRAINT_DDL}')


def downgrade():
    op.execute(f'ALTER TABLE financial_source_documents DROP CONSTRAINT IF EXISTS {CONSTRAINT}')
