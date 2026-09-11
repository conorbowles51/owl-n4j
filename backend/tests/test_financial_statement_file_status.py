from services.financial.statement_file_status import statement_file_status
from tests.test_financial_duplicates import DuplicateTestCase


class StatementFileStatusTests(DuplicateTestCase):
    def test_saved_file_status_counts_current_payments_and_preserves_periods(self):
        document = self.make_document()
        period = self.make_period(document)
        original = self.add_row(period, document, amount=100)
        replacement = self.add_row(period, document, amount=200)
        original.ledger_status = 'superseded'
        original.superseded_by_id = replacement.id
        self.db.commit()
        result = statement_file_status(self.db, case_id=self.case.id)
        item = next(f for f in result['files'] if f['evidence_file_id'] == str(document.evidence_file_id))
        self.assertEqual(item['current_transactions'], 1)
        self.assertEqual(item['periods'][0]['account_id'], str(period.account_id))
        self.assertEqual(item['periods'][0]['start'], period.period_start.isoformat())
        document.status = 'superseded'
        self.db.commit()
        result = statement_file_status(self.db, case_id=self.case.id)
        self.assertEqual(result['files'][0]['current_transactions'], 0)
        self.assertEqual(result['files'][0]['periods'][0]['source_status'], 'superseded')
        self.assertEqual(statement_file_status(self.db, case_id=self.other_case.id)['files'], [])

    def test_saved_file_status_omits_a_file_with_inconsistent_case_ownership(self):
        from postgres.models.evidence import EvidenceFile
        document = self.make_document()
        self.make_period(document)
        self.db.get(EvidenceFile, document.evidence_file_id).case_id = self.other_case.id
        self.db.commit()
        self.assertEqual(statement_file_status(self.db, case_id=self.case.id)['files'], [])
