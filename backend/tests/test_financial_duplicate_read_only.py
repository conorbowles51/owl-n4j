"""A duplicate preview must not perform or rewrite a reconciliation."""

from sqlalchemy import event, select

from postgres.models.financial import FinancialStatementPeriod
from services.financial.duplicates import find_groups, nominate_primary
from services.financial.reconcile import reconcile_period
from tests.test_financial_duplicates import DuplicateTestCase, printed


class DuplicateReadOnlyTests(DuplicateTestCase):
    def test_preview_preserves_reconciliation_even_if_caller_commits(self):
        first = self.make_copy()
        self.make_copy()
        periods = list(self.db.scalars(select(FinancialStatementPeriod)))
        # Preserve both an existing result and an as-yet unattempted period.
        reconcile_period(self.db, periods[0])
        self.db.commit()
        columns = tuple(FinancialStatementPeriod.__table__.columns)

        def snapshot():
            return list(self.db.execute(select(*columns).order_by(
                FinancialStatementPeriod.id
            )))

        before = snapshot()
        writes = []

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().split()[0].upper() in {
                "UPDATE", "INSERT", "DELETE"
            }:
                writes.append(statement)

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            groups = find_groups(self.db, self.case.id)
            self.assertEqual(len(groups), 1)
            self.assertIn(first.id, [m.document_id for m in groups[0].members])
            self.db.commit()
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(snapshot(), before)
        self.assertEqual(writes, [])

    def test_nomination_uses_current_rows_without_overwriting_old_result(self):
        good = self.make_copy(rows=((400_00, "aa"),), closing=printed(500_00))
        bad = self.make_copy(rows=((400_00, "aa"),), closing=printed(500_00))
        periods = list(self.db.scalars(select(FinancialStatementPeriod)))
        for period in periods:
            reconcile_period(self.db, period)
        self.db.commit()
        bad_period = next(p for p in periods if p.source_document_id == bad.id)
        # The persisted result now describes the previous population.
        self.add_row(bad_period, bad, amount=100_00)
        prior_attempt = bad_period.reconciled_at

        self.assertEqual(nominate_primary(self.db, [bad, good]).id, good.id)
        self.db.commit()
        self.db.refresh(bad_period)
        self.assertEqual(bad_period.reconciliation_status, "balanced")
        self.assertEqual(bad_period.transaction_count, 1)
        self.assertEqual(bad_period.reconciled_at, prior_attempt)
