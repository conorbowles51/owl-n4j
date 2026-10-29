"""Withdrawing rows the investigator entered, repeat explanations, the
balance with and without added rows, and printed corrections that prove on
their own (synthetic fixture only)."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID
from sqlalchemy import select
from tests import test_financial_statement_import as fixtures
from tests.financial_reconciled_fixture import install_reconciled_source
from tests import test_financial_statement_admission as admission_tests
from services.financial.statement_import import StatementImportRequest
from services.financial.import_batches import initial_request
from services.financial.account_history import account_history
from services.financial.pdf_candidates import PdfMappingError, _digest
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument


class RecordWithdrawalTests(TestCase):
    _manual = admission_tests.StatementAdmissionTests._manual
    _append = admission_tests.StatementAdmissionTests._append
    _retained_unreadable_amount = admission_tests.StatementAdmissionTests._retained_unreadable_amount
    _complete = admission_tests.StatementAdmissionTests._complete

    def setUp(self):
        self.f = fixtures.StatementImportTests(); self.f.setUp()
        install_reconciled_source(self.f)
    def tearDown(self): self.f.tearDown()
    def request(self): return StatementImportRequest.model_validate(initial_request(self.f.preview()))

    def _records(self):
        from services.financial.imported_records import imported_records
        with self.f.SessionLocal() as db:
            return imported_records(db, case_id=self.f.case.id)

    def _change(self, source, record, *, restore=False, reason=''):
        from services.financial.record_withdrawal import RecordWithdrawal, change
        return change(session_factory=self.f.SessionLocal, case_id=self.f.case.id, source_id=source, actor=self.f.actor,
            restore=restore, request=RecordWithdrawal(record_id=record['id'], version=record['version'], reason=reason))

    def _admitted(self):
        with self.f.SessionLocal() as db:
            return len([t for t in db.scalars(select(FinancialTransaction)) if t.ledger_status == 'admitted'])

    def _status(self):
        with self.f.SessionLocal() as db:
            return account_history(db, case_id=self.f.case.id)['groups'][0]['periods'][0]['status']

    def test_withdrawing_a_wrong_addition_lets_the_held_correction_in_and_can_be_undone(self):
        from services.financial import held_record_admission
        source, repaired = self._retained_unreadable_amount()
        # Held under the all-together rule: the wrong addition blocks the
        # correct correction (the live situation before individual admission).
        with patch.object(held_record_admission, 'INDIVIDUAL_ADMISSION', False):
            self._append(source, self._manual(source, direction='credit', description='Wrong addition'))
            self.assertTrue(self._complete(source, repaired)['pending_reconciliation'])
            listing = self._records()
            [effects] = listing['addition_effects']
            # The added row is the only reason the statement does not add up.
            self.assertTrue(effects['held_only_by_additions'])
            self.assertFalse(effects['with_all']['reconciles'])
            self.assertTrue(effects['without_additions']['reconciles'])
            self.assertEqual(effects['with_all']['difference_minor'] not in (None, 0, '0'), True)
            added = next(r for r in listing['records'] if r['kind'] == 'added')
            self.assertTrue(added['without_this']['reconciles'])
            self.assertTrue(added['can_withdraw'])
            printed = next(r for r in listing['records'] if r['kind'] == 'printed')
            self.assertTrue(printed['can_withdraw'])
            self.assertEqual(self._admitted(), 11)
            result = self._change(source, added, reason='Entered twice')
        self.assertEqual((result['withdrawn'], result['admitted'], result['statement_reconciles']), (True, 1, True))
        self.assertEqual(self._admitted(), 12)
        self.assertEqual(self._status(), 'reconciled')
        listing = self._records()
        self.assertEqual((listing['total'], listing['withdrawn_total']), (0, 1))
        [withdrawn] = listing['withdrawn']
        self.assertEqual(withdrawn['withdrawn']['reason'], 'Entered twice')
        self.assertFalse(withdrawn['can_withdraw'])
        with self.f.SessionLocal() as db:
            record = next(r for r in db.get(FinancialSourceDocument, source).metadata_['statement_incomplete_records']
                          if r['id'] == withdrawn['id'])
            self.assertEqual([h['action'] for h in record['withdrawal_history']], ['withdrawn'])
        # A replay changes nothing; a stale version cannot restore blindly.
        self.assertFalse(self._change(source, added)['changed'])
        with self.assertRaisesRegex(PdfMappingError, 'Another investigator'):
            self._change(source, added, restore=True)
        restored = self._change(source, withdrawn, restore=True)
        self.assertEqual((restored['withdrawn'], restored['changed']), (False, True))
        listing = self._records()
        self.assertEqual((listing['total'], listing['withdrawn_total']), (1, 0))
        [again] = listing['records']
        self.assertEqual(again['hold_reason'], held_record_admission.NO_FIT_REASON)
        # Restoring keeps the statement on its proven rows; the row stays held.
        self.assertEqual(self._admitted(), 12)
        self.assertEqual(self._status(), 'reconciled')
        with self.f.SessionLocal() as db:
            record = next(r for r in db.get(FinancialSourceDocument, source).metadata_['statement_incomplete_records']
                          if r['id'] == again['id'])
            self.assertEqual([h['action'] for h in record['withdrawal_history']], ['withdrawn', 'restored'])

    def test_repeat_names_the_row_it_matches_and_withdraws_in_one_step(self):
        saved = self.f.confirm(self.request().model_dump()); source = UUID(saved['source_document_id'])
        with self.f.SessionLocal() as db:
            existing = next(t for t in db.scalars(select(FinancialTransaction)) if t.ledger_status == 'admitted')
            day = existing.transaction_date or existing.posted_date or existing.value_date or existing.effective_date
            repeat = self._manual(source, direction=getattr(existing.direction, 'value', existing.direction),
                amount=str(existing.amount_minor), date=day.isoformat(), description='Re-entered payment')
        self._append(source, repeat)
        [record] = self._records()['records']
        self.assertEqual(record['repeat_of']['kind'], 'saved')
        self.assertEqual(record['repeat_of']['transaction_id'], str(existing.id))
        self.assertEqual((record['repeat_of']['date'], record['repeat_of']['amount_minor']),
                         (day.isoformat(), str(existing.amount_minor)))
        self.assertTrue(record['can_withdraw'])
        result = self._change(source, record)
        self.assertTrue(result['withdrawn'])
        self.assertEqual(self._records()['total'], 0)
        self.assertEqual(self._admitted(), 12)
        self.assertEqual(self._status(), 'reconciled')

    def test_printed_rows_without_a_correction_cannot_be_withdrawn(self):
        source, _repaired = self._retained_unreadable_amount()
        [record] = self._records()['records']
        self.assertFalse(record['can_withdraw'])
        with self.assertRaisesRegex(PdfMappingError, 'Only a row you added or corrected'):
            self._change(source, record)

    def _retained_zero_line(self):
        """A saved statement that reconciles, plus a held printed line read without its date whose printed
        amount is 0.00 (``Interest Charge on Cash Advances 0.00``)."""
        saved = self.f.confirm(self.request().model_dump()); source = UUID(saved['source_document_id'])
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, source)
            metadata = deepcopy(document.metadata_)
            cells = [dict(column_index=0, expected_text='Interest Charge on Cash Advances'),
                     dict(column_index=1, expected_text='0.00')]
            original = dict(id='1:0:99', kind='unresolved', fields={'charge_group': 'interest'}, excluded=False,
                            issues=['Check this row in the transaction section. Its date or layout could not be read.'],
                            page_number=1, table_index=0, row_index=99, source_cells=cells)
            fields = dict(id='1:0:99', date='', reason='', excluded=False, direction=None, date_values={},
                          description='', manual_page=None, amount_minor='', counterparty='', balance_minor=None,
                          date_unprinted=False)
            metadata['statement_import_original']['rows'].append(original)
            metadata['statement_import_request']['rows'].append(deepcopy(fields))
            metadata['statement_incomplete_records'] = [dict(id='1:0:99', fields=fields, original=original,
                                                             missing_fields=['amount'], version=0)]
            for key in ('statement_import_original', 'statement_import_request'):
                metadata[key + '_sha256'] = _digest(metadata[key])
            metadata.pop('statement_admission', None); document.metadata_ = metadata; db.commit()
        return source

    def test_a_printed_line_of_no_money_can_be_withdrawn_and_then_takes_no_part(self):
        source = self._retained_zero_line()
        [record] = self._records()['records']
        self.assertTrue(record['can_withdraw'])
        result = self._change(source, record, reason='Page prints 0.00: no payment.')
        self.assertEqual((result['withdrawn'], result['changed']), (True, True))
        listing = self._records()
        self.assertEqual((listing['total'], listing['withdrawn_total']), (0, 1))
        self.assertEqual(self._admitted(), 12)
        with self.f.SessionLocal() as db:
            from services.financial.saved_statement_admission import assess_saved_additions
            document = db.get(FinancialSourceDocument, source)
            from postgres.models.financial import FinancialStatementPeriod
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == source))
            self.assertTrue(assess_saved_additions(db, document, period, document.metadata_, 'EUR')['can_import'])
        [withdrawn] = listing['withdrawn']
        restored = self._change(source, withdrawn, restore=True)
        self.assertEqual((restored['withdrawn'], self._records()['total']), (False, 1))

    def test_a_printed_line_with_money_or_switched_off_still_cannot_be_withdrawn(self):
        from services.financial import record_withdrawal
        source = self._retained_zero_line()
        [record] = self._records()['records']
        with patch.object(record_withdrawal, 'PRINTED_ZERO', False):
            with self.assertRaisesRegex(PdfMappingError, 'Only a row you added or corrected'):
                self._change(source, record)
        for texts in (['Interest Charge on Purchases', '9.32'], ['0.00', 'Interest', '9.32'], ['Interest Charge', 'O.DO']):
            item = dict(original=dict(kind='unresolved', fields={}, source_cells=[dict(expected_text=t) for t in texts]))
            self.assertFalse(record_withdrawal.printed_zero(item), texts)
        self.assertTrue(record_withdrawal.printed_zero(dict(original=dict(kind='unresolved', fields={},
            source_cells=[dict(expected_text='Interest Charge on Cash Advances'), dict(expected_text='$0.00')]))))

    def test_an_admitted_added_row_is_set_aside_through_adjudication(self):
        source, repaired = self._retained_unreadable_amount()
        self._complete(source, repaired)
        with self.f.SessionLocal() as db:
            record = next(r for r in db.get(FinancialSourceDocument, source).metadata_['statement_incomplete_records']
                          if r['id'] == repaired['id'])
        result = self._change(source, record, reason='Checked against the PDF')
        self.assertEqual((result['withdrawn'], result['set_aside']), (True, 'quarantined'))
        self.assertEqual(self._admitted(), 11)
        back = self._change(source, record, restore=True)
        self.assertEqual(back['withdrawn'], False)
        self.assertEqual(self._admitted(), 12)

    def _two_retained_rows(self):
        """Printed row A lost its amount; printed row B lost only its date."""
        request = self.request().model_dump(); saved = self.f.confirm(request); source = UUID(saved['source_document_id'])
        a, b = [r for r in request['rows'] if not r['excluded']][:2]
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, source)
            metadata = deepcopy(document.metadata_)
            rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == document.id)))
            keep = next(t for t in rows if t.provenance['statement_import_original']['id'] not in (a['id'], b['id']))
            for tx in rows:
                if tx.provenance['statement_import_original']['id'] in (a['id'], b['id']):
                    tx.ledger_status = 'superseded'; tx.superseded_by_id = keep.id
            originals = {r['id']: r for r in metadata['statement_import_original']['rows']}
            metadata['statement_incomplete_records'] = []
            for row in metadata['statement_import_request']['rows']:
                if row['id'] in (a['id'], b['id']):
                    missing = 'amount' if row['id'] == a['id'] else 'date'
                    row['amount_minor' if missing == 'amount' else 'date'] = ''
                    metadata['statement_incomplete_records'].append(dict(id=row['id'], fields=deepcopy(row),
                        original=originals[row['id']], missing_fields=[missing], version=0))
            metadata['statement_import_request_sha256'] = _digest(metadata['statement_import_request'])
            metadata.pop('statement_admission', None); document.metadata_ = metadata; db.commit()
        return source, a, b

    def test_a_right_printed_correction_enters_on_its_own_beside_a_wrong_one(self):
        from services.financial.held_record_admission import BASE_REASON
        source, a, b = self._two_retained_rows()
        wrong_b = {**b, 'amount_minor': str(int(b['amount_minor']) + 100)}
        self.assertTrue(self._complete(source, wrong_b)['pending_reconciliation'])
        # A proves on its own (B keeps its printed amount, missing only a date);
        # B's wrong amount does not, so it stays held.
        done = self._complete(source, a)
        self.assertTrue(done['transaction_id'])
        self.assertEqual(self._admitted(), 11)
        [held] = self._records()['records']
        self.assertEqual((held['id'], held['hold_reason']), (b['id'], BASE_REASON))
        self.assertTrue(held['can_withdraw'])
        # Withdrawing B's correction returns it to its own reading (missing a date).
        self._change(source, held, reason='Wrong amount')
        [open_b] = self._records()['records']
        self.assertEqual((open_b['missing_fields'], open_b['has_withdrawn_correction'], open_b['fields']['amount_minor']),
                         (['date'], True, b['amount_minor']))
        from services.financial.imported_records import complete_record, CompleteImportedRecord
        complete_record(session_factory=self.f.SessionLocal, case_id=self.f.case.id, source_id=source, actor=self.f.actor,
            request=CompleteImportedRecord(row=b, currency='EUR', version=open_b['version']))
        self.assertEqual(self._admitted(), 12)
        self.assertEqual(self._status(), 'reconciled')

    def test_a_correction_never_enters_while_another_row_lacks_its_amount(self):
        source, a, b = self._two_retained_rows()
        # B (missing only a date) corrected; A still lacks its amount, so the
        # arithmetic is incomplete and B is held (fail closed).
        self.assertTrue(self._complete(source, b)['pending_reconciliation'])
        self.assertEqual(self._admitted(), 10)
