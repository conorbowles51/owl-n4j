"""Replacement readings must not undo a reviewed statement denomination."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from uuid import UUID, uuid4

from tests import test_financial_statement_import as fixtures
from tests.financial_reconciled_fixture import install_reconciled_source
from services.financial.import_batches import initial_request
from services.financial.legacy_statement_refresh import refresh_legacy_import
from services.financial.statement_import import read_statement_import
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_details import (
    read_statement_details, update_statement_details, StatementDetailsRequest,
)
from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from sqlalchemy import select


class ReplacementCurrencyTests(TestCase):
    def setUp(self):
        self.f = fixtures.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        f = self.f
        install_reconciled_source(f)
        payments = deepcopy(f.db.get(EvidenceTableGeometry, (f.file.id, 1)).payload)
        install_reconciled_source(f, quiet=True)
        self.source_id = UUID(f.confirm(initial_request(f.preview()))['source_document_id'])
        # A later reading recovers the payments missed by the older reader.
        f.db.get(EvidenceTableGeometry, (f.file.id, 1)).payload = payments
        f.db.commit()
        reading = f.preview()
        controls = {row['fields']['description'].lower(): row['fields']['balance']
            for row in reading['rows'] if row['kind'] == 'balance'}
        # The same integer represents materially different printed amounts in
        # JPY and EUR. Reusing it under EUR must not create false reconciliation.
        with f.SessionLocal() as db:
            view = read_statement_details(db, case_id=f.case.id, source_id=self.source_id)
            update_statement_details(db, case_id=f.case.id, source_id=self.source_id, actor=f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], **view['details'], currency='JPY',
                    opening={'amount_minor': controls['opening balance'], 'page': 1},
                    closing={'amount_minor': controls['closing balance'], 'page': 1}))
            self.before = deepcopy(db.get(FinancialSourceDocument, self.source_id).metadata_)

    def tearDown(self):
        self.f.tearDown()

    def test_preview_does_not_reinterpret_reviewed_yen_controls_as_euro(self):
        proposal = self.f.preview()
        self.assertEqual(proposal['currency'], 'EUR')
        self.assertEqual(proposal['current_import']['currency'], 'JPY')
        self.assertFalse(proposal['current_import']['refresh_available'])
        self.assertIsNone(proposal['current_import'].get('refresh_admission'))
        self.assertEqual(proposal['current_import']['refresh_currency_conflict']['saved_currency'], 'JPY')
        self.assertEqual(proposal['current_import']['refresh_currency_conflict']['reading_currency'], 'EUR')
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(FinancialSourceDocument, self.source_id).metadata_, self.before)

    def test_replacement_does_not_overwrite_reviewed_currency(self):
        proposal = self.f.preview()
        with self.assertRaisesRegex(PdfMappingError, '[Cc]urrency'):
            refresh_legacy_import(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
                source_id=self.source_id, expected_revision=proposal['current_import']['revision'],
                currency=proposal['currency'], expected_reading_revision=proposal['revision'],
                actor=self.f.actor, resolve_path=Path)
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, self.source_id)
            self.assertEqual(source.metadata_, self.before)
            self.assertEqual(source.status, 'admitted')
            self.assertIsNone(source.superseded_by_id)

    def test_new_reading_version_explains_the_same_saved_currency_guard(self):
        from services.financial.statement_reprocessing import create_statement_version
        f = self.f
        with f.SessionLocal() as db:
            version = create_statement_version(db, case_id=f.case.id, evidence_file_id=f.file.id,
                request_id=uuid4(), actor=f.actor, resolve_path=Path)
            text = db.get(EvidenceDocumentText, f.file.id)
            geometry = db.get(EvidenceTableGeometry, (f.file.id, 1))
            db.add(EvidenceDocumentText(evidence_file_id=version.id, content=text.content,
                content_sha256=text.content_sha256, character_count=text.character_count,
                engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
            db.add(EvidenceTableGeometry(evidence_file_id=version.id, page_number=1,
                engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
            db.commit()
            proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=version.id, currency='EUR')
            self.assertEqual(proposal['current_import']['evidence_file_id'], str(f.file.id))
            self.assertEqual(proposal['current_import']['refresh_currency_conflict']['saved_currency'], 'JPY')
            self.assertIsNone(proposal['current_import'].get('refresh_admission'))

    def test_direct_replacement_confirmation_cannot_bypass_currency_guard(self):
        proposal = self.f.preview()
        request = initial_request(proposal)
        request.update(replaces_source_document_id=str(self.source_id),
            replacement_revision=proposal['current_import']['revision'],
            details_reason='Compare the recovered synthetic payment reading.')
        with self.assertRaisesRegex(PdfMappingError, 'saved JPY'):
            self.f.confirm(request)
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, self.source_id)
            self.assertEqual(source.metadata_, self.before)
            self.assertIsNone(source.superseded_by_id)

    def test_saved_currency_recheck_preserves_values_and_requires_real_reconciliation(self):
        f = self.f
        with f.SessionLocal() as db:
            # Plain printed numbers can be checked using a corrected currency;
            # this changes parsing precision, never performs an exchange.
            geometry = db.get(EvidenceTableGeometry, (f.file.id, 1))
            payload = deepcopy(geometry.payload)
            for value in payload[0]['table']['values']:
                value['text'] = value['text'].replace('€', '')
            geometry.payload = payload
            db.commit()
            proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, currency='JPY')
            current = proposal['current_import']
            self.assertIsNone(current['refresh_currency_conflict'])
            self.assertTrue(current['refresh_available'])
            self.assertFalse(current['refresh_admission']['can_import'])
            self.assertEqual(current['refresh_admission']['calculation']['currency'], 'JPY')
            self.assertEqual(current['refresh_admission']['calculation']['opening_minor'], '1245000')
            self.assertEqual(db.get(FinancialSourceDocument, self.source_id).metadata_, self.before)
            controls = {row['fields']['description'].lower(): row['fields']['balance']
                for row in proposal['rows'] if row['kind'] == 'balance'}
            view = read_statement_details(db, case_id=f.case.id, source_id=self.source_id)
            update_statement_details(db, case_id=f.case.id, source_id=self.source_id, actor=f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], **view['details'], currency='JPY',
                    opening={'amount_minor': controls['opening balance'], 'page': 1},
                    closing={'amount_minor': controls['closing balance'], 'page': 1}))
            proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, currency='JPY')
            self.assertTrue(proposal['current_import']['refresh_admission']['can_import'])
            self.assertEqual(proposal['current_import']['refresh_admission']['calculation']['difference_minor'], '0')
        saved = refresh_legacy_import(session_factory=f.SessionLocal, case_id=f.case.id,
            source_id=self.source_id, expected_revision=proposal['current_import']['revision'], currency='JPY',
            expected_reading_revision=proposal['revision'], actor=f.actor, resolve_path=Path)
        self.assertEqual(saved['transaction_count'], 12)
        with f.SessionLocal() as db:
            old = db.get(FinancialSourceDocument, self.source_id)
            new = db.get(FinancialSourceDocument, UUID(saved['source_document_id']))
            self.assertEqual(old.status, 'superseded')
            self.assertEqual(new.metadata_['statement_import_request']['currency'], 'JPY')
            self.assertEqual(new.metadata_['statement_import_original']['currency'], 'JPY')

    def test_currency_changed_back_to_original_is_still_an_explicit_choice(self):
        f = self.f
        with f.SessionLocal() as db:
            view = read_statement_details(db, case_id=f.case.id, source_id=self.source_id)
            update_statement_details(db, case_id=f.case.id, source_id=self.source_id, actor=f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], **view['details'], currency='EUR'))
            proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, currency='JPY')
            self.assertEqual(proposal['current_import']['refresh_currency_conflict']['saved_currency'], 'EUR')
            self.assertFalse(proposal['current_import']['refresh_available'])

    def test_recheck_does_not_invent_amounts_from_incompatible_printed_currency(self):
        f = self.f
        with f.SessionLocal() as db:
            proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, currency='JPY')
            assessment = proposal['current_import']['refresh_admission']
            self.assertIsNone(proposal['current_import']['refresh_currency_conflict'])
            self.assertFalse(assessment['can_import'])
            self.assertIn('missing_field:amount', [blocker['code'] for blocker in assessment['blockers']])
            self.assertEqual(db.get(FinancialSourceDocument, self.source_id).metadata_, self.before)


class LegacyCurrencyRepresentationTests(TestCase):
    def test_uncorrected_legacy_currency_rescales_saved_balance_representation_exactly(self):
        f = fixtures.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        f.setUp()
        try:
            install_reconciled_source(f)
            payments = deepcopy(f.db.get(EvidenceTableGeometry, (f.file.id, 1)).payload)
            install_reconciled_source(f, quiet=True)
            source_id = UUID(f.confirm(initial_request(f.preview()))['source_document_id'])
            for value in payments[0]['table']['values']:
                value['text'] = value['text'].replace('€', '')
            f.db.get(EvidenceTableGeometry, (f.file.id, 1)).payload = payments
            f.db.commit()
            with f.SessionLocal() as db:
                view = read_statement_details(db, case_id=f.case.id, source_id=source_id)
                update_statement_details(db, case_id=f.case.id, source_id=source_id, actor=f.actor,
                    request=StatementDetailsRequest(expected_revision=view['revision'], **view['details'], currency='EUR',
                        opening={'amount_minor': '1245000', 'page': 1},
                        closing={'amount_minor': '4745000', 'page': 1}))
                before = deepcopy(db.get(FinancialSourceDocument, source_id).metadata_)
                proposal = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, currency='JPY')
                current = proposal['current_import']
                self.assertIsNone(current['refresh_currency_conflict'])
                self.assertTrue(current['refresh_available'])
                self.assertTrue(current['refresh_admission']['can_import'])
                calculation = current['refresh_admission']['calculation']
                self.assertEqual(calculation['opening_minor'], '12450')
                self.assertEqual(calculation['printed_closing_minor'], '47450')
                self.assertEqual(calculation['difference_minor'], '0')
                self.assertEqual(db.get(FinancialSourceDocument, source_id).metadata_, before)
            saved = refresh_legacy_import(session_factory=f.SessionLocal, case_id=f.case.id,
                source_id=source_id, expected_revision=current['revision'], currency='JPY',
                expected_reading_revision=proposal['revision'], actor=f.actor, resolve_path=Path)
            self.assertEqual(saved['transaction_count'], 12)
        finally:
            f.tearDown()


class PendingAmountCurrencyTests(TestCase):
    def setUp(self):
        self.f = fixtures.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        with self.f.SessionLocal() as db:
            wrong = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id, currency='USD')
        self.receipt = self.f.confirm_legacy(initial_request(wrong))
        self.source_id = UUID(self.receipt['source_document_id'])

    def tearDown(self):
        self.f.tearDown()

    def test_saved_currency_correction_keeps_missing_amounts_pending_on_reopen(self):
        from services.financial.imported_records import imported_records
        f = self.f
        self.assertEqual(self.receipt['transaction_count'], 0)
        with f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, self.source_id)
            original_request = deepcopy(source.metadata_['statement_import_request'])
            original_records = deepcopy(source.metadata_['statement_incomplete_records'])
            self.assertTrue(any(row['fields']['amount_minor'] == '' for row in original_records))
            view = read_statement_details(db, case_id=f.case.id, source_id=self.source_id)
            saved = update_statement_details(db, case_id=f.case.id, source_id=self.source_id, actor=f.actor,
                request=StatementDetailsRequest(expected_revision=view['revision'], **view['details'], currency='JPY'))
            self.assertEqual(saved['currency'], 'JPY')
        with f.SessionLocal() as db:
            reopened = read_statement_details(db, case_id=f.case.id, source_id=self.source_id)
            self.assertEqual(reopened, saved)
            records = imported_records(db, case_id=f.case.id, source_document_id=self.source_id)
            self.assertEqual(records['total'], len(original_records))
            self.assertTrue(all(row['currency'] == 'JPY' for row in records['records']))
            missing = [row for row in records['records'] if row['fields']['amount_minor'] == '']
            self.assertTrue(missing)
            self.assertTrue(all('amount' in row['missing_fields'] for row in missing))
            self.assertEqual(list(db.scalars(select(FinancialTransaction.id))), [])
            source = db.get(FinancialSourceDocument, self.source_id)
            self.assertEqual(source.metadata_['statement_import_request'], original_request)
            for old, current in zip(original_records, source.metadata_['statement_incomplete_records'], strict=True):
                self.assertEqual(current['fields'], old['fields'])
                self.assertFalse(current.get('resolved_transaction_id'))

    def test_nonempty_unreadable_pending_amount_blocks_currency_edit_atomically(self):
        f = self.f
        with f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, self.source_id)
            metadata = deepcopy(source.metadata_)
            record = metadata['statement_incomplete_records'][0]
            record['correction'] = {**record['fields'], 'amount_minor': 'not-a-number'}
            record['correction_currency'] = 'USD'
            source.metadata_ = metadata
            db.commit()
            before = deepcopy(source.metadata_)
            view = read_statement_details(db, case_id=f.case.id, source_id=self.source_id)
            with self.assertRaisesRegex(PdfMappingError, 'pending payment has an unreadable amount'):
                update_statement_details(db, case_id=f.case.id, source_id=self.source_id, actor=f.actor,
                    request=StatementDetailsRequest(expected_revision=view['revision'], **view['details'], currency='JPY'))
        with f.SessionLocal() as db:
            self.assertEqual(read_statement_details(db, case_id=f.case.id, source_id=self.source_id), view)
            self.assertEqual(db.get(FinancialSourceDocument, self.source_id).metadata_, before)
            self.assertEqual(list(db.scalars(select(FinancialTransaction.id))), [])
