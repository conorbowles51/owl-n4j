import copy
import json
from datetime import date
from unittest.mock import patch
from postgres.models.enums import LedgerStatus, TransactionDirection
from tests.test_financial_ledger_summary import LedgerSummaryTests
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.working_totals import working_ledger_summary, working_totals_from_readings


class WorkingTotalsTests(LedgerSummaryTests):
    def working(self, **scope):
        return working_ledger_summary(self.db, case_id=self.case.id, **scope)

    def test_p3_is_usable_without_changing_verified_totals(self):
        row, _ = self.add(18000)
        row.proof_class = 'p3'
        _, source = self.add(6162, TransactionDirection.debit)
        source.proof_class = 'p3'
        self.db.commit()
        verified = self.read(capture_readings=True)
        original = copy.deepcopy(verified)
        result = working_totals_from_readings(verified)
        self.assertEqual(verified, original)
        self.assertEqual(verified['included_rows'], 0)
        self.assertEqual(result['included_rows'], 2)
        self.assertEqual(result['outside_verified_rows'], 2)
        self.assertEqual(result['currencies'], [dict(currency='GBP', rows=2, credits_minor='18000', debits_minor='6162', net_minor='11838')])
        self.assertEqual(row.proof_class, 'p3')
        self.assertFalse(self.db.new or self.db.dirty)

    def test_excludes_old_held_rejected_and_non_admitted_sources(self):
        for status in (LedgerStatus.superseded, LedgerStatus.quarantined, LedgerStatus.rejected):
            self.add(999, status=status)
        _, source = self.add(999)
        source.status = 'superseded'
        row, _ = self.add(6162)
        row.proof_class = 'p3'
        self.db.commit()
        result = self.working()
        self.assertEqual(result['included_rows'], 1)
        self.assertEqual(result['excluded_rows'], 4)
        self.assertEqual(result['currencies'][0]['credits_minor'], '6162')

    def test_exact_currency_separation_and_scope(self):
        row, _ = self.add(9007199254740993)
        row.proof_class = 'p3'
        row.ordering_date = date(2026, 2, 1)
        other, _ = self.add(200)
        other.currency = 'USD'
        self.db.commit()
        self.assertEqual([(g['currency'], g['credits_minor']) for g in self.working()['currencies']], [('GBP', '9007199254740993'), ('USD', '200')])
        self.assertEqual(self.working(start_date=date(2026, 2, 1), end_date=date(2026, 2, 1))['included_rows'], 1)
        self.assertEqual(self.working(account_id=self.other_account.id)['included_rows'], 0)
        self.assertEqual(working_ledger_summary(self.db, case_id=self.other_case.id)['included_rows'], 0)

    def test_no_partial_or_corrupt_working_totals(self):
        row, _ = self.add()
        row.proof_class = 'p3'
        self.db.commit()
        with patch('services.financial.ledger_summary.MAX_SUMMARY_ROWS', 0):
            result = self.working()
        self.assertFalse(result['available'])
        self.assertIsNone(result['outside_verified_rows'])
        self.assertEqual(result['currencies'], [])
        summary = self.read(capture_readings=True)
        for amount in ('-1', '1.1', '9223372036854775808', '001'):
            broken = copy.deepcopy(summary)
            broken['readings'][0]['row']['amount_minor'] = amount
            with self.assertRaises(LedgerSummaryError):
                working_totals_from_readings(broken)

    def test_export_uses_captured_population(self):
        from services.financial.ledger_snapshot import capture_ledger_snapshot, _capture_history, render_ledger_report, LedgerSnapshot
        row, _ = self.add(6162)
        row.proof_class = 'p3'
        self.db.commit()
        document = json.loads(capture_ledger_snapshot(self.db, case_id=self.case.id).content)
        document = _capture_history(self.db, document, case_id=self.case.id)
        self.assertEqual(document['working_totals'], self.working())
        self.assertEqual(document['ledger']['included_rows'], 0)
        report = render_ledger_report(LedgerSnapshot(json.dumps(document), 'test', 0))
        self.assertIn('61.62 GBP', report)
        self.assertLess(report.index('<h2>Working totals'), report.index('<h2>Captured readings'))
