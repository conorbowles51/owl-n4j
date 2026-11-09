"""A statement period whose rows add up to its printed balances counts as verified (Neil, 9 Nov 2026).

Before this rule every statement reading stayed p3 (held for a person) even when it balanced, so verified totals
were zero on every real case (BNB2: 28,070 of 28,076 rows sat in periods that add up to printed balances).
"""
from __future__ import annotations

import unittest
import uuid

from sqlalchemy import select

from postgres.models.enums import LedgerStatus, ProofClass, QuarantineReason, TransactionDirection
from postgres.models.financial import AdjudicationEvent, FinancialSourceDocument, FinancialTransaction
from services.financial.periods import BalanceObservation
from tests.test_financial_reconcile_case import (
    GBP, STAMP, TABLES, ReconcileCaseTestCase, printed, reconcile_case,
)
import tests.test_financial_reconcile_case as base

if AdjudicationEvent.__table__ not in base.TABLES:
    base.TABLES.append(AdjudicationEvent.__table__)


class BalancedStatementTests(ReconcileCaseTestCase):
    def setUp(self):
        super().setUp()
        self.document.document_type = "statement_review"
        self.document.proof_class = ProofClass.p3.value
        self.document.metadata_ = {"source_shape": "selected_document_rows"}
        self.db.commit()

    def add(self, period, amount, direction=TransactionDirection.credit):
        row = self.add_row(period, amount=amount, direction=direction)
        row.proof_class = ProofClass.p3.value
        self.db.commit()
        return row

    def classes(self):
        self.db.expire_all()
        document = self.db.get(FinancialSourceDocument, self.document.id)
        rows = {r.proof_class for r in self.db.scalars(select(FinancialTransaction)
                                                       .where(FinancialTransaction.source_document_id == document.id))}
        return document.proof_class, rows

    def test_a_period_that_adds_up_to_printed_balances_counts_as_verified(self):
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add(period, 400_00)
        self.add(period, 120_00, TransactionDirection.debit)
        reconcile_case(self.db, self.case.id, now=STAMP)
        self.assertEqual(self.classes(), ("p2", {"p2"}))
        (event,) = self.db.scalars(select(AdjudicationEvent)).all()
        self.assertIn("adds up to the printed balances, checked 1 Apr 2026", event.reason)

    def test_a_period_that_does_not_add_up_stays_held(self):
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add(period, 400_00)
        reconcile_case(self.db, self.case.id, now=STAMP)
        self.assertEqual(self.classes(), ("p3", {"p3"}))

    def test_a_period_without_printed_balances_stays_held(self):
        period = self.make_period(opening=BalanceObservation.absent(), closing=printed(380_00))
        self.add(period, 380_00)
        reconcile_case(self.db, self.case.id, now=STAMP)
        self.assertEqual(self.classes(), ("p3", {"p3"}))

    def test_a_correction_that_breaks_the_balance_takes_the_period_back_out(self):
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add(period, 400_00)
        debit = self.add(period, 120_00, TransactionDirection.debit)
        reconcile_case(self.db, self.case.id, now=STAMP)
        self.assertEqual(self.classes(), ("p2", {"p2"}))
        debit = self.db.get(FinancialTransaction, debit.id)
        debit.ledger_status = LedgerStatus.quarantined.value
        debit.quarantine_reason = QuarantineReason.unreadable_row.value
        self.db.commit()
        reconcile_case(self.db, self.case.id, now=STAMP)
        self.assertEqual(self.classes(), ("p3", {"p3"}))
        reasons = [e.reason for e in self.db.scalars(select(AdjudicationEvent))]
        self.assertTrue(any("does not add up to the printed balances" in r for r in reasons))

    def test_a_stored_correction_reservation_keeps_holding_it(self):
        self.document.metadata_ = {"source_shape": "selected_document_rows",
                                   "admissibility_reservations": ["Corrected ledger reading: printed running-balance chain requires revalidation."]}
        self.db.commit()
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add(period, 400_00)
        self.add(period, 120_00, TransactionDirection.debit)
        reconcile_case(self.db, self.case.id, now=STAMP)
        self.assertEqual(self.classes(), ("p3", {"p3"}))

    def test_a_native_document_is_not_regraded_here(self):
        self.document.metadata_ = {}
        self.db.commit()
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add(period, 400_00)
        self.add(period, 120_00, TransactionDirection.debit)
        reconcile_case(self.db, self.case.id, now=STAMP)
        self.assertEqual(self.classes(), ("p3", {"p3"}))


if __name__ == "__main__":
    unittest.main()
