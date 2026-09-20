from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from uuid import UUID
from sqlalchemy import select

from tests.test_financial_statement_import import StatementImportTests as Fixture
from services.financial.statement_import import read_statement_import
from services.financial.import_batches import initial_request
from services.financial.legacy_statement_refresh import refresh_legacy_import
from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
from services.financial.pdf_candidates import PdfMappingError
from services.financial.transaction_query import list_transactions
from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod
from services.financial.periods import read_opening, read_closing


class EmptyImportRecoveryTests(TestCase):
    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def test_correct_currency_recovers_payments_preserving_saved_details_balances_and_history(self):
        f = self.f
        with f.SessionLocal() as db:
            wrong = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, currency='USD')
        receipt = f.confirm(initial_request(wrong))
        self.assertEqual(receipt['transaction_count'], 0)
        source_id = UUID(receipt['source_document_id'])
        with f.SessionLocal() as db:
            view = read_statement_details(db, case_id=f.case.id, source_id=source_id)
            update_statement_details(db, case_id=f.case.id, source_id=source_id, actor=f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], holder='Saved investigator name',
                    account_number='0012345', institution='Saved bank',
                    opening=dict(amount_minor='12345', page=1), closing=dict(amount_minor='0', page=1)))
        p = f.preview()
        self.assertTrue(p['current_import']['refresh_available'])
        self.assertEqual(p['current_import']['refresh_transaction_count'], 12)
        args = dict(session_factory=f.SessionLocal, case_id=f.case.id, source_id=source_id,
            expected_revision=p['current_import']['revision'], currency=p['currency'],
            expected_reading_revision=p['revision'], actor=f.actor, resolve_path=Path)
        with self.assertRaisesRegex(PdfMappingError, 'reading changed'):
            refresh_legacy_import(**{**args, 'expected_reading_revision': '0'*64})
        saved = refresh_legacy_import(**args)
        self.assertEqual((saved['transaction_count'], saved['incomplete_count']), (12, 0))
        self.assertFalse(refresh_legacy_import(**args)['created'])
        with f.SessionLocal() as db:
            rows = list_transactions(db, f.case.id)
            self.assertEqual(len(rows), 12)
            self.assertTrue(all(row.currency == 'EUR' for row in rows))
            source = db.get(FinancialSourceDocument, UUID(saved['source_document_id']))
            self.assertEqual(source.metadata_['statement_import_request']['holder'], 'Saved investigator name')
            self.assertEqual(source.metadata_['statement_import_request']['account_number'], '0012345')
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == source.id))
            self.assertEqual(read_opening(period).amount.minor_units, 12345)
            self.assertEqual(read_closing(period).amount.minor_units, 0)
            self.assertEqual(db.get(FinancialSourceDocument, source_id).status, 'superseded')
            from services.financial.batch_import_history import current_imports
            self.assertEqual(current_imports(db, f.case.id, [source_id])[str(source_id)]['balance_status'], 'difference')

    def test_empty_import_with_changed_draft_has_an_explicit_comparison_and_save_path(self):
        from services.financial.pdf_candidates import _digest
        from postgres.models.evidence import EvidenceFile
        f = self.f
        with f.SessionLocal() as db:
            wrong = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, currency='USD')
        receipt = f.confirm(initial_request(wrong))
        source_id = UUID(receipt['source_document_id'])
        proposal = f.preview()
        old_draft = initial_request(proposal)
        old_draft['expected_revision'] = '0'*64
        next(r for r in old_draft['rows'] if not r['excluded'])['amount_minor'] = '999999'
        token = _digest(old_draft)
        with f.SessionLocal() as db:
            file = db.get(EvidenceFile, f.file.id)
            file.metadata_ = {**(file.metadata_ or {}), 'financial_review_progress': {proposal.get('statement_id') or '':
                dict(request=old_draft, review_revision=token, saved_at='2026-09-20T12:00:00Z', saved_by=dict(name='Reviewer'))}}
            db.commit()
        proposal = f.preview()
        self.assertFalse(proposal['current_import']['refresh_available'])
        self.assertTrue(proposal['current_import']['refresh_review_required'])
        args = dict(session_factory=f.SessionLocal, case_id=f.case.id, source_id=source_id,
            expected_revision=proposal['current_import']['revision'], currency=proposal['currency'],
            expected_reading_revision=proposal['revision'], actor=f.actor, resolve_path=Path)
        with self.assertRaises(PdfMappingError): refresh_legacy_import(**args)
        with self.assertRaisesRegex(PdfMappingError, 'draft changed'):
            refresh_legacy_import(**args, compared_review_revision='f'*64)
        result = refresh_legacy_import(**args, compared_review_revision=token)
        self.assertEqual(result['transaction_count'], 12)
        self.assertFalse(refresh_legacy_import(**args, compared_review_revision=token)['created'])
        with f.SessionLocal() as db:
            history = db.get(EvidenceFile, f.file.id).metadata_['financial_review_history']
            self.assertEqual(history[-1]['request'], old_draft)
            self.assertEqual(len(list_transactions(db, f.case.id)), 12)

    def test_metadata_change_with_identical_saved_rows_does_not_require_rechecking_payments(self):
        from services.financial.review_upgrade import attach_upgrade
        p = self.f.preview()
        request = initial_request(p)
        request.update(expected_revision='0'*64, holder='Saved investigator name')
        p['saved_review'] = dict(request=request, review_revision='saved-token')
        attach_upgrade(p, {})
        self.assertEqual(p['saved_review']['request']['expected_revision'], p['revision'])
        self.assertEqual(p['saved_review']['request']['holder'], 'Saved investigator name')
        self.assertEqual(p['saved_review']['review_revision'], 'saved-token')
        changed = deepcopy(p)
        changed['saved_review']['request']['expected_revision'] = '0'*64
        next(row for row in changed['saved_review']['request']['rows'] if not row['excluded'])['amount_minor'] = '999999'
        attach_upgrade(changed, {})
        self.assertEqual(changed['saved_review']['request']['expected_revision'], '0'*64)
