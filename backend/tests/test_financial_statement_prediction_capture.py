import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('statement_capture', Path(__file__).resolve().parents[2] / 'scripts/capture_financial_statement_predictions.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PredictionCaptureTests(unittest.TestCase):
    def proposal(self):
        from services.financial.statement_import_proposal import propose_table
        from tests.test_financial_statement_import_proposal import statement
        return {**propose_table(statement(), 'EUR'), 'metadata': {'account_number': 'TEST123'}, 'currency': 'EUR'}

    def test_original_rows_remain_exact_unadmitted_and_source_positioned(self):
        proposal = self.proposal()
        before = copy.deepcopy(proposal)
        result = module.document_predictions([proposal], 'a' * 64)
        self.assertNotIn('truth', result)
        self.assertEqual(len(result['predictions']), 12)
        self.assertTrue(all(not row['admitted'] for row in result['predictions']))
        first = result['predictions'][0]
        self.assertEqual(first['source_id'], 'page-0001/table-000/row-0002')
        self.assertEqual(first['fields'], {'date': '2023-03-18', 'amount_minor': '12500000', 'direction': 'credit', 'currency': 'EUR', 'account': 'TEST123'})
        self.assertEqual(proposal, before)

    def test_damaged_field_stays_missing_and_receipt_produces_no_statement_rows(self):
        proposal = self.proposal()
        proposal['rows'][2]['fields'].pop('date')
        output = module.document_predictions([proposal, {'document_review': {'kind': 'deposit_receipt'}}], 'a' * 64)
        self.assertNotIn('date', output['predictions'][0]['fields'])
        self.assertEqual(len(output['predictions']), 12)
        self.assertEqual(module.document_predictions([{'document_review': { 'kind': 'wire' }}], 'b' * 64)['predictions'], [])

    def test_conflicting_same_row_account_is_not_silently_overwritten(self):
        proposal = self.proposal(); other = copy.deepcopy(proposal)
        other['metadata']['account_number'] = 'OTHER'
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            module.document_predictions([proposal, other], 'a' * 64)

    def test_actual_prepared_import_reading_reproduces_without_importing(self):
        from tests.test_financial_statement_import import StatementImportTests
        from postgres.models.financial import FinancialTransaction
        from sqlalchemy import select, func
        fixture = StatementImportTests(); fixture.setUp()
        try:
            inventory = {'corpus_id': 'synthetic-capture', 'corpus_version': '1', 'sources': [{
                'case_id': str(fixture.case.id), 'evidence_file_id': str(fixture.file.id),
                'source_sha256': fixture.file.sha256, 'currency': 'EUR'}]}
            first, captures = module.capture(fixture.db, inventory)
            inventory['sources'][0]['expected_proposals_sha256'] = captures[0]['proposals_sha256']
            second, again = module.capture(fixture.db, inventory)
            self.assertEqual(first, second); self.assertEqual(captures, again)
            self.assertEqual(len(first['documents'][0]['predictions']), 12)
            self.assertEqual(fixture.db.scalar(select(func.count()).select_from(FinancialTransaction)), 0)
            inventory['sources'][0]['source_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'source digest'):
                module.capture(fixture.db, inventory)
        finally:
            fixture.tearDown()
