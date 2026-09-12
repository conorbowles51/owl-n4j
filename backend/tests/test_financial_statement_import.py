import hashlib
from pathlib import Path
from uuid import uuid4, UUID
from services.financial.decisions import Actor
from unittest.mock import patch
from sqlalchemy import select
from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument
from services.financial.statement_import import read_statement_import, confirm_statement_import
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_transactions_writer import TransactionPersistenceTestCase
from tests.test_financial_pdf_geometry_candidates import rectangle
from tests.test_financial_statement_import_proposal import statement


class StatementImportTests(TransactionPersistenceTestCase):
    def setUp(self):
        super().setUp()
        self.actor=Actor(self.user.name,self.user.email,self.user.id)
        Base.metadata.create_all(self.db.connection(), tables=[EvidenceDocumentText.__table__, EvidenceTableGeometry.__table__])
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

    def test_corrected_card_balance_preserves_printed_value_and_reason(self):
        from postgres.models.financial import FinancialStatementPeriod
        from services.financial.periods import read_closing
        from services.financial.ledger_source import statement_source, LedgerSourceError
        from services.financial.pdf_candidates import _digest
        p, request = self.card_balance_request()
        closing = next(r for r in request['rows'] if r['description'] == 'Closing Balance')
        closing.update(balance_minor='93878', reason='Synthetic correction checked against the original.')
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

    def test_two_printed_periods_in_one_pdf_import_separately_without_duplicates(self):
        from tests.test_financial_statement_import_card import card_source
        from copy import deepcopy
        from postgres.models.financial import FinancialStatementPeriod
        first=self.db.scalar(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id==self.file.id))
        def payload(grid):
            return [dict(table_source='drawn_geometry',geometry_source='cell_rectangles',
                table=dict(page=1,table=rectangle(0,x=0,width=600,height=600),unlocated_values=0,
                    values=[dict(row=r['row_index'],column=c['column_index'],text=c['expected_text'],
                        locator=rectangle(20+r['row_index']*20,x=20+c['column_index']*100,width=90,height=15))
                        for r in grid['rows'] for c in r['cells']]))]
        grid=card_source()
        first.payload=payload(grid)
        second=deepcopy(grid)
        for row in second['rows']:
            for cell in row['cells']:
                cell['expected_text']=cell['expected_text'].replace('Jun.','Jul.').replace('May','Jun.')
                cell['expected_text']=cell['expected_text'].replace('31 days','30 days')
        # A second table on the same source page is enough to exercise period scope.
        first.payload=payload(grid)+payload(second)
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
