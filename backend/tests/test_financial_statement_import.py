import hashlib
from pathlib import Path
from uuid import uuid4, UUID
from services.financial.decisions import Actor
from unittest.mock import patch
from sqlalchemy import select
from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from services.financial.statement_import import read_statement_import, confirm_statement_import
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_transactions_writer import TransactionPersistenceTestCase
from tests.test_financial_pdf_geometry_candidates import rectangle
from tests.test_financial_statement_import_proposal import statement


class StatementImportTests(TransactionPersistenceTestCase):
    def setUp(self):
        super().setUp()
        self.actor=Actor(self.user.name,self.user.email,self.user.id)
        Base.metadata.create_all(self.db.connection(), tables=[EvidenceDocumentText.__table__, EvidenceTableGeometry.__table__,
            FinancialImportBatch.__table__, FinancialImportBatchItem.__table__])
        self.path=Path(self._directory)/'statement.pdf'; self.path.write_bytes(b'%PDF-1.4\nStatement test only')
        self.file=self.evidence(hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.file.stored_path=str(self.path)
        content='Account Name: Test Company\nAccount Number: TEST123\nCurrency: EUR\n'
        job=uuid4()
        self.db.add(EvidenceDocumentText(evidence_file_id=self.file.id, content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(), character_count=len(content),
            engine_job_id=job, source_locations=[dict(kind='page',page_number=1,start_char=0,end_char=len(content),text_origin='digital_text_layer')]))
        self.db.add(EvidenceTableGeometry(evidence_file_id=self.file.id,page_number=1,engine_job_id=job,
            payload=[dict(table_source='drawn_geometry',geometry_source='cell_rectangles',
                table=dict(page=1,table=rectangle(0,x=0,width=600,height=600),unlocated_values=0,
                    values=[dict(row=row['row_index'],column=c['column_index'],text=c['expected_text'],
                        locator=rectangle(20+row['row_index']*20,x=20+c['column_index']*100,width=90,height=15))
                        for row in statement()['rows'] for c in row['cells']]))]))
        self.db.commit()

    def preview(self):
        with self.SessionLocal() as db:
            return read_statement_import(db,case_id=self.case.id,evidence_file_id=self.file.id)

    def request(self):
        p=self.preview()
        return dict(expected_revision=p['revision'],currency='EUR',holder='Test Company',account_number='TEST123',institution=p['metadata']['institution'],period_start=p['metadata']['period_start'],period_end=p['metadata']['period_end'],
            rows=[dict(id=r['id'],excluded=r['excluded'],date=r['fields'].get('date',''),
                description=r['fields'].get('description',''),counterparty=r['fields'].get('counterparty',''),amount_minor=r['fields'].get('amount_minor','0'),
                direction=r['fields'].get('direction','credit'),balance_minor=r['fields'].get('balance'),reason='') for r in p['rows']])

    def confirm(self,request=None):
        return confirm_statement_import(session_factory=self.SessionLocal,case_id=self.case.id,
            evidence_file_id=self.file.id,request=request or self.request(),actor=self.actor,resolve_path=Path)

    def test_existing_import_and_same_request_keep_the_saved_account_for_navigation(self):
        request = self.request()
        saved = self.confirm(request)
        current = self.preview()['current_import']
        self.assertEqual(current['account_id'], saved['account_id'])
        self.assertEqual(current['source_document_id'], saved['source_document_id'])
        self.assertEqual(current['filename'], self.file.original_filename)
        repeated = self.confirm(request)
        self.assertEqual(repeated['account_id'], saved['account_id'])
        self.assertFalse(repeated['created'])
        self.assertEqual(repeated['transaction_count'], saved['transaction_count'])

    def excluded_import(self):
        from copy import deepcopy
        from services.financial.duplicate_decisions import decide_duplicate, duplicate_revision
        primary_request = self.request()
        primary_request.update(institution='Synthetic Bank', details_reason='Bank checked against the test source.')
        primary = self.confirm(primary_request)
        primary_file = self.file
        raw = self.path.read_bytes() + b'\n% duplicate copy'
        copy_path = Path(self._directory) / 'copy.pdf'
        copy_path.write_bytes(raw)
        copied = self.evidence(hashlib.sha256(raw).hexdigest())
        copied.stored_path = str(copy_path)
        text = self.db.get(EvidenceDocumentText, primary_file.id)
        geometry = self.db.get(EvidenceTableGeometry, (primary_file.id, 1))
        self.db.add(EvidenceDocumentText(evidence_file_id=copied.id, content=text.content,
            content_sha256=text.content_sha256, character_count=text.character_count,
            engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
        self.db.add(EvidenceTableGeometry(evidence_file_id=copied.id, page_number=1,
            engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
        self.db.commit()
        self.file = copied
        request = self.request()
        request.update(institution='Synthetic Bank', details_reason='Bank checked against the test source.')
        duplicate = self.confirm(request)
        with self.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, UUID(duplicate['source_document_id']))
            retained = db.get(FinancialSourceDocument, UUID(primary['source_document_id']))
            decide_duplicate(db, case_id=self.case.id, document_id=source.id, action='exclude',
                expected_revision=duplicate_revision(db, source), primary_id=retained.id,
                expected_primary_revision=duplicate_revision(db, retained), actor=self.actor,
                reason='Same printed payments; retain the primary synthetic statement.')
        return primary_file, duplicate, request

    def test_excluded_pdf_reopens_its_decision_and_refuses_another_import(self):
        primary_file, duplicate, request = self.excluded_import()
        current = self.preview()['current_import']
        self.assertTrue(current['excluded_as_duplicate'])
        self.assertEqual(current['source_document_id'], duplicate['source_document_id'])
        self.assertEqual(current['transaction_count'], 0)
        self.assertEqual(current['retained_filename'], primary_file.original_filename)
        with self.assertRaisesRegex(PdfMappingError, 'excluded as a duplicate'):
            self.confirm(request)
        with self.SessionLocal() as db:
            primary = read_statement_import(db, case_id=self.case.id, evidence_file_id=primary_file.id)
            self.assertFalse(primary['current_import']['excluded_as_duplicate'])
            self.assertEqual(primary['current_import']['transaction_count'], 12)
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction).where(
                FinancialTransaction.ledger_status == 'admitted')))), 12)
            from services.financial.duplicate_decisions import decide_duplicate, duplicate_revision
            source = db.get(FinancialSourceDocument, UUID(duplicate['source_document_id']))
            decide_duplicate(db, case_id=self.case.id, document_id=source.id, action='restore',
                expected_revision=duplicate_revision(db, source), actor=self.actor,
                reason='Restore the recorded synthetic exclusion for the continuation check.')
        restored = self.preview()['current_import']
        self.assertFalse(restored['excluded_as_duplicate'])
        self.assertEqual(restored['transaction_count'], 12)
        self.assertFalse(self.confirm(request)['created'])

    def test_rereading_the_same_excluded_source_cannot_bypass_its_decision(self):
        from copy import deepcopy
        from services.financial.statement_reprocessing import create_statement_version
        _, _, _ = self.excluded_import()
        original_id = self.file.id
        with self.SessionLocal() as db:
            version = create_statement_version(db, case_id=self.case.id, evidence_file_id=original_id,
                request_id=uuid4(), actor=self.actor, resolve_path=Path)
            text = db.get(EvidenceDocumentText, original_id)
            geometry = db.get(EvidenceTableGeometry, (original_id, 1))
            db.add(EvidenceDocumentText(evidence_file_id=version.id, content=text.content,
                content_sha256=text.content_sha256, character_count=text.character_count,
                engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
            db.add(EvidenceTableGeometry(evidence_file_id=version.id, page_number=1,
                engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
            db.commit()
            version_id = version.id
        self.file = self.db.get(type(self.file), version_id)
        self.assertTrue(self.preview()['current_import']['excluded_as_duplicate'])
        with self.assertRaisesRegex(PdfMappingError, 'excluded as a duplicate'):
            self.confirm()

    def prepare_long_statement(self, count):
        from tests.test_financial_statement_import_proposal import source
        job = self.db.get(EvidenceDocumentText, self.file.id).engine_job_id
        self.db.query(EvidenceTableGeometry).filter_by(evidence_file_id=self.file.id).delete()
        for start in range(0, count, 25):
            page = start // 25 + 1
            grids = [source([['Date', 'Description', 'Credit', 'Debit', 'Balance']] + [
                ['2024-01-01', f'Payment {i}', '1.00', '', str(i + 1)]
                for i in range(start, min(start + 25, count))]),
                source([['Account Name: Test Company'], ['Account Number: TEST123'],
                        ['Currency: EUR'], ['Bank: Example Bank'], [f'Page {page} of {(count + 24) // 25}']])]
            payload = [dict(table_source='drawn_geometry', geometry_source='cell_rectangles',
                table=dict(page=page, table={**rectangle(0, x=0, width=600, height=800), 'page': page}, unlocated_values=0,
                    values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'],
                        locator={**rectangle(20 + r['row_index'] * 20, x=20 + c['column_index'] * 100, width=90, height=15), 'page': page})
                        for r in grid['rows'] for c in r['cells']])) for grid in grids]
            self.db.add(EvidenceTableGeometry(evidence_file_id=self.file.id, page_number=page,
                engine_job_id=job, payload=payload))
        self.db.commit()

    def test_five_thousand_payments_keep_all_headings_and_import_every_payment(self):
        from services.financial.statement_import import StatementImportRequest, check_import_request
        self.prepare_long_statement(5000)
        preview = self.preview()
        self.assertEqual(preview['transaction_count'], 5000)
        self.assertEqual(len(preview['rows']), 6200)
        self.assertEqual(preview['needs_attention'], 0)
        request = StatementImportRequest.model_validate(self.request())
        check_import_request(preview, request)
        self.assertEqual(len(request.rows), 6200)
        result = self.confirm(request.model_dump(mode='json'))
        self.assertEqual(result['transaction_count'], 5000)
        with self.SessionLocal() as db:
            payments = list(db.scalars(select(FinancialTransaction).where(
                FinancialTransaction.source_document_id == UUID(result['source_document_id']))))
            self.assertEqual(len(payments), 5000)
            self.assertEqual({r.description for r in payments}, {f'Payment {i}' for i in range(5000)})
            self.assertEqual(sum(r.amount_minor for r in payments), 500000)
        # Excluded text must still be accounted for, even in a long statement.
        request = request.model_copy(update={'rows': [r for r in request.rows if not r.excluded]})
        with self.assertRaisesRegex(PdfMappingError, 'every prepared row'):
            check_import_request(preview, request)

    def test_long_statement_limits_count_payments_and_bound_all_review_text(self):
        from services.financial.statement_import import StatementImportRequest, _check_review_size
        from pydantic import ValidationError
        _check_review_size([dict(excluded=False)] * 25000)
        with self.assertRaisesRegex(PdfMappingError, '25,000 possible transactions'):
            _check_review_size([dict(excluded=False)] * 25001)
        with self.assertRaisesRegex(PdfMappingError, '100,000-row review limit'):
            _check_review_size([dict(excluded=True)] * 100001)
        request = dict(expected_revision='a' * 64, currency='EUR', holder='Example', account_number='123',
            rows=[dict(id=str(i), date='2024-01-01', description='Payment', amount_minor='100', direction='credit')
                  for i in range(25000)])
        self.assertEqual(len(StatementImportRequest.model_validate(request).rows), 25000)
        request['rows'].append({**request['rows'][-1], 'id': 'overflow'})
        with self.assertRaisesRegex(ValidationError, 'up to 25,000 transactions'):
            StatementImportRequest.model_validate(request)

    def card_balance_request(self):
        from tests.test_financial_statement_import_card import card_source, summary_source
        payload = []
        for index, grid in enumerate((summary_source(), card_source())):
            payload.append(dict(table_source='drawn_geometry', geometry_source='cell_rectangles',
                table=dict(page=1, table=rectangle(0, x=0, width=600, height=800), unlocated_values=0,
                    values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'],
                        locator=c['locator'] if index == 0 else rectangle(20+r['row_index']*20, x=20+c['column_index']*180, width=170))
                        for r in grid['rows'] for c in r['cells']])))
        self.db.get(EvidenceTableGeometry, (self.file.id, 1)).payload = payload
        self.db.commit()
        with self.SessionLocal() as db:
            p = read_statement_import(db, case_id=self.case.id, evidence_file_id=self.file.id, currency='USD')
        request = dict(expected_revision=p['revision'], statement_id=p['statement_id'], currency='USD',
            **{key:p['metadata'][key] for key in ('holder', 'account_number', 'institution', 'period_start', 'period_end')}, rows=[])
        for r in p['rows']:
            fields = r['fields']
            request['rows'].append(dict(id=r['id'], excluded=r['excluded'], date=fields.get('date', p['metadata']['period_end'] if r['issues'] else ''),
                description=fields.get('description', ''), amount_minor=fields.get('amount_minor', '0'), direction=fields.get('direction', 'credit'),
                balance_minor=fields.get('balance'), reason='Synthetic interest date assigned for this test.' if r['issues'] else ''))
        return p, request

    def test_card_balances_import_as_owed_and_reopen_the_exact_summary_cells(self):
        from tests.test_financial_statement_import_card import summary_source
        from postgres.models.financial import FinancialStatementPeriod
        from services.financial.periods import read_opening, read_closing
        from services.financial.ledger_source import statement_source
        from services.financial.printed_totals import retained_total_controls
        p, request = self.card_balance_request()
        self.assertEqual(p['metadata']['balance_convention'], 'liability_owed')
        result = self.confirm(request)
        self.assertEqual(result['transaction_count'], 3)
        self.assertFalse(self.confirm(request)['created'])
        self.db.expire_all()
        period = self.db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == UUID(result['source_document_id'])))
        self.assertEqual(read_opening(period).amount.minor_units, -100000)
        self.assertEqual(read_closing(period).amount.minor_units, -93778)
        self.assertTrue(read_closing(period).is_independent)
        controls = statement_source(self.db, case_id=self.case.id, period_id=period.id)['reviewed_controls']
        self.assertEqual(controls['balance_convention'], 'liability_owed')
        self.assertEqual([c['reviewed_value'] for c in controls['controls']], ['100000', '93778'])
        self.assertEqual(controls['controls'][1]['original_text'], '= $937.78')
        self.assertEqual(controls['controls'][1]['locator'], summary_source()['rows'][9]['cells'][1]['locator'])
        document = self.db.get(FinancialSourceDocument, UUID(result['source_document_id']))
        self.assertEqual(retained_total_controls(self.db, period, document), controls)

    def test_merrick_summary_import_retains_zero_opening_and_exact_closing_source(self):
        from tests.test_financial_statement_import_merrick import summary_statement
        from postgres.models.financial import FinancialStatementPeriod
        from services.financial.periods import read_opening, read_closing
        from services.financial.ledger_source import statement_source
        data = summary_statement()
        self.db.get(EvidenceTableGeometry, (self.file.id, 1)).payload = [dict(
            table_source='drawn_geometry', geometry_source='cell_rectangles',
            table=dict(page=1, table=rectangle(0, x=0, width=600, height=800), unlocated_values=0,
                       values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'], locator=c['locator'])
                               for r in data['rows'] for c in r['cells']]))]
        self.db.commit()
        with self.SessionLocal() as db:
            p = read_statement_import(db, case_id=self.case.id, evidence_file_id=self.file.id, currency='USD')
        self.assertEqual(p['metadata']['balance_convention'], 'liability_owed')
        self.assertEqual(p['metadata']['period_start'], '')
        request = dict(expected_revision=p['revision'], statement_id=p['statement_id'], currency='USD',
                       holder=p['metadata']['holder'], account_number=p['metadata']['account_number'],
                       institution=p['metadata']['institution'], period_start='', period_end='',
                       rows=[dict(id=r['id'], excluded=r['excluded'], date=r['fields'].get('date', ''),
                                  description=r['fields'].get('description', ''),
                                  amount_minor=r['fields'].get('amount_minor', '0'),
                                  direction=r['fields'].get('direction', 'credit'),
                                  balance_minor=r['fields'].get('balance'), reason='') for r in p['rows']])
        result = self.confirm(request)
        self.assertEqual(result['transaction_count'], 2)
        self.assertFalse(self.confirm(request)['created'])
        self.db.expire_all()
        period = self.db.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == UUID(result['source_document_id'])))
        self.assertEqual(read_opening(period).amount.minor_units, 0)
        self.assertEqual(read_closing(period).amount.minor_units, -11400)
        controls = statement_source(self.db, case_id=self.case.id, period_id=period.id)['reviewed_controls']
        self.assertEqual([c['reviewed_value'] for c in controls['controls']], ['0', '11400'])
        self.assertEqual(controls['controls'][1]['original_text'], '$114.00')
        self.assertEqual(controls['controls'][1]['locator'], data['rows'][5]['cells'][1]['locator'])

    def test_changed_reader_version_requires_a_fresh_review_even_when_source_is_unchanged(self):
        from services.financial.pdf_candidates import PdfMappingError
        with patch('services.financial.statement_import.VERSION', 'statement-review-v2'):
            old_request = self.request()
        with self.assertRaisesRegex(PdfMappingError, 'prepared statement changed'):
            self.confirm(old_request)

    def multi_date_request(self):
        from tests.test_financial_statement_import_proposal import source
        grid = source([['Date', 'Posting date', 'Value date', 'Description', 'Credit', 'Debit'],
                       ['2023-01-02', '2023-01-03', '2023-01-04', 'Payment', '125.00', '']])
        self.db.get(EvidenceTableGeometry, (self.file.id, 1)).payload = [dict(
            table_source='drawn_geometry', geometry_source='cell_rectangles',
            table=dict(page=1, table=rectangle(0,x=0,width=600,height=600), unlocated_values=0,
                       values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'],
                                    locator=rectangle(20+r['row_index']*20, x=10+c['column_index']*95, width=90, height=15))
                               for r in grid['rows'] for c in r['cells']]))]
        self.db.commit()
        return self.request()

    def test_fee_only_card_import_keeps_holder_and_two_different_dates(self):
        from tests.test_financial_statement_import_card import fee_source
        data = fee_source()
        self.db.get(EvidenceTableGeometry, (self.file.id, 1)).payload = [dict(
            table_source='drawn_geometry', geometry_source='cell_rectangles',
            table=dict(page=1, table=rectangle(0,x=0,width=600,height=800), unlocated_values=0,
                       values=[dict(row=r['row_index'],column=c['column_index'],text=c['expected_text'],
                                    locator=rectangle(20+r['row_index']*20,x=10+c['column_index']*145,width=140,height=10))
                               for r in data['rows'] for c in r['cells']]))]
        self.db.commit()
        with self.SessionLocal() as db:
            proposal = read_statement_import(db,case_id=self.case.id,evidence_file_id=self.file.id,currency='USD')
        self.assertEqual(proposal['metadata']['holder'], 'SAMPLE HOLDER')
        request = dict(expected_revision=proposal['revision'],statement_id=proposal['statement_id'],currency='USD',
                       **{k:proposal['metadata'][k] for k in ('holder','account_number','institution','period_start','period_end')},
                       rows=[dict(id=r['id'],excluded=r['excluded'],date=r['fields'].get('date',''),description=r['fields'].get('description',''),
                                  amount_minor=r['fields'].get('amount_minor','0'),direction=r['fields'].get('direction'),reason='') for r in proposal['rows']])
        fee=request['rows'][7]
        fee.update(date_values={'booking_date':'2022-03-10'},reason='Corrected the posting date after checking the source.')
        result=self.confirm(request)
        self.assertEqual(result['transaction_count'],1)
        self.db.expire_all()
        payment=self.db.scalar(select(FinancialTransaction).where(FinancialTransaction.source_document_id==UUID(result['source_document_id'])))
        self.assertEqual((str(payment.transaction_date),str(payment.posted_date)),('2022-03-08','2022-03-10'))
        self.assertEqual(payment.amount_minor,2500)
        self.assertEqual(payment.provenance['statement_import_original']['fields']['booking_date'],'2022-03-09')

    def test_correcting_posting_and_value_dates_keeps_transaction_date_and_originals(self):
        from datetime import date
        request = self.multi_date_request()
        request['rows'][1]['date_values'] = dict(booking_date='2023-01-05', value_date='2023-01-06')
        with self.assertRaisesRegex(PdfMappingError, 'Explain the correction'):
            self.confirm(request)
        request['rows'][1]['reason'] = 'Checked the separate posting and value dates in the original.'
        result = self.confirm(request)
        self.db.expire_all()
        payment = self.db.scalar(select(FinancialTransaction).where(FinancialTransaction.source_document_id == UUID(result['source_document_id'])))
        self.assertEqual((payment.transaction_date,payment.posted_date,payment.value_date), (date(2023,1,2),date(2023,1,5),date(2023,1,6)))
        original = payment.provenance['statement_import_original']['fields']
        self.assertEqual((original['booking_date'],original['value_date']), ('2023-01-03','2023-01-04'))
        self.assertEqual(payment.provenance['statement_import_review']['date_values'], request['rows'][1]['date_values'])
        self.assertFalse(self.confirm(request)['created'])

    def test_clearing_an_unreadable_secondary_date_records_the_decision_without_losing_other_dates(self):
        request = self.multi_date_request()
        request['rows'][1].update(date_values={'booking_date':''}, reason='Posting date cannot be confirmed from the source.')
        result = self.confirm(request)
        self.db.expire_all()
        payment = self.db.scalar(select(FinancialTransaction).where(FinancialTransaction.source_document_id == UUID(result['source_document_id'])))
        self.assertIsNone(payment.posted_date)
        self.assertEqual(str(payment.transaction_date), '2023-01-02')
        self.assertEqual(str(payment.value_date), '2023-01-04')

    def test_date_corrections_cannot_invent_a_date_role_or_override_the_primary_twice(self):
        from pydantic import ValidationError
        for values in ({'booking_date':'2023-01-05'}, {'date':'2023-01-05'}, {'effective_date':'2023-01-05'}, {'value_date':'2023-02-30'}):
            request = self.request()
            request['rows'][1].update(date_values=values, reason='Attempted unsupported date correction.')
            with self.subTest(values=values), self.assertRaises((PdfMappingError, ValidationError)):
                self.confirm(request)

    def test_correcting_only_a_damaged_merrick_date_preserves_other_readings_and_original_date(self):
        from services.financial.statement_import import StatementImportRequest
        from pydantic import ValidationError
        from tests.test_financial_statement_import_merrick import measured_statement
        data = measured_statement()
        data['rows'][6]['cells'][0]['expected_text'] = 'O4/22'
        values = [dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'],
                       locator=c['locator'])
                  for r in data['rows'] for c in r['cells']]
        self.db.get(EvidenceTableGeometry, (self.file.id, 1)).payload = [dict(
            table_source='drawn_geometry', geometry_source='cell_rectangles',
            table=dict(page=1, table=rectangle(0, x=0, width=600, height=800), unlocated_values=0, values=values))]
        self.db.commit()
        with self.SessionLocal() as db:
            p = read_statement_import(db, case_id=self.case.id, evidence_file_id=self.file.id, currency='USD')
        request = dict(expected_revision=p['revision'], statement_id=p['statement_id'], currency='USD',
                       **{key: p['metadata'][key] for key in ('holder', 'account_number', 'institution', 'period_start', 'period_end')},
                       rows=[dict(id=r['id'], excluded=r['excluded'], date=r['fields'].get('date', ''),
                                  description=r['fields'].get('description', ''), amount_minor=r['fields'].get('amount_minor', '0'),
                                  direction=r['fields'].get('direction'), balance_minor=r['fields'].get('balance'), reason='') for r in p['rows']])
        with self.assertRaises(ValidationError):
            StatementImportRequest.model_validate(request)
        request['rows'][6].update(date='2021-04-22', reason='Read the first date against the original PDF.')
        result = self.confirm(request)
        self.assertEqual(result['transaction_count'], 2)
        self.db.expire_all()
        payment = self.db.scalar(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == UUID(result['source_document_id']), FinancialTransaction.row_index == 0))
        self.assertEqual(payment.description, 'EXAMPLE SHOP')
        self.assertEqual(payment.amount_minor, 1400)
        self.assertEqual(payment.bank_reference, '24137463GEJBPDNXO')
        document = self.db.get(FinancialSourceDocument, UUID(result['source_document_id']))
        retained = document.metadata_['statement_import_original']['rows'][6]
        self.assertNotIn('date', retained['fields'])
        self.assertEqual(retained['source_cells'][0]['expected_text'], 'O4/22')


    def test_corrected_card_balance_preserves_printed_value_and_reason(self):
        from postgres.models.financial import FinancialStatementPeriod
        from services.financial.periods import read_closing
        from services.financial.ledger_source import statement_source, LedgerSourceError
        from services.financial.pdf_candidates import _digest
        p, request = self.card_balance_request()
        closing = next(r for r in request['rows'] if r['description'] == 'Closing Balance')
        closing.update(balance_minor='93878', reason='Synthetic correction checked against the original.')
        with self.assertRaises(PdfMappingError):
            self.confirm(request)
        from services.financial.review_arithmetic import check_proposed_rows
        request['balance_exception_revision'] = check_proposed_rows(p, request['rows'])['checks_revision']
        request['balance_exception_reason'] = 'Synthetic printed closing value differs from the payments. Retain for investigation.'
        result = self.confirm(request)
        period = self.db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == UUID(result['source_document_id'])))
        self.assertEqual(read_closing(period).amount.minor_units, -93878)
        controls = statement_source(self.db, case_id=self.case.id, period_id=period.id)['reviewed_controls']
        self.assertEqual(controls['controls'][1]['original_text'], '= $937.78')
        self.assertEqual(controls['controls'][1]['reviewed_value'], '93878')
        self.assertIn('Synthetic correction', controls['reason'])
        from copy import deepcopy
        doc = self.db.get(FinancialSourceDocument, UUID(result['source_document_id']))
        metadata = deepcopy(doc.metadata_)
        metadata['statement_import_controls']['controls'][1]['locator']['rect'][0] = 1
        metadata['statement_import_controls_sha256'] = _digest(metadata['statement_import_controls'])
        doc.metadata_ = metadata
        with self.assertRaises(LedgerSourceError):
            statement_source(self.db, case_id=self.case.id, period_id=period.id)

    def test_card_summary_cannot_be_imported_as_a_payment_or_overflow_after_conversion(self):
        p, request = self.card_balance_request()
        balance = next(r for r in request['rows'] if r['description'] == 'Opening Balance')
        balance.update(excluded=False, date='2020-05-12', amount_minor='100000', reason='Not a payment')
        with self.assertRaisesRegex(PdfMappingError, 'not a transaction'):
            self.confirm(request)
        balance.update(excluded=True, balance_minor='-9223372036854775808')
        with self.assertRaisesRegex(PdfMappingError, 'supported balance range'):
            self.confirm(request)

    def test_repeated_summary_pages_flag_ambiguous_balances(self):
        from copy import deepcopy
        self.card_balance_request()
        geometry = self.db.get(EvidenceTableGeometry, (self.file.id, 1))
        geometry.payload = [*geometry.payload, deepcopy(geometry.payload[0])]
        self.db.commit()
        with self.SessionLocal() as db:
            proposal = read_statement_import(db, case_id=self.case.id, evidence_file_id=self.file.id, currency='USD')
        self.assertEqual(proposal['transaction_count'], 3)
        self.assertTrue(any('More than one opening amount owed' in issue for issue in proposal['issues']))
        self.assertTrue(any('More than one closing amount owed' in issue for issue in proposal['issues']))

    def test_one_confirmation_imports_all_payments_and_retry_does_not_duplicate(self):
        request=self.request(); result=self.confirm(request)
        self.assertEqual(result['transaction_count'],12)
        self.assertFalse(self.confirm(request)['created'])
        self.db.expire_all()
        rows=list(self.db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id==UUID(result['source_document_id']))))
        self.assertEqual(len(rows),12)

    def test_overlapping_imports_require_resolution_before_replacement(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from services.financial.statement_import import _existing_statement
        source = dict(page_number=1, table_index=0)
        candidates = [SimpleNamespace(metadata_={
            'statement_import_statement_id': str(index),
            'statement_import_original': {'sources': [source]},
        }) for index in range(2)]
        session = Mock()
        session.scalars.return_value = candidates
        with self.assertRaisesRegex(PdfMappingError, 'more than one imported statement'):
            _existing_statement(session, self.case.id, self.file, 'new-period', [(1, 0)])

    def test_printed_closing_control_is_retained_without_becoming_a_payment(self):
        from copy import deepcopy
        from postgres.models.financial import FinancialStatementPeriod
        from services.financial.periods import read_closing
        geometry = self.db.get(EvidenceTableGeometry, (self.file.id, 1))
        payload = deepcopy(geometry.payload)
        values = payload[0]['table']['values']
        index = max(item['row'] for item in values) + 1
        for column, value in ((0, '2023-12-31'), (1, 'Closing Balance'), (4, '€47,450')):
            values.append(dict(row=index, column=column, text=value,
                locator=rectangle(400, x=20+column*100, width=90, height=15)))
        geometry.payload = payload
        self.db.commit()
        request = self.request()
        self.assertTrue(request['rows'][-1]['excluded'])
        result = self.confirm(request)
        period = self.db.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == UUID(result['source_document_id'])))
        self.assertEqual(result['transaction_count'], 12)
        self.assertEqual(read_closing(period).amount.minor_units, 4745000)
        self.assertTrue(read_closing(period).is_independent)

    def test_bad_revision_or_unexplained_correction_writes_no_statement(self):
        for change in ('revision','correction'):
            request=self.request()
            if change=='revision':request['expected_revision']='0'*64
            else:request['rows'][2]['amount_minor']='1'
            with self.assertRaises(PdfMappingError):self.confirm(request)
        self.assertEqual(list(self.db.scalars(select(FinancialSourceDocument).where(FinancialSourceDocument.evidence_file_id==self.file.id))),[])

    def test_changed_bytes_are_not_imported(self):
        request=self.request();self.path.write_bytes(b'changed')
        with self.assertRaises(PdfMappingError):self.confirm(request)

    def test_row_write_failure_rolls_back_source_and_all_rows(self):
        with patch('services.financial.transactions.record_transactions',side_effect=RuntimeError('injected failure')):
            with self.assertRaises(RuntimeError):self.confirm()
        self.db.expire_all()
        self.assertEqual(list(self.db.scalars(select(FinancialSourceDocument).where(FinancialSourceDocument.evidence_file_id==self.file.id))),[])

    def test_manual_addition_requires_a_real_page_and_preserves_its_origin(self):
        request=self.request()
        request['rows'].append(dict(id='manual:missed',manual_page=2,date='2023-12-29',description='Missed payment',
            amount_minor='500',direction='debit',reason='Read from original page'))
        with self.assertRaises(PdfMappingError):self.confirm(request)
        request['rows'][-1]['manual_page']=1
        result=self.confirm(request)
        self.assertEqual(result['transaction_count'],13)

    def test_reprocessed_version_preserves_old_source_and_replaces_totals_once(self):
        from copy import deepcopy
        from services.financial.statement_reprocessing import create_statement_version
        old=self.confirm()
        original_id=self.file.id
        original_bytes=self.path.read_bytes()
        with self.SessionLocal() as db:
            request_id=uuid4()
            version=create_statement_version(db,case_id=self.case.id,evidence_file_id=original_id,request_id=request_id,
                actor=self.actor,resolve_path=Path)
            self.assertEqual(create_statement_version(db,case_id=self.case.id,evidence_file_id=original_id,
                request_id=request_id,actor=self.actor,resolve_path=Path).id,version.id)
            self.assertNotEqual(version.stored_path,str(self.path))
            self.assertEqual(Path(version.stored_path).read_bytes(),original_bytes)
            text=db.get(EvidenceDocumentText,original_id)
            geometry=db.get(EvidenceTableGeometry,(original_id,1))
            db.add(EvidenceDocumentText(evidence_file_id=version.id,content=text.content,content_sha256=text.content_sha256,
                character_count=text.character_count,engine_job_id=text.engine_job_id,source_locations=deepcopy(text.source_locations)))
            db.add(EvidenceTableGeometry(evidence_file_id=version.id,page_number=1,engine_job_id=geometry.engine_job_id,payload=deepcopy(geometry.payload)))
            db.commit();version_id=version.id
        self.file=self.db.get(type(self.file),version_id)
        request=self.request()
        with self.assertRaises(PdfMappingError):self.confirm(request)
        current=self.preview()['current_import']
        request.update(replaces_source_document_id=current['source_document_id'],replacement_revision=current['revision'],details_reason='New extraction reviewed against the original')
        result=self.confirm(request)
        self.assertEqual(result['transaction_count'],12)
        self.assertFalse(self.confirm(request)['created'])
        self.db.expire_all()
        old_rows=list(self.db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id==UUID(old['source_document_id']))))
        self.assertEqual(len(old_rows),12)
        self.assertTrue(all(r.ledger_status=='superseded' for r in old_rows))
        self.assertEqual(self.path.read_bytes(),original_bytes)
        self.assertIsNotNone(self.db.get(EvidenceDocumentText,original_id))
        from postgres.models.financial import AdjudicationEvent
        event = self.db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.subject_id == UUID(old['source_document_id']),
            AdjudicationEvent.decision == 'supersede_duplicate'))
        self.assertIn('New extraction reviewed against the original', event.reason)

    def test_image_reread_binds_method_to_request_and_preserves_original_bytes(self):
        from services.financial.statement_reprocessing import create_statement_version
        request_id = uuid4()
        original_bytes = self.path.read_bytes()
        with self.SessionLocal() as db:
            args = dict(case_id=self.case.id, evidence_file_id=self.file.id, request_id=request_id,
                actor=self.actor, resolve_path=Path)
            version = create_statement_version(db, **args, reading_mode='page_images')
            self.assertEqual(version.metadata_['statement_pdf_reading_mode'], 'page_images')
            self.assertEqual(Path(version.stored_path).read_bytes(), original_bytes)
            self.assertEqual(self.path.read_bytes(), original_bytes)
            self.assertEqual(create_statement_version(db, **args, reading_mode='page_images').id, version.id)
            with self.assertRaises(PdfMappingError):
                create_statement_version(db, **args, reading_mode='automatic')
            self.assertIsNotNone(db.get(EvidenceDocumentText, self.file.id))
            self.assertIsNone(db.get(EvidenceDocumentText, version.id))

    def test_invalid_reread_method_creates_no_version(self):
        from services.financial.statement_reprocessing import create_statement_version
        before = set(self.path.parent.iterdir())
        with self.SessionLocal() as db, self.assertRaises(PdfMappingError):
            create_statement_version(db, case_id=self.case.id, evidence_file_id=self.file.id,
                request_id=uuid4(), actor=self.actor, resolve_path=Path, reading_mode='guess')
        self.assertEqual(set(self.path.parent.iterdir()), before)

    def test_two_printed_periods_in_one_pdf_import_separately_without_duplicates(self):
        from tests.test_financial_statement_import_card import card_source
        from copy import deepcopy
        from postgres.models.financial import FinancialStatementPeriod
        first=self.db.scalar(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id==self.file.id))
        def payload(grid, page_number=1):
            return [dict(table_source='drawn_geometry',geometry_source='cell_rectangles',
                table=dict(page=page_number,table=dict(rectangle(0,x=0,width=600,height=600), page=page_number),unlocated_values=0,
                    values=[dict(row=r['row_index'],column=c['column_index'],text=c['expected_text'],
                        locator=dict(rectangle(20+r['row_index']*20,x=20+c['column_index']*100,width=90,height=15), page=page_number))
                        for r in grid['rows'] for c in r['cells']]))]
        grid=card_source()
        first.payload=payload(grid)
        second=deepcopy(grid)
        for row in second['rows']:
            for cell in row['cells']:
                cell['expected_text']=cell['expected_text'].replace('Jun.','Jul.').replace('May','Jun.')
                cell['expected_text']=cell['expected_text'].replace('31 days','30 days')
        # Conflicting headers occupying the same page cannot establish page-wide context.
        first.payload=payload(grid)+payload(second)
        self.db.commit()
        self.assertEqual(self.preview()['statement_choices'], [])
        # Two physical statement pages provide an unambiguous period for each.
        first.payload=payload(grid)
        self.db.add(EvidenceTableGeometry(evidence_file_id=self.file.id, page_number=2,
            engine_job_id=first.engine_job_id, payload=payload(second, 2)))
        text=self.db.get(EvidenceDocumentText, self.file.id)
        contents=['\n'.join(c['expected_text'] for r in value['rows'] for c in r['cells']) for value in (grid,second)]
        text.content='\n'.join(contents)
        text.content_sha256=hashlib.sha256(text.content.encode()).hexdigest()
        text.character_count=len(text.content)
        text.source_locations=[dict(kind='page',page_number=1,start_char=0,end_char=len(contents[0]),text_origin='digital_text_layer'),
            dict(kind='page',page_number=2,start_char=len(contents[0])+1,end_char=len(text.content),text_origin='digital_text_layer')]
        self.db.commit()
        choices=self.preview()['statement_choices']
        self.assertEqual(len(choices),2)
        receipts=[]
        for choice in choices:
            with self.SessionLocal() as db:
                proposal=read_statement_import(db,case_id=self.case.id,evidence_file_id=self.file.id,currency='USD',statement_id=choice['id'])
            request=dict(expected_revision=proposal['revision'],statement_id=choice['id'],currency='USD',
                holder=proposal['metadata']['holder'],account_number=proposal['metadata']['account_number'],institution=proposal['metadata']['institution'],
                period_start=choice['period_start'],period_end=choice['period_end'],rows=[])
            for row in proposal['rows']:
                fields=row['fields']
                request['rows'].append(dict(id=row['id'],excluded=row['excluded'],date=fields.get('date',choice['period_end'] if row['issues'] else ''),
                    description=fields.get('description',''),amount_minor=fields.get('amount_minor','0'),direction=fields.get('direction','credit'),
                    reason='Local test: interest date checked against period end.' if row['issues'] else ''))
            receipt=self.confirm(request)
            self.assertEqual(receipt['transaction_count'],3)
            self.assertFalse(self.confirm(request)['created'])
            receipts.append(UUID(receipt['source_document_id']))
        self.db.expire_all()
        self.assertEqual(len(list(self.db.scalars(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id.in_(receipts))))),2)
        self.assertEqual(len(list(self.db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id.in_(receipts))))),6)

    def andrews_request(self, share, *, install=False, no_payments=False):
        from tests.test_financial_statement_import_andrews import two_shares
        if install:
            grid = two_shares()
            if no_payments:
                grid['rows'] = [r for r in grid['rows'] if r['row_index'] not in (10, 11, 14, 15)]
                for r in grid['rows']:
                    if r['row_index'] == 12: r['cells'][-1]['expected_text'] = '100.00'
                    if r['row_index'] == 16: r['cells'][-1]['expected_text'] = '200.00'
            self.db.get(EvidenceTableGeometry, (self.file.id, 1)).payload = [dict(
                table_source='text_alignment', geometry_source='cell_rectangles',
                table=dict(page=1, table=rectangle(0, x=0, width=600, height=800), unlocated_values=0,
                    values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'], locator=c['locator'])
                            for r in grid['rows'] for c in r['cells']]))]
            self.db.commit()
        with self.SessionLocal() as db:
            choices = read_statement_import(db, case_id=self.case.id, evidence_file_id=self.file.id, currency='USD')
            choice = next(s for s in choices['statement_choices'] if s['share_reference'] == share)
            p = read_statement_import(db, case_id=self.case.id, evidence_file_id=self.file.id,
                                      currency='USD', statement_id=choice['id'])
        request = dict(expected_revision=p['revision'], statement_id=p['statement_id'], currency='USD',
            **{key:p['metadata'][key] for key in ('holder', 'account_number', 'institution', 'period_start', 'period_end')},
            rows=[dict(id=r['id'], excluded=r['excluded'], date=r['fields'].get('date',''),
                description=r['fields'].get('description',''), counterparty=r['fields'].get('counterparty',''),
                amount_minor=r['fields'].get('amount_minor','0'), direction=r['fields'].get('direction'),
                balance_minor=r['fields'].get('balance'), reason='') for r in p['rows']])
        return p, request

    def test_andrews_shares_on_one_page_import_as_two_accounts_and_keep_balance_sources(self):
        from postgres.models.financial import FinancialAccount, FinancialStatementPeriod
        from services.financial.periods import read_opening, read_closing
        from services.financial.ledger_source import statement_source
        p, a = self.andrews_request('0000', install=True)
        self.assertEqual(p['metadata']['balance_convention'], 'asset_balance')
        first = self.confirm(a)
        p, b = self.andrews_request('0040')
        self.assertIsNone(p['current_import'])
        second = self.confirm(b)
        self.assertNotEqual(first['account_id'], second['account_id'])
        self.assertFalse(self.confirm(a)['created'])
        self.assertFalse(self.confirm(b)['created'])
        self.db.expire_all()
        for result, kind, opening, closing in ((first, 'savings', 10000, 12000), (second, 'checking', 20000, 18000)):
            self.assertEqual(result['transaction_count'], 1)
            self.assertEqual(self.db.get(FinancialAccount, UUID(result['account_id'])).account_type, kind)
            period = self.db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == UUID(result['source_document_id'])))
            self.assertEqual(read_opening(period).amount.minor_units, opening)
            self.assertEqual(read_closing(period).amount.minor_units, closing)
            controls = statement_source(self.db, case_id=self.case.id, period_id=period.id)['reviewed_controls']
            self.assertEqual(controls['balance_convention'], 'asset_balance')
            self.assertEqual([c['reviewed_value'] for c in controls['controls']], [str(opening), str(closing)])
        saved = self.db.get(FinancialSourceDocument, UUID(first['source_document_id'])).metadata_['statement_import_original']
        self.assertTrue(saved['statement_row_addresses'])
        self.assertEqual(next(r for r in saved['rows'] if not r['excluded'])['continuation_sources'][0]['source_cells'][0]['expected_text'], 'Funds Transfer via Mobile')

    def test_andrews_statement_without_payments_saves_matching_balances(self):
        from postgres.models.financial import FinancialStatementPeriod
        from services.financial.periods import read_opening, read_closing
        p, request = self.andrews_request('0000', install=True, no_payments=True)
        self.assertTrue(p['can_import_balances'])
        result = self.confirm(request)
        self.assertEqual(result['transaction_count'], 0)
        self.assertFalse(self.confirm(request)['created'])
        self.db.expire_all()
        period = self.db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == UUID(result['source_document_id'])))
        self.assertEqual(read_opening(period).amount.minor_units, 10000)
        self.assertEqual(read_closing(period).amount.minor_units, 10000)

    def test_balance_only_cannot_hide_transactions_or_record_unexplained_movement(self):
        p, request = self.andrews_request('0000', install=True)
        self.assertFalse(p['can_import_balances'])
        for r in request['rows']:
            if not r['excluded']: r.update(excluded=True, reason='Test omitted payment')
        with self.assertRaisesRegex(PdfMappingError, 'matching opening and closing'):
            self.confirm(request)
        p, request = self.andrews_request('0000', install=True, no_payments=True)
        closing_id = next(r['id'] for r in p['rows'] if r['fields'].get('description') == 'Closing Balance')
        next(r for r in request['rows'] if r['id'] == closing_id).update(balance_minor='12000', reason='Synthetic changed balance')
        with self.assertRaisesRegex(PdfMappingError, 'matching opening and closing'):
            self.confirm(request)

    def test_andrews_reread_row_numbers_cannot_hide_an_existing_import_or_mix_shares(self):
        from copy import deepcopy
        _, savings_request = self.andrews_request('0000', install=True)
        savings = self.confirm(savings_request)
        _, checking_request = self.andrews_request('0040')
        checking = self.confirm(checking_request)
        # Simulate a new reading that inserted header rows but retained the
        # measured positions on the same source page. Row indexes are not stable.
        geometry = self.db.get(EvidenceTableGeometry, (self.file.id, 1))
        shifted = deepcopy(geometry.payload)
        for value in shifted[0]['table']['values']:
            value['row'] += 100
        geometry.payload = shifted
        self.db.commit()
        for share, existing in (('0000', savings), ('0040', checking)):
            proposal, request = self.andrews_request(share)
            self.assertEqual(proposal['current_import']['source_document_id'], existing['source_document_id'])
            with self.assertRaisesRegex(PdfMappingError, 'already has imported transactions'):
                self.confirm(request)

    def test_andrews_printed_order_is_saved_with_original_pdf_page_locations(self):
        from tests.test_financial_statement_import_andrews import source
        grids = [source([
            [(15, '06/04'), (75, 'Deposit ACH Example'), (310, '20.00 100.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '100.00')]], page=1, printed_page=2, names=False),
            source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00 80.00')],
            [(15, '--- Continued on following page ---')]], page=2, printed_page=1)]
        for grid in grids:
            geometry = self.db.get(EvidenceTableGeometry, (self.file.id, grid['page_number']))
            if geometry is None:
                geometry = EvidenceTableGeometry(evidence_file_id=self.file.id, page_number=grid['page_number'],
                    engine_job_id=self.db.get(EvidenceDocumentText, self.file.id).engine_job_id)
                self.db.add(geometry)
            geometry.payload = [dict(table_source='text_alignment', geometry_source='cell_rectangles',
                table=dict(page=grid['page_number'], table=dict(rectangle(0, x=0, width=600, height=800), page=grid['page_number']), unlocated_values=0,
                    values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'], locator=c['locator'])
                            for r in grid['rows'] for c in r['cells']]))]
        self.db.commit()
        proposal, request = self.andrews_request('0040')
        self.assertEqual(proposal['statement_page_numbers'], [2, 1])
        receipt = self.confirm(request)
        self.db.expire_all()
        saved = list(self.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == UUID(receipt['source_document_id'])).order_by(FinancialTransaction.row_index)))
        self.assertEqual([str(row.transaction_date) for row in saved], ['2020-06-03', '2020-06-04'])
        self.assertEqual([row.running_balance_minor for row in saved], [8000, 10000])
        self.assertEqual([row.provenance['statement_import_original']['page_number'] for row in saved], [2, 1])

    def test_closed_payment_share_saves_notice_without_inventing_a_final_balance(self):
        from tests.test_financial_statement_import_andrews import source
        from postgres.models.financial import FinancialAccount, FinancialStatementPeriod
        from services.financial.periods import read_opening, read_closing
        from services.financial.ledger_source import statement_source
        grid = source([[(15,'06/01 ID 0011 VISA PAYMENT Previous Balance'),(350,'0.00')],
                       [(15,'06/29 ID 0011 VISA PAYMENT Closed')],
                       [(15,'*** This is the final statement you will receive for this account***')]])
        self.db.get(EvidenceTableGeometry,(self.file.id,1)).payload=[dict(table_source='text_alignment',geometry_source='cell_rectangles',
            table=dict(page=1,table=rectangle(0,x=0,width=600,height=800),unlocated_values=0,
                values=[dict(row=r['row_index'],column=c['column_index'],text=c['expected_text'],locator=c['locator']) for r in grid['rows'] for c in r['cells']]))]
        self.db.commit()
        p, request = self.andrews_request('0011')
        self.assertTrue(p['can_record_account_closure']);self.assertFalse(p['can_import_balances'])
        self.assertEqual(p['metadata']['account_closure']['date'],'2020-06-29')
        from copy import deepcopy
        from services.financial.statement_import import check_import_request, StatementImportRequest
        incorrect = deepcopy(request)
        notice = next(r for r in incorrect['rows'] if 'Closed' in r['description'])
        notice.update(excluded=False, date='2020-06-29', amount_minor='100', direction='credit', reason='Wrongly treated closure as a payment')
        with self.assertRaisesRegex(PdfMappingError, 'closure notice is not a payment'):
            check_import_request(p, StatementImportRequest.model_validate(incorrect))
        result=self.confirm(request);self.assertEqual(result['transaction_count'],0)
        self.assertEqual(result['account_closed_on'],'2020-06-29')
        self.assertFalse(self.confirm(request)['created'])
        self.db.expire_all()
        account=self.db.get(FinancialAccount,UUID(result['account_id']));self.assertEqual(account.account_type,'other')
        period=self.db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id==UUID(result['source_document_id'])))
        self.assertEqual(read_opening(period).amount.minor_units,0)
        self.assertIsNone(read_closing(period).amount)
        controls=statement_source(self.db,case_id=self.case.id,period_id=period.id)['reviewed_controls']
        self.assertEqual([c['role'] for c in controls['controls']],['opening'])
        self.assertEqual(controls['account_closure']['original_text'],'06/29 ID 0011 VISA PAYMENT Closed')
        self.assertEqual(controls['account_closure']['date'],'2020-06-29')
        self.assertEqual(controls['account_closure']['locator']['page'],1)

    def test_unseparated_card_collection_keeps_readable_rows_out_of_one_combined_import(self):
        # Amounts can be readable even when older stored geometry omitted the
        # account/period headers. Do not turn all pages into one statement.
        text = self.db.get(EvidenceDocumentText, self.file.id)
        text.content += ('\nCapital One\nMay 12, 2020 - Jun. 11, 2020 | 31 days in Billing Cycle\n'
                         'Jun. 12, 2020 - Jul. 11, 2020 | 30 days in Billing Cycle\n')
        text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
        text.character_count = len(text.content)
        self.db.commit()
        result = self.preview()
        self.assertIn('Transaction amounts on later pages may already be readable', result['reading_failure'])
        self.assertEqual(result['transaction_count'], 0)
        self.assertEqual(result['rows'], [])
        self.assertTrue(result['sources'])
        self.assertEqual(result['page_numbers'], [1])
        from services.financial.statement_import import check_import_request
        with self.assertRaisesRegex(PdfMappingError, 'several Capital One statements'):
            check_import_request(result, None)
