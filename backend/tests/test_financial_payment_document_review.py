"""Wire reviews save findings and links, never a second ledger payment."""
import hashlib
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4
from sqlalchemy import select, func
from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink, WorkspaceEntryRevision, WorkspaceEntryEvent
from services.financial.pdf_candidates import PdfMappingError
from services.financial.payment_document_review import read_payment_document, save_payment_document, matching_payments
from services.financial.statement_import import read_statement_import
from services.financial.references import RowReading
from postgres.models.enums import TransactionDirection
from tests.test_financial_transactions_writer import TransactionPersistenceTestCase
from tests.test_financial_payment_document_proposal import wire_source
from tests.test_financial_pdf_geometry_candidates import rectangle


class PaymentDocumentReviewTests(TransactionPersistenceTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.db.connection(), tables=[EvidenceDocumentText.__table__, EvidenceTableGeometry.__table__,
            WorkspaceEntry.__table__, WorkspaceEntryLink.__table__, WorkspaceEntryRevision.__table__, WorkspaceEntryEvent.__table__, FinancialImportBatch.__table__, FinancialImportBatchItem.__table__])
        self.path=Path(self._directory)/'wire.pdf';self.path.write_bytes(b'%PDF-1.4\nSYNTHETIC WIRE TEST')
        self.wire=self.evidence(hashlib.sha256(self.path.read_bytes()).hexdigest());self.wire.stored_path=str(self.path)
        content='Synthetic wire report';job=uuid4();grid=wire_source()
        self.db.add(EvidenceDocumentText(evidence_file_id=self.wire.id,content=content,character_count=len(content),
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),engine_job_id=job,
            source_locations=[dict(kind='page',page_number=1,start_char=0,end_char=len(content),text_origin='digital_text_layer')]))
        self.db.add(EvidenceTableGeometry(evidence_file_id=self.wire.id,page_number=1,engine_job_id=job,
            payload=[dict(table_source='text_alignment',geometry_source='cell_rectangles',table=dict(page=1,
                table=rectangle(0,x=0,width=600,height=800),unlocated_values=0,
                values=[dict(row=r['row_index'],column=c['column_index'],text=c['expected_text'],locator=c['locator']) for r in grid['rows'] for c in r['cells']]))]))
        self.db.commit()

    def request(self):
        p=read_payment_document(self.db,case_id=self.case.id,evidence_file_id=self.wire.id)
        return dict(request_id=str(uuid4()),expected_revision=p['revision'],title='Synthetic wire review',
            values={f['key']:f['value'] for f in p['fields']},reasons={},notes='Check the purpose of this payment.')

    def save(self,request):
        return save_payment_document(self.db,case_id=self.case.id,evidence_file_id=self.wire.id,request=request,user=self.user,resolve_path=Path)

    def matching(self,**changes):
        return matching_payments(self.db,case_id=self.case.id,request=dict(amount='120.00',currency='USD',value_date='2021-03-23',**changes))

    def payment(self, **changes):
        self.acct.currency='USD'
        args=dict(currency='USD',amount_minor=12000,direction=TransactionDirection.credit,
                  transaction_date=date(2021,3,24),description='SYNTHETIC PAYMENT')
        args.update(changes)
        row=self.write([self.draft(reading=RowReading(**args),row_index=len(list(self.db.scalars(select(FinancialTransaction)))))])[0]
        self.db.commit();return row

    def test_opening_wire_does_not_offer_statement_rows_and_saving_is_idempotent(self):
        p=read_statement_import(self.db,case_id=self.case.id,evidence_file_id=self.wire.id)
        self.assertTrue(p['document_review']['supported']);self.assertEqual(p['rows'],[])
        request=self.request();first=self.save(request);again=self.save(request)
        self.assertEqual(first['entry_id'],again['entry_id']);self.assertFalse(again['created'])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialTransaction)),0)
        note=self.db.get(WorkspaceEntry,UUID(first['entry_id']))
        self.assertIn('Wire amount: 120.00',note.body)
        self.assertEqual(note.entry_type,'note')
        link=self.db.scalar(select(WorkspaceEntryLink).where(WorkspaceEntryLink.entry_id==note.id))
        self.assertEqual(link.target_id,str(self.wire.id))
        self.assertEqual(link.link_metadata['original']['file_sha256'],self.wire.sha256)
        self.assertEqual(link.link_metadata['reviewed_values']['value_date'],'2021-03-23')
        request['notes']='Changed after save'
        with self.assertRaisesRegex(PdfMappingError,'already been used'):self.save(request)

    def test_correction_needs_reason_and_stale_source_or_altered_pdf_is_refused(self):
        request=self.request();request['values']['sending_party']='CORRECTED SYNTHETIC SENDER'
        with self.assertRaisesRegex(PdfMappingError,'Explain the correction'):self.save(request)
        request['reasons']['sending_party']='Checked the synthetic source name.'
        self.path.write_bytes(b'changed')
        with self.assertRaisesRegex(PdfMappingError,'differs'):self.save(request)
        self.path.write_bytes(b'%PDF-1.4\nSYNTHETIC WIRE TEST')
        request['expected_revision']='0'*64
        with self.assertRaisesRegex(PdfMappingError,'reading changed'):self.save(request)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(WorkspaceEntry)),0)

    def test_same_amount_candidate_can_be_linked_without_adding_a_payment(self):
        row=self.payment();matches=self.matching();self.assertEqual(len(matches['candidates']),1)
        request=self.request();request.update(transaction_id=str(row.id),transaction_revision=matches['candidates'][0]['revision'],link_reason='Same amount and checked source reference.')
        receipt=self.save(request)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialTransaction)),1)
        links=list(self.db.scalars(select(WorkspaceEntryLink).where(WorkspaceEntryLink.entry_id==UUID(receipt['entry_id']))))
        wire_link=next(l for l in links if l.target_id==str(self.wire.id));payment_link=next(l for l in links if l.target_id==str(self.evidence_file.id))
        self.assertNotIn('financial_transaction_ids',wire_link.source_anchor)
        self.assertEqual(payment_link.source_anchor['financial_transaction_ids'],[str(row.id)])
        self.assertEqual(payment_link.link_metadata['transactions'][0]['key'],str(row.id))
        from services.financial.transaction_notes import capture_transaction_notes
        captured=capture_transaction_notes(self.db,case_id=self.case.id,readings=[dict(row=dict(key=str(row.id),ref_id=row.ref_id,ledger_status='admitted'),source=dict(evidence_file_id=str(self.evidence_file.id)))])
        self.assertEqual(len(captured),1)

    def test_changed_payment_wrong_case_and_out_of_window_are_not_linked(self):
        row=self.payment();candidate=self.matching()['candidates'][0]
        request=self.request();request.update(transaction_id=str(row.id),transaction_revision=candidate['revision'],link_reason='Synthetic link check')
        row.description='Changed';self.db.commit()
        with self.assertRaisesRegex(PdfMappingError,'payment changed'):self.save(request)
        row.transaction_date=date(2021,4,10);row.ordering_date=row.transaction_date;self.db.commit()
        self.assertEqual(self.matching()['candidates'],[])
        with self.assertRaisesRegex(PdfMappingError,'no longer matches'):self.save(request)
        with self.assertRaisesRegex(PdfMappingError,'not found in this case'):
            read_payment_document(self.db,case_id=self.other_case.id,evidence_file_id=self.wire.id)

    def test_matching_handles_date_bounds_and_unknown_currency(self):
        for value in ('0001-01-01', '9999-12-31'):
            self.assertEqual(matching_payments(self.db, case_id=self.case.id,
                request=dict(amount='120.00', currency='USD', value_date=value))['candidates'], [])
        with self.assertRaisesRegex(PdfMappingError, 'Check the amount and currency'):
            matching_payments(self.db, case_id=self.case.id,
                request=dict(amount='120.00', currency='USO', value_date='2021-03-23'))

    def test_file_list_shows_saved_wire_reviews_without_implying_an_import(self):
        from services.financial.statement_file_status import statement_file_status
        receipt = self.save(self.request())
        status = statement_file_status(self.db, case_id=self.case.id)
        wire = next(item for item in status['files'] if item['evidence_file_id'] == str(self.wire.id))
        self.assertEqual(wire['wire_review_count'], 1)
        self.assertEqual(wire['current_transactions'], 0)
        self.assertEqual(wire['periods'], [])
        self.assertEqual(statement_file_status(self.db, case_id=self.other_case.id)['files'], [])
        from datetime import datetime, timezone
        self.db.get(WorkspaceEntry, UUID(receipt['entry_id'])).deleted_at = datetime.now(timezone.utc)
        self.db.commit()
        self.assertEqual(statement_file_status(self.db, case_id=self.case.id)['files'], [])
