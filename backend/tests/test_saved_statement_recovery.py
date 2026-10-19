from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import select
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction, FinancialStatementPeriod
from services.financial.pdf_candidates import PdfMappingError
from services.financial.saved_statement_recovery import (
    StatementRecoveryRequest, read_recovery, preview_recovery, save_recovery,
)
from services.financial.statement_details import read_statement_details
from tests.test_financial_statement_import import StatementImportTests as Fixture


class SavedStatementRecoveryTests(TestCase):
    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.receipt = self.f.confirm()
        self.source_id = UUID(self.receipt['source_document_id'])
        from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
        WorkspaceEntry.__table__.create(self.f.db.get_bind(), checkfirst=True)
        WorkspaceEntryLink.__table__.create(self.f.db.get_bind(), checkfirst=True)

    def tearDown(self):
        self.f.tearDown()

    def read(self):
        with self.f.SessionLocal() as db:
            return read_recovery(db, case_id=self.f.case.id, source_id=self.source_id)

    def request(self):
        view = self.read()
        ids = [row['key'] for row in view['transactions']]
        sections = [dict(key=f'section-{index}', holder='Synthetic holder', account_number=f'TEST-{index}',
            institution='Synthetic bank', currency=currency, period_start='2023-01-01', period_end='2023-12-31',
            transaction_ids=ids[index::2]) for index, currency in enumerate(('EUR', 'USD'))]
        return dict(expected_revision=view['recovery_revision'], sections=sections,
            reason='The source contains two distinct printed account sections.')

    def preview(self, raw):
        with self.f.SessionLocal() as db:
            return preview_recovery(db, case_id=self.f.case.id, source_id=self.source_id,
                request=StatementRecoveryRequest.model_validate(raw))

    def save(self, raw):
        with self.f.SessionLocal() as db:
            return save_recovery(db, case_id=self.f.case.id, source_id=self.source_id,
                request=StatementRecoveryRequest.model_validate(raw), actor=self.f.actor)

    def test_split_reopen_preserves_history_labels_and_each_payment_once(self):
        with self.f.SessionLocal() as db:
            rows = list(db.scalars(select(FinancialTransaction)))
            row = rows[0]
            row.metadata_ = {**(row.metadata_ or {}), 'investigation_labels': dict(version=1,
                from_name='Reviewed sender', to_name='Reviewed recipient', category='Reviewed category')}
            db.commit()
            original = {r.id: (r.amount_minor, deepcopy(r.metadata_), r.ref_id, r.currency) for r in rows}
        raw = self.request()
        preview = self.preview(raw)
        self.assertEqual(preview['transaction_count'], 12)
        raw['expected_preview'] = preview['revision']
        result = self.save(raw)
        self.assertEqual(self.save(raw), result)
        with self.f.SessionLocal() as db:
            old = db.get(FinancialSourceDocument, self.source_id)
            self.assertEqual(old.status, 'superseded')
            current = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.ledger_status == 'admitted')))
            self.assertEqual(len(current), 12)
            self.assertEqual(len(result['replacements']), 12)
            for replacement in current:
                before_id = UUID(replacement.provenance['correction']['previous_transaction_id'])
                amount, labels, reference, currency = original[before_id]
                self.assertEqual(replacement.amount_minor, amount)
                self.assertEqual(replacement.metadata_, labels)
                before = db.get(FinancialTransaction, before_id)
                self.assertEqual(before.ref_id, reference)
                self.assertEqual(before.currency, currency)
                self.assertEqual(before.superseded_by_id, replacement.id)
                self.assertEqual(before.ledger_status, 'superseded')
            for section in result['sections']:
                details = read_statement_details(db, case_id=self.f.case.id, source_id=UUID(section['source_document_id']))
                self.assertEqual(details['currency'], section['currency'])
                self.assertIsNone(details['balances']['opening']['amount_minor'])
                period = db.get(FinancialStatementPeriod, UUID(section['period_id']))
                self.assertEqual(str(period.account_id), section['account_id'])

    def test_preview_rejects_omissions_duplicate_assignment_and_foreign_rows(self):
        for variation in ('omit', 'duplicate', 'foreign'):
            raw = self.request()
            if variation == 'omit': raw['sections'][0]['transaction_ids'].pop()
            elif variation == 'duplicate': raw['sections'][0]['transaction_ids'].append(raw['sections'][1]['transaction_ids'][0])
            else: raw['sections'][0]['transaction_ids'][0] = str(uuid4())
            with self.assertRaisesRegex(PdfMappingError, 'exactly one section'):
                self.preview(raw)
        self.assertEqual(len(self.read()['transactions']), 12)

    def test_balances_require_source_pages_and_currency_never_rounds(self):
        raw = self.request()
        raw['sections'][0]['opening'] = dict(amount_minor='0', page=999)
        with self.assertRaisesRegex(PdfMappingError, 'original PDF page'):
            self.preview(raw)
        raw = self.request()
        raw['sections'][1]['currency'] = 'JPY'
        with self.f.SessionLocal() as db:
            row = db.get(FinancialTransaction, UUID(raw['sections'][1]['transaction_ids'][0]))
            row.amount_minor += 1
            db.commit()
        raw['expected_revision'] = self.read()['recovery_revision']
        with self.assertRaisesRegex(PdfMappingError, 'decimal places'):
            self.preview(raw)

    def test_concurrent_payment_edit_invalidates_preview(self):
        raw = self.request()
        raw['expected_preview'] = self.preview(raw)['revision']
        with self.f.SessionLocal() as db:
            row = db.get(FinancialTransaction, UUID(raw['sections'][0]['transaction_ids'][0]))
            row.metadata_ = {**(row.metadata_ or {}), 'investigation_labels': {'version': 1, 'category': 'New review'}}
            db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'changed'):
            self.save(raw)
        self.assertEqual(len(self.read()['transactions']), 12)

    def test_late_failure_rolls_back_entire_recovery(self):
        with self.f.SessionLocal() as db:
            before = {row.id for row in db.scalars(select(FinancialSourceDocument))}
        raw = self.request()
        raw['expected_preview'] = self.preview(raw)['revision']
        with patch('services.financial.reconcile.reconcile_period', side_effect=RuntimeError('Injected failure')):
            with self.assertRaises(RuntimeError): self.save(raw)
        self.assertEqual(len(self.read()['transactions']), 12)
        with self.f.SessionLocal() as db:
            self.assertEqual({row.id for row in db.scalars(select(FinancialSourceDocument))}, before)

    def test_other_case_cannot_read_saved_import(self):
        with self.f.SessionLocal() as db, self.assertRaisesRegex(PdfMappingError, 'not found'):
            read_recovery(db, case_id=uuid4(), source_id=self.source_id)

    def test_incomplete_record_is_assigned_and_correction_remains_pending_after_unreconciled_split(self):
        from pathlib import Path
        from services.financial.imported_records import CompleteImportedRecord, complete_record
        self.f.tearDown()
        self.f.setUp()
        request = self.f.request()
        pending = next(row for row in request['rows'] if not row['excluded'])
        correct_date = pending['date']
        pending['date'] = ''
        pending['reason'] = 'The date needs source review.'
        self.source_id = UUID(self.f.confirm_legacy(request)['source_document_id'])
        raw = self.request()
        with self.assertRaisesRegex(PdfMappingError, 'incomplete record'):
            self.preview(raw)
        record = self.read()['incomplete_records'][0]
        raw['sections'][1]['incomplete_ids'] = [record['id']]
        raw['expected_preview'] = self.preview(raw)['revision']
        saved = self.save(raw)
        source = UUID(saved['sections'][1]['source_document_id'])
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, source)
            remaining = document.metadata_['statement_incomplete_records'][0]
            self.assertEqual(remaining['correction_currency'], 'USD')
            corrected = {**remaining['correction'], 'date': correct_date, 'reason': 'Date checked against the original.'}
        result = complete_record(session_factory=self.f.SessionLocal, case_id=self.f.case.id, source_id=source,
            request=CompleteImportedRecord.model_validate(dict(row=corrected, currency='USD', version=record.get('version', 0))),
            actor=self.f.actor)
        self.assertTrue(result['pending_reconciliation'])
        self.assertIsNone(result['transaction_id'])
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, source)
            saved_record = document.metadata_['statement_incomplete_records'][0]
            self.assertEqual(saved_record['correction_currency'], 'USD')
            self.assertEqual(saved_record['correction']['date'], correct_date)
            self.assertFalse(saved_record.get('resolved_transaction_id'))
            self.assertEqual(saved_record['version'], record.get('version', 0) + 1)

    def test_old_ready_batch_does_not_offer_split_records_as_new_import(self):
        from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
        from services.financial.statement_file_status import statement_file_status
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, self.source_id)
            batch = Batch(id=uuid4(), case_id=self.f.case.id, created_by=self.f.actor.user_id, actor={}, files=[], status='review')
            db.add(batch); db.flush()
            db.add(Item(id=uuid4(), batch_id=batch.id, file_id=self.f.file.id,
                statement_key=source.metadata_.get('statement_import_statement_id') or '', status='ready', summary={'can_import': True}))
            db.commit()
        raw = self.request()
        raw['expected_preview'] = self.preview(raw)['revision']
        self.save(raw)
        with self.f.SessionLocal() as db:
            item = next(item for item in statement_file_status(db, case_id=self.f.case.id)['files'] if item['evidence_file_id'] == str(self.f.file.id))
            self.assertEqual(item['available_periods'], 0)
            self.assertEqual(item['current_transactions'], 12)

    def test_existing_timeline_payment_resolves_new_currency_and_keeps_its_identity(self):
        from types import SimpleNamespace
        from services.timeline_entries import _payment_event, resolve_entry
        raw = self.request()
        selected = UUID(raw['sections'][1]['transaction_ids'][0])
        with self.f.SessionLocal() as db:
            snapshot = _payment_event(db.get(FinancialTransaction, selected), 'saved-timeline-key')
        entry = SimpleNamespace(case_id=self.f.case.id, source_kind='transaction', source_id=selected, event_snapshot=snapshot)
        raw['expected_preview'] = self.preview(raw)['revision']
        self.save(raw)
        with self.f.SessionLocal() as db:
            resolved = resolve_entry(db, entry)
            self.assertEqual(resolved['key'], snapshot['key'])
            self.assertIn('USD', resolved['amount'])
            self.assertIn('EUR', snapshot['amount'])

    def test_finding_stays_linked_in_exports_after_account_currency_recovery(self):
        from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
        from services.financial.transaction_notes import capture_transaction_notes
        raw = self.request()
        previous = raw['sections'][1]['transaction_ids'][0]
        with self.f.SessionLocal() as db:
            entry = WorkspaceEntry(case_id=self.f.case.id, entry_type='note', title='Reviewed payment', body='Recorded interpretation.', author_name='Investigator')
            db.add(entry); db.flush()
            db.add(WorkspaceEntryLink(case_id=self.f.case.id, entry_id=entry.id, target_type='evidence',
                target_id=str(self.f.file.id), target_label='Synthetic statement.pdf', source_anchor=dict(financial_transaction_ids=[previous])))
            db.commit()
        raw['expected_preview'] = self.preview(raw)['revision']
        result = self.save(raw)
        current_id = next(pair['id'] for pair in result['replacements'] if pair['previous_id'] == previous)
        with self.f.SessionLocal() as db:
            row = db.get(FinancialTransaction, UUID(current_id))
            notes = capture_transaction_notes(db, case_id=self.f.case.id, readings=[dict(
                row=dict(key=current_id, ref_id=row.ref_id, ledger_status=row.ledger_status),
                source=dict(evidence_file_id=str(self.f.file.id)))])
            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0]['links'][0]['transactions'][0]['transaction_id'], current_id)
            self.assertEqual(notes[0]['links'][0]['source_anchor']['financial_transaction_ids'], [previous])

    def test_recovered_payment_can_be_corrected_again_through_normal_table_editor(self):
        from services.financial.payment_edits import PaymentEditRequest, preview_payment_edits, save_payment_edits
        raw = self.request()
        raw['expected_preview'] = self.preview(raw)['revision']
        saved = self.save(raw)
        identity = saved['replacements'][0]['id']
        request = dict(transactions=[dict(id=identity, version=0)], changes=dict(description='Further source correction'))
        with self.f.SessionLocal() as db:
            preview = preview_payment_edits(db, case_id=self.f.case.id, request=PaymentEditRequest.model_validate(request))
        request['expected_revision'] = preview['revision']
        with self.f.SessionLocal() as db:
            result = save_payment_edits(db, case_id=self.f.case.id, request=PaymentEditRequest.model_validate(request), actor=self.f.actor)
            row = db.get(FinancialTransaction, UUID(result['replacements'][0]['id']))
            self.assertEqual(row.description, 'Further source correction')
            self.assertEqual(row.provenance['correction']['previous_transaction_id'], identity)

    def test_reopen_pdf_choose_each_recovered_section_and_follow_old_source(self):
        from services.financial.statement_import import read_statement_import
        from services.financial.ledger_source import ledger_source
        from services.financial.statement_import_controls import read_import_controls
        from services.financial.statement_file_status import statement_file_status
        raw = self.request()
        raw['sections'][0]['opening'] = dict(amount_minor='0', page=1)
        raw['expected_preview'] = self.preview(raw)['revision']
        saved = self.save(raw)
        with self.f.SessionLocal() as db:
            opened = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id)
            self.assertEqual(len(opened['statement_choices']), 2)
            for choice in opened['statement_choices']:
                selected = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id, statement_id=choice['id'])
                self.assertTrue(selected['recovered_saved_section'])
                self.assertEqual(selected['current_import']['transaction_count'], 6)
                self.assertEqual(selected['currency'], choice['currency'])
            for section in saved['sections']:
                document = db.get(FinancialSourceDocument, UUID(section['source_document_id']))
                period = db.get(FinancialStatementPeriod, UUID(section['period_id']))
                controls = read_import_controls(period, document, self.f.file)
                self.assertEqual(controls['currency'], section['currency'])
            for pair in saved['replacements']:
                old = ledger_source(db, case_id=self.f.case.id, transaction_id=UUID(pair['previous_id']))
                current = ledger_source(db, case_id=self.f.case.id, transaction_id=UUID(pair['id']))
                self.assertEqual(old['evidence_file_id'], current['evidence_file_id'])
                self.assertEqual(old['locator'], current['locator'])
                self.assertEqual(old['superseded_by_id'], pair['id'])
            files = statement_file_status(db, case_id=self.f.case.id)['files']
            item = next(item for item in files if item['evidence_file_id'] == str(self.f.file.id))
            self.assertEqual(item['current_transactions'], 12)
